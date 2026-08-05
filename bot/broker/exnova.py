"""ExnovaAdapter: primer BrokerClient concreto. Envuelve la librería exnovaapi.

El núcleo del bot solo conoce BrokerClient; jamás importa exnovaapi directamente.
Cambiar de bróker = nuevo adapter.
"""

import sys
from pathlib import Path

from bot.broker.base import BrokerClient

_VENDOR_DIR = Path(__file__).resolve().parents[1] / "vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))


class ExnovaAdapter(BrokerClient):
    def __init__(self, email: str, password: str, account_type: str = "PRACTICE", market_type: str = "NORMAL"):
        # import tardío: mantener exnovaapi opt-in, no romper import del núcleo
        from exnovaapi.stable_api import Exnova

        self._api = Exnova(email, password)
        self.account_type = account_type.upper()
        self.market_type = market_type.upper()

    def connect(self) -> tuple[bool, str | None]:
        ok, reason = self._api.connect()
        if ok:
            self._api.change_balance(self.account_type)
        return ok, reason

    def connect_2fa(self, sms_code: str) -> tuple[bool, str | None]:
        return self._api.connect_2fa(sms_code)

    def check_connect(self) -> bool:
        return self._api.check_connect()

    def disconnect(self) -> None:
        self._api.api.close()

    def get_candles(
        self, pair: str, timeframe: str, count: int, endtime: int | None = None
    ) -> list[dict]:
        interval = self._to_seconds(timeframe)
        endtime = endtime if endtime is not None else self._server_timestamp()
        raw = self._api.get_candles(pair, interval, count, endtime) or []
        return [
            {
                "time": c["from"],
                "open": c["open"],
                "close": c["close"],
                "high": c["max"],
                "low": c["min"],
            }
            for c in raw
        ]

    def get_available_assets(self) -> list[str]:
        data = self._api.get_all_init_v2() or {}
        assets = set()
        for option in ("binary", "turbo"):
            for active in data.get(option, {}).get("actives", {}).values():
                name = str(active["name"]).split(".")[1]
                if not (active.get("enabled") and not active.get("is_suspended")):
                    continue
                if self.market_type == "OTC":
                    if name.endswith("-OTC"):
                        assets.add(name)
                elif not name.endswith("-OTC"):
                    assets.add(name)
        return sorted(assets)

    def place_order(self, pair: str, side: str, amount: float, duration: str) -> str | None:
        minutes = self._to_minutes(duration)
        status, order_id = self._api.buy(amount, pair, side.lower(), minutes)
        return order_id if status else None

    def check_result(self, order_id: str) -> tuple[str, float]:
        win, pnl = self._api.check_win_v4(order_id)
        return win, pnl

    def get_balance(self) -> float:
        return self._api.get_balance()

    def get_payout(self, pair: str) -> float:
        """Payout del activo: fracción ganancia (0..1). None si no existe."""
        return self._api.get_all_profit().get(pair, {}).get("turbo")

    def _server_timestamp(self) -> int:
        return self._api.get_server_timestamp()

    @staticmethod
    def _to_seconds(timeframe: str) -> int:
        unit = timeframe[-1]
        value = int(timeframe[:-1])
        return {"s": 1, "m": 60, "h": 3600}[unit] * value

    @staticmethod
    def _to_minutes(duration: str) -> int:
        seconds = ExnovaAdapter._to_seconds(duration)
        return max(1, round(seconds / 60))