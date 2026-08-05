"""Backtesting del modelo con curva de payout (simula una cuenta).

Usa las predicciones out-of-sample (walk-forward, sin leakage) y simula
operaciones sobre velas históricas: CALL si proba>=0.5, PUT si no.
Cada vela t+1 resuelve la operación: win => +payout*stake, loss => -stake.

Reporta por umbral de confianza: operaciones, win rate, expectancy,
PnL acumulado y máximo drawdown. Es la métrica que decide si hay edge
real antes de tocar DEMO.

Uso:
    uv run python -m bot.ml.backtest --in data/5m/EURUSD.features.csv --payout 0.80
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from bot.ml.features import load_csv
from bot.ml.train import walk_forward

ROOT = Path(__file__).resolve().parents[1]


def simulate(oos: pd.DataFrame, payout: float, threshold: float) -> dict:
    proba = oos["y_prob"].to_numpy()
    y = oos["y_true"].to_numpy()
    signal = (proba >= 0.5).astype(int)
    confidence = np.where(signal == 1, proba, 1 - proba)

    mask = confidence >= threshold
    n = int(mask.sum())
    if n == 0:
        return {"n": 0}

    win = (signal[mask] == y[mask]).astype(float)
    pnl = np.where(win == 1, payout, -1.0)
    cum = np.cumsum(pnl)
    peak = np.maximum.accumulate(cum)
    max_dd = float((peak - cum).max())

    return {
        "n": n,
        "win_rate": float(win.mean()),
        "expectancy": float(win.mean() * payout - (1 - win.mean())),
        "pnl": float(cum[-1]),
        "max_drawdown": max_dd,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Backtest con curva de payout.")
    parser.add_argument("--in", dest="src", default=None, help="CSV de features de entrada")
    parser.add_argument("--payout", type=float, default=0.80, help="Payout por operación ganadora (0.80 = 80%%)")
    parser.add_argument("--thresholds", default="0.5,0.55,0.6,0.65,0.7,0.8,0.9")
    args = parser.parse_args()

    src = Path(args.src) if args.src else ROOT / "data" / "5m" / "EURUSD.features.csv"
    df = load_csv(src)

    _, _, y_oos, proba_oos = walk_forward(df)
    oos = pd.DataFrame({"y_true": y_oos, "y_prob": proba_oos})

    thresholds = [float(t) for t in args.thresholds.split(",")]
    print(f"Payout: {args.payout:.0%} | Velas OOS: {len(oos)} | Stake = 1")
    print(f"{'umbral':>7} | {'ops':>5} | {'win%':>6} | {'expect':>7} | {'pnl':>7} | {'maxDD':>7}")
    for t in thresholds:
        r = simulate(oos, args.payout, t)
        if r["n"] == 0:
            print(f"{t:7.2f} |     0 |    - |      - |      - |      -")
            continue
        print(
            f"{t:7.2f} | {r['n']:5d} | {r['win_rate']:5.1%} | {r['expectancy']:+7.3f}"
            f" | {r['pnl']:+7.2f} | {r['max_drawdown']:7.2f}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())