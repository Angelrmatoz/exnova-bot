"""ExnovaWSClient: cliente WebSocket propio para Exnova, sin depender de exnovaapi.

Implementa el ciclo mínimo del bróker sobre el protocolo WS de Exnova:
login HTTP (SSID), stream de velas, histórico, buy/sell, heartbeat y
reconexión con backoff exponencial.
"""

import json
import logging
import random
import ssl
import threading
import time
from datetime import datetime, timedelta

import requests
import websocket

logger = logging.getLogger(__name__)

AUTH_URL = "https://auth.trade.exnova.com/api/v2/login"
VERIFY_2FA_URL = "https://auth.trade.exnova.com/api/v2/verify/2fa"
WSS_URL = "wss://ws.trade.exnova.com/echo/websocket"

BALANCE_TYPE_ID = {"REAL": 1, "PRACTICE": 4, "TOURNAMENT": 2}

_2FA_HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Referer": "https://trade.exnova.com/en/login",
    "Sec-Fetch-Mode": "cors",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 6.3; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/77.0.3865.90 Safari/537.36"
    ),
}

_SSLOPT = {"check_hostname": False, "cert_reqs": ssl.CERT_NONE}


def _date_to_timestamp(dt):
    return time.mktime(dt.timetuple())


def _asset_name(name) -> str:
    """Nombre de activo: 'EUR.USD-OTC' -> 'USD-OTC' y fallback al nombre completo."""
    name = str(name)
    return name.split(".")[-1] if "." in name else name


def get_expiration_time(timestamp, duration):
    """Replica exnovaapi.expiration: expiración y tipo (turbo/binary)."""
    now_date = datetime.fromtimestamp(timestamp)
    exp_date = now_date.replace(second=0, microsecond=0)
    if (int(_date_to_timestamp(exp_date + timedelta(minutes=1))) - timestamp) > 30:
        exp_date = exp_date + timedelta(minutes=1)
    else:
        exp_date = exp_date + timedelta(minutes=2)
    exp = []
    for _ in range(5):
        exp.append(_date_to_timestamp(exp_date))
        exp_date = exp_date + timedelta(minutes=1)

    idx = 50
    index = 0
    now_date = datetime.fromtimestamp(timestamp)
    exp_date = now_date.replace(second=0, microsecond=0)
    while index < idx:
        if int(exp_date.strftime("%M")) % 15 == 0 and (int(_date_to_timestamp(exp_date)) - int(timestamp)) > 60 * 5:
            exp.append(_date_to_timestamp(exp_date))
            index = index + 1
        exp_date = exp_date + timedelta(minutes=1)

    remaning = [int(t) - int(time.time()) for t in exp]
    close = [abs(x - 60 * duration) for x in remaning]
    return int(exp[close.index(min(close))]), int(close.index(min(close)))


