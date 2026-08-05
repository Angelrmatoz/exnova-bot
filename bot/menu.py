"""Menú interactivo de inicio: mercado (Normal/OTC) + selección de divisas.

Desacoplado del bróker: recibe un BrokerClient y usa solo su interfaz.
"""

from bot.broker.base import BrokerClient


def choose_market() -> str:
    print("\n=== Exnova Bot ===")
    print("[1] Mercado Real (Normal)  — Lun-Vie, activa Capa 1 (Gemini)")
    print("[2] Mercado OTC            — Activos simulados, sin noticias")
    while True:
        opt = input("Selecciona mercado [1/2]: ").strip()
        if opt == "1":
            print("Mercado: NORMAL\n")
            return "NORMAL"
        if opt == "2":
            print("Mercado: OTC\n")
            return "OTC"
        print("Opción inválida, intenta de nuevo.")


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
        raw = input(
            "Selecciona (n)úmeros separados por coma, o 'all' para todas: "
        ).strip().lower()
        if raw == "all":
            return available
        try:
            idxs = [int(x) for x in raw.replace(" ", "").split(",") if x]
            picked = [available[i - 1] for i in idxs]
            if picked:
                print(f"Monitorizando: {', '.join(picked)}\n")
                return picked
        except (ValueError, IndexError):
            pass
        print("Selección inválida.")