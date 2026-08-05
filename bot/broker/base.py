"""Interfaz abstracta BrokerClient. Núcleo del bot nunca importa un broker concreto.

Un BrokerClient implementa el ciclo mínimo sobre un bróker: velas, órdenes, saldo.
Cualquier bróker (Exnova, Mock, ...) se conecta implementando esta interfaz.
"""

from abc import ABC, abstractmethod
from typing import Any


class BrokerClient(ABC):
    """Contrato mínimo desacoplado de cualquier bróker específico."""

    @abstractmethod
    def get_candles(self, pair: str, timeframe: str, count: int) -> list[dict[str, Any]]:
        """Devuelve velas históricas del par como lista de dicts."""

    @abstractmethod
    def get_available_assets(self) -> list[str]:
        """Devuelve los activos actualmente abiertos en el mercado activo."""

    @abstractmethod
    def place_order(self, pair: str, side: str, amount: float, duration: str) -> Any:
        """Envía una orden. Devuelve identificador de la operación o None si falla."""

    @abstractmethod
    def get_balance(self) -> float:
        """Devuelve el balance disponible en la cuenta."""