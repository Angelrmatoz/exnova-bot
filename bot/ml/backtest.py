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
    parser.add_argument(
        "--atr-gate",
        type=float,
        default=None,
        help="Operar solo si atr_14 está sobre este percentil rodante (0.0-1.0). Test de régimen de volatilidad.",
    )
    parser.add_argument("--atr-win", type=int, default=500, help="Ventana del percentil rodante de ATR")
    parser.add_argument("--rows", type=int, default=None, help="Usar solo las últimas N velas (regimes no estacionarios)")
    parser.add_argument(
        "--train-window",
        type=int,
        default=None,
        help="Entrenar cada fold solo con las últimas N velas (walk-forward rodante, anti-snooping)",
    )
    parser.add_argument(
        "--horizon",
        type=int,
        default=1,
        help="Target a N velas adelante (1=5min, 3=15min). Opciones con expiración más larga.",
    )
    parser.add_argument(
        "--embargo",
        type=int,
        default=0,
        help="Filas purgadas al final del train fold (evita que el target toque el test).",
    )
    parser.add_argument("--by-pair", action="store_true", help="Desglosar resultados por par (CSV pool multi-par)")
    args = parser.parse_args()

    src = Path(args.src) if args.src else ROOT / "data" / "5m" / "EURUSD.features.csv"
    df = load_csv(src)
    if args.rows and len(df) > args.rows:
        df = df.tail(args.rows).reset_index(drop=True)

    _, _, y_oos, proba_oos = walk_forward(
        df, train_window=args.train_window, horizon=args.horizon, embargo=args.embargo
    )
    oos = pd.DataFrame({"y_true": y_oos, "y_prob": proba_oos})
    if args.atr_gate is not None:
        if "atr_14" not in df:
            print("El CSV no tiene atr_14; --atr-gate requiere features")
            return 1
        atr = df["atr_14"].dropna()
        pct = atr / atr.rolling(args.atr_win, min_periods=args.atr_win).mean()
        oos = oos.join(pct.rename("atr_pct").to_frame()).dropna(subset=["atr_pct"])
        oos = oos[oos["atr_pct"] >= args.atr_gate]

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

    if args.by_pair:
        if "pair" not in df:
            print("--by-pair requiere CSV pool con columna 'pair'")
            return 1
        oos = oos.join(df[["pair"]].loc[oos.index])
        print(f"\n{'umbral':>7} | {'par':>8} | {'ops':>5} | {'win%':>6} | {'expect':>7}")
        for t in thresholds:
            for pair, g in oos.groupby("pair", sort=False):
                r = simulate(g, args.payout, t)
                if r["n"] == 0:
                    continue
                print(f"{t:7.2f} | {pair:>8} | {r['n']:5d} | {r['win_rate']:5.1%} | {r['expectancy']:+7.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())