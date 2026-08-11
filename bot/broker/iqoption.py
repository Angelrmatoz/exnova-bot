"""IqOptionAdapter: BrokerClient concreto sobre IqOptionWSClient.

IQ Option comparte la familia de protocolo Quadcode con Exnova; este adaptador
se conecta con un ssid (cookie de sesión del navegador). El núcleo del bot solo
conoce BrokerClient; cambiar de bróker = nuevo adapter.
"""

from bot.broker.base import BrokerClient
from bot.broker.iqoption_ws import IqOptionWSClient


class IqOptionAdapter(BrokerClient):
    def __init__(self, ssid: str, account_type: str = "PRACTICE"):
        self._client = IqOptionWSClient(ssid, account_type=account_type)
        self.account_type = account_type.upper()

    def connect(self) -> tuple[bool, str | None]:
        return self._client.connect()

    def check_connect(self) -> bool:
        return self._client.check_connect()

    def disconnect(self) -> None:
        self._client.close()

    def get_candles(
        self, pair: str, timeframe: str, count: int, endtime: int | None = None
    ) -> list[dict]:
        return self._client.get_candles(pair, timeframe, count, endtime)

    def get_available_assets(self) -> list[str]:
        return self._client.get_available_assets()

    def place_order(self, pair: str, side: str, amount: float, duration: str) -> str | None:
        ok, order_id = self._client.buy(pair, side, amount, duration)
        return order_id if ok else None

    def check_result(self, order_id: str) -> tuple[str, float]:
        return self._client.check_result(order_id)

    def get_balance(self) -> float:
        return self._client.get_balance()

    def get_payout(self, pair: str) -> float | None:
        """Payout del activo: fracción ganancia (0..1). None si no existe."""
        return self._client.get_payout(pair)
