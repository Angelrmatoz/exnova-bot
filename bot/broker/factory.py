"""Factory de BrokerClient: construye el adaptador del operador elegido.

El CLI elige operador (configurado_brokers) y este módulo devuelve el
BrokerClient concreto sin que el núcleo conozca el adaptador.
"""

from bot.broker.base import BrokerClient
from bot.broker.exnova import ExnovaAdapter
from bot.broker.iqoption import IqOptionAdapter
from bot.config import exnova_credentials, iqoption_credentials


def build_broker(name: str, market_type: str = "NORMAL", account_type: str | None = None) -> BrokerClient:
    """Crea el BrokerClient del operador `name` (exnova | iqoption).

    `account_type` (PRACTICE/REAL) lo elige el usuario en el CLI; si es None
    usa el default de .env.
    """
    if name == "exnova":
        c = exnova_credentials()
        at = account_type or c["account_type"]
        return ExnovaAdapter(c["email"], c["password"], at, market_type)
    if name == "iqoption":
        c = iqoption_credentials()
        at = account_type or c["account_type"]
        return IqOptionAdapter(c["ssid"], at)
    raise ValueError(f"operador desconocido: {name}")
