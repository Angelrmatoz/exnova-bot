"""ExnovaAdapter: BrokerClient concreto sobre ExnovaWSClient.

El núcleo del bot solo conoce BrokerClient; jamás importa exnovaapi directamente.
Cambiar de bróker = nuevo adapter.
"""

from bot.broker.base import BrokerClient
from bot.broker.exnova_ws import ExnovaWSClient


class ExnovaAdapter(BrokerClient):
    def __init__(self, email: str, password: str, account_type: str = "PRACTICE", market_type: str = "NORMAL"):
        self._client = ExnovaWSClient(email, password, account_type=account_type)
        self.account_type = account_type.upper()
        self.market_type = market_type.upper()

    def connect(self) -> tuple[bool, str | None]:
        return self._client.connect()

    def connect_2fa(self, sms_code: str) -> tuple[bool, str | None]:
        return self._client.connect_2fa(sms_code)

    def check_connect(self) -> bool:
        return self._client.check_connect()

    def disconnect(self) -> None:
        self._client.close()

    def get_candles(
        self, pair: str, timeframe: str, count: int, endtime: int | None = None
    ) -> list[dict]:
        return self._client.get_candles(pair, timeframe, count, endtime)

    def get_available_assets(self) -> list[str]:
        assets = self._client.get_available_assets()
        if self.market_type == "OTC":
            return sorted(a for a in assets if a.endswith("-OTC"))
        return sorted(a for a in assets if not a.endswith("-OTC"))

    def place_order(self, pair: str, side: str, amount: float, duration: str) -> str | None:
        ok, order_id = self._client.buy(pair, side, amount, duration)
        return order_id if ok else None

    def check_result(self, order_id: str) -> tuple[str, float]:
        # 420s cubre expiraciones de hasta 5m + retardo de entrada (el loop
        # retorna en cuanto llega el resultado; solo alarga el peor caso).
        return self._client.check_result(order_id, timeout=420.0)

    def get_balance(self) -> float:
        return self._client.get_balance()

    def get_payout(self, pair: str) -> float | None:
        """Payout del activo: fracción ganancia (0..1). None si no existe."""
        return self._client.get_payout(pair)