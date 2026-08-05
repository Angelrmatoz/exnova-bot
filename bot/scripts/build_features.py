"""Genera features técnicos a partir de CSV de velas y los guarda.

Uso:
    uv run python -m bot.scripts.build_features --in data/5m/EURUSD.csv --out data/5m/EURUSD.features.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from bot.ml.features import FEATURE_COLUMNS, build_features, load_csv

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser(description="Genera features técnicos desde velas CSV.")
    parser.add_argument("--in", dest="src", default=None, help="CSV de velas de entrada")
    parser.add_argument("--out", default=None, help="CSV de salida con features")
    args = parser.parse_args()

    src = Path(args.src) if args.src else ROOT / "data" / "5m" / "EURUSD.csv"
    out = Path(args.out) if args.out else src.with_name(src.stem + ".features.csv")

    df = load_csv(src)
    feats = build_features(df)

    keep = ["time", "open", "close", "high", "low"] + FEATURE_COLUMNS
    feats[keep].to_csv(out, index=False)

    valid = feats[FEATURE_COLUMNS].dropna()
    print(f"Velas: {len(df)} | Con features válidas: {len(valid)}")
    print(f"Guardado: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())