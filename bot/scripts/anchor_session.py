"""Sesión de anclaje OTC en bucle diario, con kill-switch propio.

uv run python -m bot.scripts.anchor_session --stake 1000
uv run python -m bot.scripts.anchor_session --stake 1000 --pairs AUDUSD,EURUSD --rounds 2
"""

import argparse

from bot.anchor import ANCHORS, MARKET_TYPE, anchor_alive, run_anchors
from bot.broker.factory import build_broker
from bot.config import exnova_credentials
from bot.db import get_win_rate, log_trade


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--broker", default="exnova")
    ap.add_argument("--account", default="PRACTICE")
    ap.add_argument("--stake", type=float, default=1000.0)
    ap.add_argument("--pairs", default="")
    ap.add_argument("--rounds", type=int, default=1)
    args = ap.parse_args()

    pairs = [p.strip().upper() for p in args.pairs.split(",") if p.strip()] or None
    for base in pairs or ANCHORS:
        if base not in ANCHORS:
            print(f"Par sin anclaje validado: {base}")
            return 2

    rate, resolved = get_win_rate(MARKET_TYPE)
    if not anchor_alive(rate, resolved):
        print(
            f"Anclaje sin edge: {rate:.1%} en {resolved} operaciones (mínimo 90%). No se opera."
        )
        return 1

    broker = build_broker(args.broker, "NORMAL", args.account)
    ok, reason = broker.connect()
    if not ok:
        print(f"Error de conexión: {reason}")
        return 3

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
        run_anchors(broker, args.stake, on_trade=on_trade, pairs=pairs, rounds=args.rounds)
    finally:
        broker.disconnect()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
