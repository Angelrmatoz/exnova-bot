"""Descarga 10,000+ velas históricas de un activo y las guarda en data/.

Uso:
    uv run python -m bot.scripts.fetch_history EURUSD 1m 10000
        uv run python -m bot.scripts.fetch_history EURUSD 1m 10000 --out data/hist/EURUSD.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from bot.broker.exnova import ExnovaAdapter
from bot.config import exnova_credentials
from bot.history import fetch_candle_history, save_history_csv

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser(description="Descarga historial de velas.")
    parser.add_argument("pair", help="Activo, ej: EURUSD")
    parser.add_argument("timeframe", help="Temporalidad, ej: 1m, 5m, 1h")
    parser.add_argument("target", type=int, help="Velas a descargar (10_000+)")
    parser.add_argument("--out", default=None, help="Ruta CSV de salida")
    parser.add_argument("--market", default="NORMAL", choices=["NORMAL", "OTC"], help="Tipo de mercado (NORMAL u OTC)")
    args = parser.parse_args()

    creds = exnova_credentials()
    broker = ExnovaAdapter(creds["email"], creds["password"], creds["account_type"], market_type=args.market)
    ok, reason = broker.connect()
    if not ok:
        print(f"Error conectando: {reason}")
        return 1

    getter = lambda count, cut: broker.get_candles(args.pair, args.timeframe, count, cut)  # noqa: E731
    try:
        print(f"Descargando {args.target} velas de {args.pair} ({args.timeframe})...")
        rows = fetch_candle_history(getter, args.target)
    finally:
        broker.disconnect()

    out = Path(args.out) if args.out else ROOT / "data" / args.timeframe / f"{args.pair}.csv"
    save_history_csv(rows, out)
    print(f"Guardadas {len(rows)} velas en {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())