class ExnovaWSClient:
    """Cliente WebSocket mínimo de Exnova con reconexión automática."""

    def __init__(self, email: str, password: str, account_type: str = "PRACTICE"):
        self.email = email
        self.password = password
        self.account_type = account_type.upper()
        self.ssid = None
        self._token_sms = None
        self._token_login2fa = None
        self._session = requests.Session()
        self._session.headers.update({"User-Agent": _2FA_HEADERS["User-Agent"]})

        self.profile = None
        self.balance_id = None
        self.server_timestamp = None
        self._actives = {}
        self._init_all = None
        self._init_v2 = None

        self._app = None
        self._ws_thread = None
        self._stop = threading.Event()
        self._send_lock = threading.Lock()
        self._connected = threading.Event()
        self._profile_event = threading.Event()
        self._ts_event = threading.Event()
        self._candles_event = threading.Event()
        self._balances_event = threading.Event()
        self._init_event = threading.Event()
        self._init_v2_event = threading.Event()
        self._sold_event = threading.Event()

        self._candles_data = None
        self._balances_data = None
        self._realtime_candles = {}
        self._buy_result = None
        self._buy_option = {}
        self._closed = {}
        self._sold = None
        self._subscriptions = set()

        self._reconnect_backoff = 2.0
        self._max_backoff = 30.0

    # -------------------------------------------------------------- HTTP auth

    def _http_post(self, url, data, headers=None):
        return self._session.post(url, json=data, headers=headers, timeout=30)

    def _login(self):
        resp = self._http_post(AUTH_URL, {"identifier": self.email, "password": self.password})
        try:
            body = resp.json()
        except json.JSONDecodeError:
            return False, resp.text
        if resp.status_code >= 400:
            return False, body.get("message", resp.text)
        if body.get("code") == "verify":
            sms = self._http_post(VERIFY_2FA_URL, {"method": "sms", "token": body["token"]}, _2FA_HEADERS)
            if sms.json().get("code") != "success":
                return False, sms.json().get("message")
            self._token_sms = sms.json()["token"]
            return False, "2FA"
        try:
            self.ssid = resp.cookies["ssid"]
        except KeyError:
            return False, body.get("message", "no ssid en respuesta")
        return True, None

    def connect(self) -> tuple[bool, str | None]:
        """Login HTTP + arranque del WS. Con 2FA devuelve (False, '2FA')."""
        if not self._stop.is_set():
            self.close()
        ok, reason = self._login()
        if not ok:
            return ok, reason
        self._start()
        return True, None

    def connect_2fa(self, sms_code: str) -> tuple[bool, str | None]:
        resp = self._http_post(VERIFY_2FA_URL, {"code": str(sms_code), "token": self._token_sms}, _2FA_HEADERS)
        body = resp.json()
        if body.get("code") != "success":
            return False, body.get("message")
        self._token_login2fa = body["token"]
        resp = self._http_post(
            AUTH_URL,
            {"identifier": self.email, "password": self.password, "token": self._token_login2fa},
        )
        try:
            self.ssid = resp.cookies["ssid"]
        except KeyError:
            return False, resp.text
        self._start()
        return True, None

    # ------------------------------------------------------------ WS lifecycle

    def _start(self):
        self._stop.clear()
        self._ws_thread = threading.Thread(target=self._ws_loop, daemon=True)
        self._ws_thread.start()
        if not self._connected.wait(20):
            raise TimeoutError("no se pudo conectar al websocket de Exnova")

    def _ws_loop(self):
        while not self._stop.is_set():
            backoff = self._reconnect_backoff
            self._connected.clear()
            self._profile_event.clear()
            self._ts_event.clear()
            self._app = websocket.WebSocketApp(
                WSS_URL,
                on_open=self._on_open,
                on_message=self._on_message,
                on_error=self._on_error,
                on_close=self._on_close,
            )
            try:
                self._app.run_forever(
                    sslopt=_SSLOPT,
                    ping_interval=15,
                    ping_timeout=10,
                    suppress_origin=True,
                )
            except Exception:
                logger.exception("error en run_forever")
            if self._stop.is_set():
                break
            logger.warning("ws desconectado, reconexión en %.1fs", backoff)
            time.sleep(backoff)
            self._reconnect_backoff = min(self._reconnect_backoff * 2, self._max_backoff)

    def _on_open(self, wss):
        logger.info("ws conectado")
        self._profile_event.clear()
        self._ts_event.clear()
        self._send_raw({"name": "ssid", "msg": self.ssid})
        threading.Thread(target=self._handshake, args=(wss,), daemon=True).start()

    def _handshake(self, wss):
        if not self._profile_event.wait(10):
            wss.close()
            return
        if self.profile is False:
            logger.error("ssid rechazado por el servidor")
            wss.close()
            return
        if not self._ts_event.wait(10):
            wss.close()
            return
        self._send_raw({"name": "setOptions", "msg": {"sendResults": True}, "request_id": "1"})
        for pair, size in self._subscriptions:
            try:
                self._subscribe_msg(pair, size)
            except ValueError:
                pass
        self._reconnect_backoff = 2.0
        self._connected.set()

    def _on_error(self, wss, error):
        logger.error("ws error: %s", error)

    def _on_close(self, wss, close_status_code=None, close_msg=None):
        self._connected.clear()

    def close(self):
        self._stop.set()
        if self._app is not None:
            try:
                self._app.close()
            except Exception:
                pass
        if self._ws_thread is not None and self._ws_thread.is_alive():
            self._ws_thread.join(timeout=5)

    def check_connect(self) -> bool:
        return self._connected.is_set()

    # --------------------------------------------------------------- sending

    def _send_raw(self, data):
        with self._send_lock:
            if self._app is not None:
                self._app.send(json.dumps(data))

    def _send(self, name, msg, request_id=""):
        if request_id == "":
            request_id = int(str(time.time()).split(".")[1])
        self._send_raw({"name": name, "msg": msg, "request_id": request_id})

    def _set_options(self, send_results: bool):
        self._send("setOptions", {"sendResults": send_results}, request_id="1")

    # ------------------------------------------------------------- receiving

    def _on_message(self, wss, message):
        try:
            msg = json.loads(message)
        except (json.JSONDecodeError, TypeError):
            logger.warning("frame no-JSON ignorado: %.100r", message)
            return
        name = msg.get("name")
        data = msg.get("msg")
        if name == "timeSync":
            self.server_timestamp = data / 1000
            self._ts_event.set()
        elif name == "heartbeat":
            self._send_raw({
                "name": "heartbeat",
                "msg": {"msg": {
                    "heartbeatTime": int(data),
                    "userTime": int(self.server_timestamp * 1000),
                }},
                "request_id": "",
            })
        elif name == "profile":
            self.profile = data
            self._profile_event.set()
            if data and self.balance_id is None:
                target_type = BALANCE_TYPE_ID.get(self.account_type, 4)
                for balance in data.get("balances", []):
                    if balance["type"] == target_type:
                        self.balance_id = balance["id"]
                        break
        elif name == "candles":
            self._candles_data = data.get("candles", [])
            self._candles_event.set()
        elif name == "balances":
            self._balances_data = data
            self._balances_event.set()
        elif name == "candle-generated":
            self._on_candle(data)
        elif name == "buyComplete":
            if data.get("isSuccessful"):
                self._buy_option[str(msg.get("request_id"))] = {"id": data.get("result", {}).get("id")}
        elif name == "option":
            self._buy_option[str(msg.get("request_id"))] = data
        elif name == "result":
            self._buy_result = data.get("success")
        elif name == "socket-option-closed":
            self._closed[data["id"]] = data
        elif name == "sold-options":
            self._sold = data
            self._sold_event.set()
        elif name == "api_option_init_all_result":
            self._init_all = data
            self._init_event.set()
        elif name == "initialization-data":
            self._init_v2 = data
            self._init_v2_event.set()

    def _on_candle(self, data):
        active_id = data.get("active_id")
        size = data.get("size")
        key = (active_id, size)
        self._realtime_candles[key] = data

    def get_realtime_candle(self, pair: str, size: int) -> dict | None:
        active_id = self._active_id(pair)
        return self._realtime_candles.get((active_id, size))

    # ------------------------------------------------------------ candles API

    @staticmethod
    def _to_seconds(timeframe: str) -> int:
        unit = timeframe[-1]
        value = int(timeframe[:-1])
        return {"s": 1, "m": 60, "h": 3600}[unit] * value

    @staticmethod
    def _to_minutes(duration: str) -> int:
        seconds = ExnovaWSClient._to_seconds(duration)
        return max(1, round(seconds / 60))

    def _active_id(self, pair: str) -> int:
        if not self._actives:
            self._load_actives()
        if pair in self._actives:
            return self._actives[pair]
        bare = pair.replace(".", "").upper()
        for name, aid in self._actives.items():
            if name.replace(".", "").upper() == bare:
                return aid
        raise ValueError(f"activo no encontrado: {pair}") from None

    def get_candles(self, pair: str, timeframe: str, count: int, endtime: int | None = None) -> list[dict]:
        interval = self._to_seconds(timeframe)
        if endtime is None:
            endtime = int(self.server_timestamp)
        active_id = self._active_id(pair)
        self._candles_data = None
        self._candles_event.clear()
        self._send("sendMessage", {
            "name": "get-candles",
            "version": "2.0",
            "body": {
                "active_id": int(active_id),
                "split_normalization": True,
                "size": interval,
                "to": int(endtime),
                "count": count,
                "": active_id,
            },
        })
        if not self._candles_event.wait(15):
            raise TimeoutError(f"timeout esperando velas de {pair}")
        return [
            {"time": c["from"], "open": c["open"], "close": c["close"],
             "high": c["max"], "low": c["min"]}
            for c in (self._candles_data or [])
        ]

    # ------------------------------------------------------------- streaming

    def subscribe(self, pair: str, size: int):
        self._subscriptions.add((pair, size))
        self._subscribe_msg(pair, size)

    def unsubscribe(self, pair: str, size: int):
        self._subscriptions.discard((pair, size))
        active_id = self._active_id(pair)
        self._send("unsubscribeMessage", {
            "name": "candle-generated",
            "params": {"routingFilters": {"active_id": str(active_id), "size": int(size)}},
        })

    def _subscribe_msg(self, pair: str, size: int):
        active_id = self._active_id(pair)
        self._send("subscribeMessage", {
            "name": "candle-generated",
            "params": {"routingFilters": {"active_id": str(active_id), "size": int(size)}},
        })

    # ------------------------------------------------------------------ init

    def _load_actives(self):
        try:
            data = self.get_all_init_v2()
        except Exception:
            data = None
        if data:
            for option in ("binary", "turbo"):
                for aid, active in data.get(option, {}).get("actives", {}).items():
                    self._actives[_asset_name(active["name"])] = int(aid)

    def get_all_init_v2(self, timeout: int = 30) -> dict:
        self._init_v2 = None
        self._init_v2_event.clear()
        self._send("sendMessage", {"name": "get-initialization-data", "version": "3.0", "body": {}})
        if not self._init_v2_event.wait(timeout):
            raise TimeoutError("timeout esperando initialization-data")
        return self._init_v2

    def get_all_init(self, timeout: int = 30) -> dict:
        self._init_all = None
        self._init_event.clear()
        self._send("api_option_init_all", "")
        if not self._init_event.wait(timeout):
            raise TimeoutError("timeout esperando api_option_init_all")
        return self._init_all

    def get_available_assets(self) -> list[str]:
        data = self.get_all_init_v2() or {}
        assets = set()
        for option in ("binary", "turbo"):
            for active in data.get(option, {}).get("actives", {}).values():
                name = _asset_name(active["name"])
                if active.get("enabled") and not active.get("is_suspended"):
                    assets.add(name)
        return sorted(assets)

    def get_payout(self, pair: str) -> float | None:
        init_info = self.get_all_init()
        for option in ("turbo", "binary"):
            for active in init_info.get("result", {}).get(option, {}).get("actives", {}).values():
                if _asset_name(active["name"]) == pair:
                    return (100.0 - active["option"]["profit"]["commission"]) / 100.0
        return None

    # --------------------------------------------------------------- trading

    def buy(self, pair: str, side: str, amount: float, duration: str) -> tuple[bool, str | None]:
        req_id = str(random.randint(0, 10000))
        minutes = self._to_minutes(duration)
        exp, idx = get_expiration_time(int(self.server_timestamp), minutes)
        option_type_id = 3 if idx < 5 else 1
        body = {
            "price": float(amount),
            "active_id": self._active_id(pair),
            "expired": int(exp),
            "direction": side.lower(),
            "option_type_id": option_type_id,
            "user_balance_id": int(self.balance_id),
        }
        self._buy_result = None
        self._buy_option = {}
        self._send("sendMessage", {"name": "binary-options.open-option", "version": "1.0", "body": body}, request_id=req_id)
        start = time.time()
        while time.time() - start < 10:
            option = self._buy_option.get(req_id, {})
            if "message" in option:
                return False, option["message"]
            if self._buy_result is not None and "id" in option:
                return self._buy_result, option["id"]
            time.sleep(0.05)
        logger.warning("buy timeout para %s", pair)
        return False, None

    def check_result(self, order_id: str, timeout: float = 120.0) -> tuple[str, float]:
        start = time.time()
        while time.time() - start < timeout:
            x = self._closed.get(order_id)
            if x is not None:
                payload = x.get("msg") if isinstance(x.get("msg"), dict) else x
                win = payload["win"]
                pnl = (
                    0.0 if win == "equal" else
                    float(payload["sum"]) * -1 if win == "loose" else
                    float(payload["win_amount"]) - float(payload["sum"])
                )
                return win, pnl
            time.sleep(0.1)
        raise TimeoutError(f"timeout esperando cierre de la opción {order_id}")

    def sell(self, options_ids) -> dict | None:
        if not isinstance(options_ids, list):
            options_ids = [options_ids]
        self._sold = None
        self._sold_event.clear()
        self._send("sendMessage", {
            "name": "sell-options", "version": "2.0", "body": {"options_ids": options_ids},
        })
        if not self._sold_event.wait(10):
            raise TimeoutError("timeout esperando sold-options")
        return self._sold

    # -------------------------------------------------------------- balance

    def get_balances(self, timeout: int = 10) -> list[dict]:
        self._balances_data = None
        self._balances_event.clear()
        self._send("sendMessage", {"name": "get-balances", "version": "1.0"})
        if not self._balances_event.wait(timeout):
            raise TimeoutError("timeout esperando get-balances")
        return list(self._balances_data) if isinstance(self._balances_data, list) else []

    def get_balance(self) -> float:
        if self.balance_id is None:
            return 0.0
        for balance in self.get_balances():
            if balance["id"] == self.balance_id:
                return balance["amount"]
        return 0.0
