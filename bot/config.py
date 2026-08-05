"""Config desde variables de entorno / .env. Credenciales jamás hardcodeadas."""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

_EXNOVA = {
    "email": os.getenv("EXNOVA_EMAIL", ""),
    "password": os.getenv("EXNOVA_PASSWORD", ""),
    "account_type": os.getenv("EXNOVA_ACCOUNT_TYPE", "PRACTICE"),
}

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

DATA_DIR = Path(os.getenv("DATA_DIR", "data"))


def exnova_credentials() -> dict[str, str]:
    """Valida y devuelve credenciales Exnova. Falla rápido si faltan."""
    missing = [k for k, v in _EXNOVA.items() if not v]
    if missing:
        raise RuntimeError(f"Faltan credenciales {missing} en .env")
    return dict(_EXNOVA)