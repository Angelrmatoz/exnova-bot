import subprocess
import sys
import time
import webbrowser
from pathlib import Path

from bot.broker.factory import build_broker
from bot.db import log_trade
from bot.menu import (
    choose_account_type,
    choose_after_session,
    choose_assets,
    choose_broker,
    choose_market,
    choose_stake,
    choose_timeframe,
)
from bot.session import run_session


def start_dashboard(port: int = 8501) -> None:
    """Lanza el dashboard Streamlit en segundo plano y muestra la URL."""
    dash = Path(__file__).resolve().parent / "bot" / "scripts" / "dashboard.py"
    try:
        subprocess.Popen(
            [sys.executable, "-m", "streamlit", "run", str(dash),
             "--server.headless", "true", "--server.port", str(port)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        print("No se pudo lanzar Streamlit (¿uv sync?). Dashboard manual: uv run streamlit run bot/scripts/dashboard.py")
        return
    url = f"http://localhost:{port}"
    print(f"Dashboard: {url}")
    webbrowser.open(url)


def main():
    start_dashboard()
    name = choose_broker()
    if not name:
        return
    market = choose_market()
    account = choose_account_type()
    timeframe = choose_timeframe()
    stake = choose_stake()
    broker = build_broker(name, market, account)

    print(f"Conectando a {name} ({account})...")
    ok, reason = broker.connect()
    if not ok:
        print(f"Error de conexión: {reason}. Revisa credenciales o activa 2FA.")
        return
    print(f"Conectado. Balance: {broker.get_balance():.2f}\n")

    assets = choose_assets(broker)
    if not assets:
        broker.disconnect()
        return

    def on_trade(**kw):
        log_trade(
            pair=kw["pair"],
            market_type=kw["market_type"],
            signal=kw["signal"],
            result=kw["result"],
            pnl=kw["pnl"],
            confidence=kw["confidence"],
            gate_passed=kw["gate_passed"],
        )

    try:
        while True:
            run_session(broker, assets, timeframe, stake, market_type=market, on_trade=on_trade,
                        expiry="5m" if timeframe == "1m" else None)
            action = choose_after_session()
            if action == "exit":
                break
            if action == "wait1h":
                print("Esperando 1 hora antes de la siguiente operación...")
                time.sleep(3600)
            print("Re-analizando el mercado...")
    except KeyboardInterrupt:
        print("\nSesión interrumpida.")
    finally:
        broker.disconnect()


if __name__ == "__main__":
    main()
