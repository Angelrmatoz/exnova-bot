"""Pool multi-par para entrenamiento conjunto, interleado por timestamp.

Concatena los CSV MTLF de varios pares, añade columna `pair`, ordena por
tiempo y calcula el target `y` por-par por separado (interleaved, el
shift debe respetar cada serie suya).

Uso:
    uv run python -m bot.ml.pool --pairs EURUSD,GBPUSD,USDJPY --out data/5m/pool.mtl.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from bot.ml.features import load_csv

ROOT = Path(__file__).resolve().parents[2]


def build_pool(pairs: list[str], root: Path = ROOT, horizon: int = 10) -> pd.DataFrame:
    frames = []
    for p in pairs:
        df = load_csv(root / "data" / "5m" / f"{p}.mtl.csv")
        df.insert(0, "pair", p)
        frames.append(df)
    pooled = pd.concat(frames, ignore_index=True).sort_values("time").reset_index(drop=True)
    grouped = pooled.groupby("pair", sort=False)
    y_a = grouped["close"].shift(-1 * horizon) > pooled["close"]
    pooled["y"] = y_a.astype(int)
    return pooled


def main() -> int:
    parser = argparse.ArgumentParser(description="Pool multi-par interleaved por tiempo.")
    parser.add_argument("--pairs", default="EURUSD,GBPUSD,USDJPY", help="Lista de pares separada por comas")
    parser.add_argument("--horizon", type=int, default=10, help="Pasos del target (por pares, por separado)")
    parser.add_argument("--out", default=None, help="CSV de salida")
    args = parser.parse_args()

    pairs = [p.upper() for p in args.pairs.split(",")]
    pooled = build_pool(pairs, horizon=args.horizon)
    out = Path(args.out) if args.out else ROOT / "data" / "5m" / "pool.mtl.csv"
    pooled.to_csv(out, index=False)
    print(f"Filas: {len(pooled)} | pares: {pairs} | horizon: {args.horizon}")
    print(f"Guardado: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
