"""Menú interactivo de inicio: mercado (Normal/OTC) + selección de divisas.

Desacoplado del bróker: recibe un BrokerClient y usa solo su interfaz.
"""

import re

from bot.broker.base import BrokerClient
from bot.config import configured_brokers

_LABELS = {"exnova": "Exnova", "iqoption": "IQ Option"}


def choose_broker() -> str:
    """Primer paso del CLI: elegir operador entre los configurados en .env."""
    brokers = configured_brokers()
    if not brokers:
        print("No hay operadores configurados en .env. Revisa credenciales.")
        return ""
    print("\n=== Bot de Opciones Binarias ===")
    print("Operadores configurados:")
    for i, name in enumerate(brokers, 1):
        print(f"[{i}] {_LABELS.get(name, name)}")
    while True:
        opt = input(f"Selecciona operador [1-{len(brokers)}]: ").strip()
        try:
            return brokers[int(opt) - 1]
        except (ValueError, IndexError):
            print("Opción inválida, intenta de nuevo.")


def choose_market() -> str:
    print("\n=== Bot de Opciones Binarias ===")
    print("[1] Mercado Real (Normal)  — Lun-Vie")
    print("[2] Mercado OTC            — Activos simulados")
    while True:
        opt = input("Selecciona mercado [1/2]: ").strip()
        if opt == "1":
            print("Mercado: NORMAL\n")
            return "NORMAL"
        if opt == "2":
            print("Mercado: OTC\n")
            return "OTC"
        print("Opción inválida, intenta de nuevo.")


def choose_account_type() -> str:
    """Elección de cuenta: DEMO por defecto, REAL si el usuario lo pide."""
    print("\n=== Bot de Opciones Binarias ===")
    print("[1] Cuenta DEMO  (práctica, por defecto)")
    print("[2] Cuenta REAL (riesgo de capital real)")
    while True:
        opt = input("Selecciona cuenta [1/2]: ").strip()
        if opt in ("", "1"):
            return "PRACTICE"
        if opt == "2":
            return "REAL"
        print("Opción inválida, intenta de nuevo.")


def choose_timeframe(default: str = "5m") -> str:
    print("\n=== Bot de Opciones Binarias ===")
    print("[1] 1 minuto")
    print("[2] 5 minutos (por defecto)")
    while True:
        opt = input("Selecciona timeframe [1/2]: ").strip()
        if opt in ("", "2"):
            return "5m"
        if opt == "1":
            return "1m"
        print("Opción inválida, intenta de nuevo.")


def choose_stake(lo: float = 1.0, hi: float = 20000.0) -> float:
    """Monto por operación dentro de [lo, hi]. Números con punto decimal, sin comas."""
    print("\n=== Bot de Opciones Binarias ===")
    while True:
        raw = input(f"Monto por operación (de {lo:g} a {hi:g}, ej. 18370.45): ").strip()
        if re.fullmatch(r"\d+(\.\d+)?", raw):
            stake = float(raw)
            if lo <= stake <= hi:
                return stake
        print("Monto inválido, usa números con punto decimal (ej. 18370.45).")


def choose_assets(broker: BrokerClient) -> list[str]:
    print("Escaneando divisas abiertas...")
    available = broker.get_available_assets()
    if not available:
        print("Sin divisas abiertas en este mercado. Saliendo.")
        return []

    print(f"Divisas disponibles ({len(available)}):")
    for i, name in enumerate(available, 1):
        print(f"  [{i}] {name}")

    while True:
        raw = input("Selecciona una divisa [número]: ").strip()
        try:
            idx = int(raw)
            picked = available[idx - 1]
            print(f"Monitorizando: {picked}\n")
            return [picked]
        except (ValueError, IndexError):
            print("Selección inválida, elige un número de la lista.")