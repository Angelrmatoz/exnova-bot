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

_IQ_OPTION = {
    "ssid": os.getenv("IQ_OPTION_SSID", ""),
    "email": os.getenv("IQ_OPTION_EMAIL", ""),
    "password": os.getenv("IQ_OPTION_PASSWORD", ""),
    "account_type": os.getenv("IQ_OPTION_ACCOUNT_TYPE", "PRACTICE"),
}

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-lite")
GEMINI_MODEL_FALLBACK = os.getenv("GEMINI_MODEL_FALLBACK", "gemini-2.0-flash")
GEMINI_MODEL_FALLBACK_2 = os.getenv("GEMINI_MODEL_FALLBACK_2", "gemini-2.5-flash")

DATA_DIR = Path(os.getenv("DATA_DIR", "data"))


def exnova_credentials() -> dict[str, str]:
    """Valida y devuelve credenciales Exnova. Falla rápido si faltan."""
    missing = [k for k, v in _EXNOVA.items() if not v]
    if missing:
        raise RuntimeError(f"Faltan credenciales {missing} en .env")
    return dict(_EXNOVA)


def iqoption_credentials() -> dict[str, str]:
    """Valida y devuelve credenciales IQ Option. Solo el ssid es obligatorio
    (email/password se usan solo para renovar el ssid vía navegador)."""
    if not _IQ_OPTION["ssid"]:
        raise RuntimeError("Falta IQ_OPTION_SSID en .env")
    return dict(_IQ_OPTION)


def configured_brokers() -> list[str]:
    """Operadores con credenciales completas en .env, para el menú del CLI."""
    out = []
    if _EXNOVA["email"] and _EXNOVA["password"]:
        out.append("exnova")
    if _IQ_OPTION["ssid"]:
        out.append("iqoption")
    return out