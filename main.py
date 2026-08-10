from bot.broker.factory import build_broker
from bot.db import log_trade
from bot.menu import (
    choose_account_type,
    choose_assets,
    choose_broker,
    choose_market,
    choose_stake,
    choose_timeframe,
)
from bot.session import run_session


def main():
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
        run_session(broker, assets, timeframe, stake, market_type=market, on_trade=on_trade)
    except KeyboardInterrupt:
        print("\nSesión interrumpida.")
    finally:
        broker.disconnect()


if __name__ == "__main__":
    main()
