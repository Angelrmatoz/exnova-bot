"""IqOptionWSClient: cliente WebSocket propio para IQ Option (misma familia Quadcode que Exnova).

Protocolo IQ Option (RE en vivo sobre wss://ws.iqoption.com/echo/websocket):
- Auth con ssid (cookie de sesión, no login HTTP — la API de login responde 403).
  El ssid se obtiene de la cookie del navegador tras loguearse.
- get-first-candles antes de suscribir velas; candles por id o timestamp.
- Órdenes con binary-options.open-option v2.0 (expired = timestamp absoluto).
- Resultado vía suscripción portfolio.position-changed.
"""

import json
import logging
import random
import ssl
import threading
import time

import websocket

logger = logging.getLogger(__name__)

WSS_URL = "wss://ws.iqoption.com/echo/websocket"

BALANCE_TYPE_ID = {"REAL": 1, "PRACTICE": 4, "TOURNAMENT": 2}

_SSLOPT = {"check_hostname": False, "cert_reqs": ssl.CERT_NONE}

_TURBO_OPTION_TYPE_ID = 3


def get_expiration_time(timestamp, duration_seconds):
    """Próximo cierre de vela alineado con margen >= 30s (IQ rechaza vencimientos casi vencidos).

    Devuelve timestamp absoluto del vencimiento de una opción turbo.
    """
    step = duration_seconds
    next_close = (int(timestamp) // step + 1) * step
    if next_close - timestamp < 30:
        next_close += step
    return next_close


class IqOptionWSClient:
    """Cliente WebSocket mínimo de IQ Option con reconexión automática."""

    def __init__(self, ssid: str, account_type: str = "PRACTICE"):
        self.ssid = ssid
        self.account_type = account_type.upper()

        self.profile = None
        self.balance_id = None
        self.user_id = None
        self.server_timestamp = None
        self._ts_mono = None
        self._connect_error = None
        self._authenticated = None
        self._actives = {}
        self._underlyings = {}
        self._actives_loaded = False
        self._init_cache = None
        self._init_cache_at = 0.0

        self._app = None
        self._ws_thread = None
        self._stop = threading.Event()
        self._send_lock = threading.Lock()
        self._connected = threading.Event()
        self._connect_failed = threading.Event()
        self._auth_event = threading.Event()
        self._ts_event = threading.Event()
        self._candles_event = threading.Event()
        self._first_candles_event = threading.Event()
        self._balances_event = threading.Event()
        self._underlying_event = threading.Event()
        self._trading_params_event = threading.Event()
        self._positions_event = threading.Event()
        self._init_event = threading.Event()

        self._candles_data = None
        self._first_candles_data = None
        self._balances_data = None
        self._underlying_data = None
        self._trading_params_data = None
        self._positions_data = None
        self._init_data = None
        self._realtime_candles = {}
        self._buy_result = None
        self._buy_option = {}
        self._closed = {}
        self._subscriptions = set()

        self._reconnect_backoff = 2.0
        self._max_backoff = 30.0

    def connect(self) -> tuple[bool, str | None]:
        """Arranca el WS y autentica con el ssid."""
        if not self._stop.is_set():
            self.close()
        self._connect_error = None
        try:
            self._start()
        except TimeoutError as e:
            self.close()
            return False, str(e)
        if self._connect_error:
            self.close()
            return False, self._connect_error
        return True, None

    # ------------------------------------------------------------ WS lifecycle

    def _start(self):
        self._stop.clear()
        self._authenticated = None
        self._connect_failed.clear()
        self._ws_thread = threading.Thread(target=self._ws_loop, daemon=True)
        self._ws_thread.start()
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            if self._connected.wait(0.1):
                return
            if self._connect_failed.is_set():
                break
        raise TimeoutError(self._connect_error or "no se pudo conectar al websocket de IQ Option")

    def _ws_loop(self):
        while not self._stop.is_set():
            backoff = self._reconnect_backoff
            self._connected.clear()
            self._auth_event.clear()
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
            self._stop.wait(backoff)
            self._reconnect_backoff = min(self._reconnect_backoff * 2, self._max_backoff)

    def _on_open(self, wss):
        logger.info("ws conectado")
        self._send_raw({
            "name": "authenticate",
            "msg": {"ssid": self.ssid, "protocol": 3},
        })
        threading.Thread(target=self._handshake, args=(wss,), daemon=True).start()

    def _fail(self, reason, wss=None):
        self._connect_error = reason
        self._connect_failed.set()
        if wss is not None:
            try:
                wss.close()
            except Exception:
                pass

    def _handshake(self, wss):
        if not self._auth_event.wait(10):
            logger.error("timeout esperando authenticated")
            self._fail("timeout esperando authenticated", wss)
            return
        if not self._authenticated:
            logger.error("ssid inválido o sesión expirada")
            self._fail("ssid inválido o sesión expirada", wss)
            return
        if not self._ts_event.wait(10):
            logger.error("timeout esperando timeSync")
            self._fail("timeout esperando timeSync", wss)
            return
        self._send("setOptions", {"sendResults": True}, request_id="1")
        try:
            balances = self.get_balances(timeout=10)
            target_type = BALANCE_TYPE_ID.get(self.account_type, 4)
            for balance in balances:
                if balance["type"] == target_type:
                    self.balance_id = balance["id"]
                    self.user_id = balance["user_id"]
                    break
        except TimeoutError:
            logger.error("no se obtuvieron balances en handshake")
            self._fail("no se obtuvieron balances", wss)
            return
        if self.balance_id is None:
            logger.error("sin balance de tipo %s", self.account_type)
            self._fail(f"sin balance de tipo {self.account_type}", wss)
            return
        try:
            self.get_initialization_data()
        except TimeoutError:
            logger.warning("initialization-data no llegó en handshake")
        self._subscribe_positions()
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

    def server_now(self) -> float:
        """Hora estimada del servidor, corregida por el offset de timeSync."""
        if self.server_timestamp is None:
            return time.time()
        if self._ts_mono is None:
            return self.server_timestamp
        return self.server_timestamp + (time.monotonic() - self._ts_mono)

    # --------------------------------------------------------------- sending

    def _send_raw(self, data):
        with self._send_lock:
            if self._app is not None:
                self._app.send(json.dumps(data))

    def _send(self, name, msg, request_id=""):
        if request_id == "":
            request_id = int(str(time.time()).split(".")[1])
        self._send_raw({"name": name, "msg": msg, "request_id": request_id})

    # ------------------------------------------------------------- receiving

    def _on_message(self, wss, message):
        try:
            msg = json.loads(message)
        except (json.JSONDecodeError, TypeError):
            logger.warning("frame no-JSON ignorado: %.100r", message)
            return
        name = msg.get("name")
        data = msg.get("msg")
        if name == "authenticated":
            self._authenticated = bool(data)
            if not self._authenticated:
                self._connect_error = "ssid inválido o sesión expirada"
                self._connect_failed.set()
            self._auth_event.set()
        elif name == "timeSync":
            self.server_timestamp = data / 1000
            self._ts_mono = time.monotonic()
            self._ts_event.set()
        elif name == "candles":
            self._candles_data = data.get("candles", [])
            self._candles_event.set()
        elif name == "first-candles":
            self._first_candles_data = data
            self._first_candles_event.set()
        elif name == "balances":
            self._balances_data = data
            self._balances_event.set()
        elif name == "underlying-list":
            self._underlying_data = data.get("underlying", [])
            self._underlying_event.set()
        elif name == "trading-params":
            self._trading_params_data = data
            self._trading_params_event.set()
        elif name == "positions":
            self._positions_data = data
            self._positions_event.set()
        elif name == "history-positions":
            self._positions_data = data
            self._positions_event.set()
        elif name == "initialization-data":
            self._init_data = data
            self._init_event.set()
        elif name == "candle-generated":
            self._on_candle(data)
        elif name == "option":
            self._buy_option[str(msg.get("request_id"))] = data
        elif name == "result":
            self._buy_result = data.get("success")
        elif name == "position-changed":
            self._on_position_changed(data)

    def _on_candle(self, data):
        active_id = data.get("active_id")
        size = data.get("size")
        key = (active_id, size)
        self._realtime_candles[key] = data

    def _on_position_changed(self, data):
        raw = data.get("raw_event", {})
        option = raw.get("binary_options_option_changed1", {})
        option_id = option.get("option_id")
        if option_id is None:
            return
        result = option.get("result")
        if result in ("win", "lose", "loose", "tie", "equal"):
            self._closed[str(option_id)] = option

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
        seconds = IqOptionWSClient._to_seconds(duration)
        return max(1, round(seconds / 60))

    def _active_id(self, pair: str) -> int:
        if not self._actives and not self._actives_loaded:
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
            endtime = int(self.server_now())
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
                "from": 0,
                "to": int(endtime),
                "count": count,
                "only_closed": True,
            },
        })
        if not self._candles_event.wait(15):
            raise TimeoutError(f"timeout esperando velas de {pair}")
        return [
            {"time": c["from"], "open": c["open"], "close": c["close"],
             "high": c["max"], "low": c["min"]}
            for c in (self._candles_data or [])
        ]

    def get_first_candles(self, active_id: int, timeout: int = 15) -> dict:
        self._first_candles_data = None
        self._first_candles_event.clear()
        self._send("sendMessage", {
            "name": "get-first-candles",
            "version": "1.0",
            "body": {"active_id": int(active_id), "split_normalization": True},
        })
        if not self._first_candles_event.wait(timeout):
            raise TimeoutError("timeout esperando first-candles")
        return self._first_candles_data

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
        self.get_first_candles(active_id)
        self._send("subscribeMessage", {
            "name": "candle-generated",
            "params": {"routingFilters": {"active_id": str(active_id), "size": int(size)}},
        })

    def _subscribe_positions(self):
        if self.user_id is None or self.balance_id is None:
            return
        self._send("subscribeMessage", {
            "name": "portfolio.position-changed",
            "version": "3.0",
            "params": {
                "routingFilters": {
                    "user_id": self.user_id,
                    "user_balance_id": self.balance_id,
                    "instrument_type": "turbo-option",
                }
            },
        })

    # ------------------------------------------------------------------ init

    def _load_actives(self):
        try:
            data = self.get_underlying_list()
        except Exception:
            data = []
        for item in data:
            name = item.get("name")
            if not name:
                continue
            self._underlyings[name] = item
            active_id = item.get("active_id")
            if active_id is not None:
                self._actives[name] = int(active_id)
        self._actives_loaded = True

    def get_schedule(self, pair: str) -> list | None:
        """Ventanas [open, close] del activo desde underlying-list."""
        self._active_id(pair)
        item = self._underlyings.get(pair)
        if item is not None:
            return item.get("schedule")
        bare = pair.replace(".", "").upper()
        for name, data in self._underlyings.items():
            if name.replace(".", "").upper() == bare:
                return data.get("schedule")
        return None

    def get_underlying_list(self, timeout: int = 15) -> list[dict]:
        self._underlying_data = None
        self._underlying_event.clear()
        self._send("sendMessage", {
            "name": "digital-option-instruments.get-underlying-list",
            "version": "3.0",
            "body": {"filter_suspended": True},
        })
        if not self._underlying_event.wait(timeout):
            raise TimeoutError("timeout esperando underlying-list")
        return list(self._underlying_data or [])

    def get_available_assets(self) -> list[str]:
        if not self._actives and not self._actives_loaded:
            self._load_actives()
        return sorted(
            name for name, item in self._underlyings.items()
            if not item.get("is_suspended") and item.get("is_enabled", True)
        )

    def get_payout(self, pair: str) -> float | None:
        for kind in ("binary", "turbo"):
            try:
                payout = self._payout_for(pair, kind)
            except Exception:
                payout = None
            if payout is not None:
                return payout
        params = self.get_trading_params()
        commissions = {
            c["active_id"]: c["value"]
            for c in params.get("commissions", [])
        }
        active_id = self._active_id(pair)
        commission = commissions.get(active_id)
        if commission is None:
            return None
        return (100.0 - commission) / 100.0

    def get_trading_params(self, timeout: int = 15) -> dict:
        self._trading_params_data = None
        self._trading_params_event.clear()
        self._send("sendMessage", {
            "name": "trading-settings.get-trading-group-params",
            "version": "2.0",
            "body": {"instrument_type": "turbo-option"},
        })
        if not self._trading_params_event.wait(timeout):
            raise TimeoutError("timeout esperando trading-params")
        return dict(self._trading_params_data or {})

    def get_initialization_data(self, timeout: int = 15) -> dict:
        self._init_data = None
        self._init_event.clear()
        self._send("sendMessage", {"name": "get-initialization-data", "version": "4.0", "body": {}})
        if not self._init_event.wait(timeout):
            raise TimeoutError("timeout esperando initialization-data")
        return dict(self._init_data or {})

    def _initialization(self) -> dict:
        if self._init_cache is None and self._init_data:
            self._init_cache = self._init_data
            self._init_cache_at = time.monotonic()
        if self._init_cache is None or time.monotonic() - self._init_cache_at > 30:
            self._init_cache = self.get_initialization_data()
            self._init_cache_at = time.monotonic()
        return self._init_cache

    def _active_config(self, pair: str, kind: str) -> dict | None:
        active_id = self._active_id(pair)
        actives = (self._initialization().get(kind) or {}).get("actives") or {}
        return actives.get(str(active_id))

    def _payout_for(self, pair: str, kind: str) -> float | None:
        active = self._active_config(pair, kind)
        if not active:
            return None
        commission = (((active.get("option") or {}).get("profit") or {}).get("commission"))
        if commission is None:
            return None
        return (100.0 - commission) / 100.0

    @staticmethod
    def _next_expiration(active: dict, seconds: int, now: float) -> int | None:
        opt = active.get("option") or {}
        start = int(opt.get("start_time") or 0)
        step = int(opt.get("exp_time") or 0) or seconds
        count = int(opt.get("count") or 0)
        if start > 0 and step > 0 and count > 0:
            earliest = now + float(active.get("deadtime") or 0)
            candidates = [
                start + k * step for k in range(count)
                if start + k * step >= earliest
            ]
            if not candidates:
                return None
            target = now + seconds
            best = min(candidates, key=lambda e: abs(e - target))
            if abs(best - target) > step + float(active.get("deadtime") or 0):
                return None
            return int(best)
        return int(get_expiration_time(int(now), seconds))

    def resolve_expiration(self, pair: str, duration: str) -> tuple[int, int, str]:
        """Elige tipo de opción y vencimiento válido para `duration`.

        `expiration_times` es la grilla (1m turbo, 15m binaria), no la lista de
        duraciones. Igual que Exnova: <=5m usa turbo; >5m usa binaria, y se
        elige el vencimiento de la grilla más cercano a `now + duration`.
        """
        seconds = self._to_seconds(duration)
        now = self.server_now()
        preferred = (("turbo", _TURBO_OPTION_TYPE_ID), ("binary", 1))
        if seconds > 5 * 60:
            preferred = (("binary", 1), ("turbo", _TURBO_OPTION_TYPE_ID))
        supported = {}
        for kind, type_id in preferred:
            active = self._active_config(pair, kind)
            if not active or active.get("is_suspended") or not active.get("enabled", True):
                continue
            opt = active.get("option") or {}
            exp = self._next_expiration(active, seconds, now)
            if exp is None:
                supported[kind] = opt.get("expiration_times")
                continue
            return type_id, exp, kind
        raise ValueError(
            f"{pair}: expiración {duration} no disponible en la grilla de IQ"
        )

    def get_positions(self, timeout: int = 10) -> list[dict]:
        self._positions_data = None
        self._positions_event.clear()
        self._send("sendMessage", {
            "name": "portfolio.get-history-positions",
            "version": "2.0",
            "body": {
                "user_id": int(self.user_id),
                "user_balance_id": int(self.balance_id),
                "instrument_types": ["turbo-option"],
                "offset": 0,
                "limit": 50,
            },
        })
        if not self._positions_event.wait(timeout):
            raise TimeoutError("timeout esperando history-positions")
        out = []
        data = self._positions_data or {}
        items = data.get("positions", []) if isinstance(data, dict) else data
        for item in items:
            option = item.get("raw_event", {}).get("binary_options_option_changed1", {})
            if option:
                out.append(option)
        return out

    # --------------------------------------------------------------- trading

    def buy(self, pair: str, side: str, amount: float, duration: str) -> tuple[bool, str | None]:
        if side.lower() not in ("call", "put"):
            return False, f"dirección inválida: {side}"
        try:
            option_type_id, exp, kind = self.resolve_expiration(pair, duration)
        except (ValueError, TimeoutError) as e:
            logger.warning("orden rechazada: %s", e)
            return False, str(e)
        try:
            payout = self._payout_for(pair, kind)
        except Exception as e:
            logger.warning("payout no disponible para %s: %s", pair, e)
            return False, f"payout no disponible: {e}"
        if payout is None:
            return False, f"payout no disponible para {pair}"
        req_id = str(random.randint(0, 10000))
        self._subscribe_positions()
        body = {
            "option_type_id": option_type_id,
            "active_id": self._active_id(pair),
            "user_balance_id": int(self.balance_id),
            "price": float(amount),
            "direction": side.lower(),
            "expired": int(exp),
            "profit_percent": round(payout * 100),
        }
        self._buy_result = None
        self._buy_option = {}
        self._send("sendMessage", {
            "name": "binary-options.open-option",
            "version": "2.0",
            "body": body,
        }, request_id=req_id)
        start = time.time()
        while time.time() - start < 10:
            option = self._buy_option.get(req_id, {})
            if "message" in option:
                return False, option["message"]
            if self._buy_result is not None and "id" in option:
                return True, str(option["id"])
            time.sleep(0.05)
        logger.warning("buy timeout para %s", pair)
        return False, None

    def check_result(self, order_id: str, timeout: float = 180.0) -> tuple[str, float]:
        start = time.time()
        while time.time() - start < timeout:
            x = self._closed.get(order_id)
            if x is not None:
                result = x["result"]
                pnl = (
                    0.0 if result in ("tie", "equal") else
                    float(x["amount"]) * -1 if result in ("lose", "loose") else
                    float(x["profit_amount"])
                )
                return result, pnl
            time.sleep(0.5)
        raise TimeoutError(f"timeout esperando cierre de la opción {order_id}")

    # -------------------------------------------------------------- balance

    def get_balances(self, timeout: int = 10) -> list[dict]:
        self._balances_data = None
        self._balances_event.clear()
        self._send("sendMessage", {
            "name": "internal-billing.get-balances",
            "version": "1.0",
            "body": {"types_ids": [1, 4, 2], "tournaments_statuses_ids": [3, 2]},
        })
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
