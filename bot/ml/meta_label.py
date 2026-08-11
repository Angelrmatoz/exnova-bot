"""Meta-labeling: predice si la SEÑAL BASE acertará, no la dirección.

La señal base es el momentum de la vela cerrada (close>open => CALL),
operada en t y resuelta con la vela t+1. El meta-modelo (XGBoost,
walk-forward) aprende P(la señal base acierta) desde las features de t;
solo se opera cuando esa proba supera un umbral.

Reporta por umbral: % de velas que califican, win rate del subconjunto
filtrado, expectancy con --payout, y lo compara contra operar todo.

Uso:
    uv run python -m bot.ml.meta_label --in data/5m/EURUSD.features.csv --payout 0.80
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import TimeSeriesSplit
from xgboost import XGBClassifier

from bot.ml.features import load_csv
from bot.ml.train import feature_columns

ROOT = Path(__file__).resolve().parents[2]

THRESHOLDS = [0.50, 0.52, 0.54, 0.56, 0.58, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90]


def build_meta_target(df: pd.DataFrame) -> pd.Series:
    """1 si la señal base de la vela t acierta sobre la vela t+1, 0 si pierde.

    Señal base: CALL si close[t] > open[t], PUT si no.
    Acierto: CALL gana si close[t+1] > close[t]; PUT si close[t+1] < close[t].
    """
    side_call = df["close"] > df["open"]
    up_next = df["close"].shift(-1) > df["close"]
    return (side_call == up_next).astype(int)


def meta_oos_proba(df: pd.DataFrame, n_splits: int = 5, train_window: int | None = 10000) -> tuple[pd.Series, pd.Series]:
    """Proba OOS de que la señal base acierte, por walk-forward."""
    cols = feature_columns(df)
    y = build_meta_target(df)
    y = y.loc[df.index].dropna()
    X = df.loc[y.index, cols].dropna()
    y = y.loc[X.index]

    tss = TimeSeriesSplit(n_splits=n_splits)
    proba_parts: list[pd.Series] = []
    y_parts: list[pd.Series] = []
    for train_i, test_i in tss.split(X):
        if train_window is not None:
            train_i = train_i[-train_window:]
        model = XGBClassifier(n_estimators=300, learning_rate=0.05, eval_metric="logloss", verbosity=0)
        model.fit(X.iloc[train_i], y.iloc[train_i])
        proba_parts.append(pd.Series(model.predict_proba(X.iloc[test_i])[:, 1], index=y.iloc[test_i].index))
        y_parts.append(y.iloc[test_i])

    return pd.concat(y_parts), pd.concat(proba_parts)


def _expectancy(win: float, payout: float) -> float:
    return win * payout - (1 - win)


def main() -> int:
    parser = argparse.ArgumentParser(description="Meta-labeling: filtra señales base por confianza ML.")
    parser.add_argument("--in", dest="src", default=None, help="CSV de features de entrada")
    parser.add_argument("--payout", type=float, default=0.80, help="Payout por ganar (0.80 = 80%%)")
    parser.add_argument("--splits", type=int, default=5, help="Splits walk-forward")
    args = parser.parse_args()

    src = Path(args.src) if args.src else ROOT / "data" / "5m" / "EURUSD.features.csv"
    df = load_csv(src)
    if "y" in df.columns:
        df = df.drop(columns=["y"])

    y_oos, proba_oos = meta_oos_proba(df, n_splits=args.splits)

    base_win = y_oos.mean()
    base_ops = len(y_oos)
    auc = roc_auc_score(y_oos, proba_oos)
    print(f"Datos: {src} | Velas OOS: {base_ops:,} | Señal base (operar todo): win {base_win:.2%}")
    print(f"Meta-modelo: AUC {auc:.4f} (0.50 = sin poder discriminatorio)")
    print(f"Payout {args.payout:.0%} => breakeven {1 / (1 + args.payout):.1%}; "
          f"expectancy base: {_expectancy(base_win, args.payout):+.3f}\n")
    print(f"{'Umbral':>6}{'ops':>9}{'% del set':>10}{'win%':>8}{'expect':>9}{'|p-0.5|':>9}")

    for t in THRESHOLDS:
        mask = proba_oos >= t
        n = int(mask.sum())
        if n < 20:
            print(f"{t:>6.2f}{n:>9,}{n / base_ops:>9.1%}{'--':>8}")
            continue
        wr = y_oos[mask].mean()
        exp = _expectancy(wr, args.payout)
        spread = float((proba_oos[mask] - 0.5).abs().mean())
        print(f"{t:>6.2f}{n:>9,}{n / base_ops:>9.1%}{wr:>7.2%}{exp:>+9.3f}{spread:>8.3f}")

    low_mask = proba_oos <= 0.40
    n_low = int(low_mask.sum())
    if n_low >= 20:
        wr = y_oos[low_mask].mean()
        print(f"\nLado bajo proba<=0.40 (contraria del meta-modelo): {n_low:,} ops, win {wr:.2%}, "
              f"expect {_expectancy(wr, args.payout):+.3f}")

    return 0


if __name__ == "__main__":
    sys.exit(main())