"""Exporta el modelo final a .pkl y lo registra en la tabla model_versions.

Usa las métricas de validación walk-forward (train.walk_forward) para el
registro y luego entrena un modelo final con todos los datos válidos, que
será el que se use en inferencia (inference.py, Fase 2 serial).

Uso:
    uv run python -m bot.ml.export_model --in data/5m/EURUSD.features.csv --out models/eurusd_5m.pkl
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import joblib
from xgboost import XGBClassifier

from bot.db import register_model
from bot.ml.features import FEATURE_COLUMNS, load_csv
from bot.ml.train import build_target, walk_forward

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description="Exporta y registra modelo XGBoost.")
    parser.add_argument("--in", dest="src", default=None, help="CSV de features de entrada")
    parser.add_argument("--out", default=None, help="Ruta del .pkl de salida")
    args = parser.parse_args()

    src = Path(args.src) if args.src else ROOT / "data" / "5m" / "EURUSD.features.csv"
    out = Path(args.out) if args.out else ROOT / "models" / "eurusd_5m.pkl"

    df = load_csv(src)
    accs, losses, _, _ = walk_forward(df)
    val_accuracy = sum(accs) / len(accs)
    val_logloss = sum(losses) / len(losses)

    X = df[FEATURE_COLUMNS].dropna()
    y = build_target(df).loc[X.index].dropna()
    X = X.loc[y.index]

    model = XGBClassifier(n_estimators=300, learning_rate=0.05, eval_metric="logloss", verbosity=0)
    model.fit(X, y)

    out.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, out)

    model_id = register_model(
        val_accuracy=val_accuracy,
        val_logloss=val_logloss,
        feature_list=FEATURE_COLUMNS,
        notes=f"baseline 5m; walk-forward 5 splits; sin edge confirmado aun",
    )

    print(f"val_accuracy={val_accuracy:.4f} val_logloss={val_logloss:.4f}")
    print(f"Modelo guardado: {out}")
    print(f"Registrado en model_versions id={model_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())