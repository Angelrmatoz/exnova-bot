"""Entrenamiento XGBoost con validación walk-forward (sin data leakage).

Uso:
    uv run python -m bot.ml.train --in data/5m/EURUSD.features.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
from sklearn.metrics import accuracy_score, log_loss
from sklearn.model_selection import TimeSeriesSplit
from xgboost import XGBClassifier

from bot.ml.features import FEATURE_COLUMNS, load_csv
from bot.ml.multi_tf import MTL_COLUMNS

ROOT = Path(__file__).resolve().parents[2]


def feature_columns(df: pd.DataFrame) -> list[str]:
    """Columnas de features presentes en el CSV (soporta base y MTLF)."""
    return [c for c in MTL_COLUMNS if c in df.columns] or [c for c in FEATURE_COLUMNS if c in df.columns]


def build_target(df: pd.DataFrame) -> pd.Series:
    """Dirección de la vela t+1: 1 si sube, 0 si baja."""
    return (df["close"].shift(-1) > df["close"]).astype(int)


def walk_forward(df: pd.DataFrame, n_splits: int = 5) -> tuple[list[float], list[float], pd.Series, pd.Series]:
    cols = feature_columns(df)
    X = df[cols].dropna()
    y = build_target(df).loc[X.index].dropna()
    X = X.loc[y.index]

    tss = TimeSeriesSplit(n_splits=n_splits)
    accs, losses = [], []
    y_oos, proba_oos = [], []
    for train_i, test_i in tss.split(X):
        model = XGBClassifier(n_estimators=300, learning_rate=0.05, eval_metric="logloss", verbosity=0)
        model.fit(X.iloc[train_i], y.iloc[train_i])
        proba = model.predict_proba(X.iloc[test_i])[:, 1]
        accs.append(accuracy_score(y.iloc[test_i], proba > 0.5))
        losses.append(log_loss(y.iloc[test_i], proba))
        y_oos.append(y.iloc[test_i])
        proba_oos.append(pd.Series(proba, index=y.iloc[test_i].index))

    return accs, losses, pd.concat(y_oos), pd.concat(proba_oos)


def main() -> int:
    parser = argparse.ArgumentParser(description="Entrena XGBoost con validación walk-forward.")
    parser.add_argument("--in", dest="src", default=None, help="CSV de features de entrada")
    parser.add_argument("--splits", type=int, default=5, help="Número de splits walk-forward")
    args = parser.parse_args()

    src = Path(args.src) if args.src else ROOT / "data" / "5m" / "EURUSD.features.csv"
    df = load_csv(src)

    accs, losses, y = walk_forward(df, n_splits=args.splits)

    print(f"Datos: {src} | Filas válidas: {len(y)}")
    print(f"Clase 1 (sube): {y.mean():.1%}")
    for i, (acc, loss) in enumerate(zip(accs, losses), 1):
        print(f"  Fold {i}: accuracy={acc:.4f} logloss={loss:.4f}")
    print(f"Media: accuracy={sum(accs) / len(accs):.4f} logloss={sum(losses) / len(losses):.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
