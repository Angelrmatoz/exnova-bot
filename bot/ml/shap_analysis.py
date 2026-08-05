"""Importancia de features con SHAP (TreeExplainer) sobre el modelo final.

Entrena el modelo con todos los datos válidos y reporta contribución media
absoluta de cada feature al log-odds. No valida (eso es walk_forward);
solo explica qué usa el modelo.

Uso:
    uv run python -m bot.ml.shap_analysis --in data/5m/EURUSD.features.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import shap
from xgboost import XGBClassifier

from bot.ml.features import FEATURE_COLUMNS, load_csv
from bot.ml.train import build_target

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser(description="Shows SHAP feature importance.")
    parser.add_argument("--in", dest="src", default=None, help="CSV de features de entrada")
    args = parser.parse_args()

    src = Path(args.src) if args.src else ROOT / "data" / "5m" / "EURUSD.features.csv"
    df = load_csv(src)

    X = df[FEATURE_COLUMNS].dropna()
    y = build_target(df).loc[X.index].dropna()
    X = X.loc[y.index]

    model = XGBClassifier(n_estimators=300, learning_rate=0.05, eval_metric="logloss", verbosity=0)
    model.fit(X, y)

    explainer = shap.TreeExplainer(model)
    shap_values = explainer.shap_values(X)

    importance = pd.DataFrame(
        {"feature": FEATURE_COLUMNS, "mean_abs_shap": np.abs(shap_values).mean(axis=0)}
    ).sort_values("mean_abs_shap", ascending=False)

    out = src.with_name(src.stem + ".shap.csv")
    importance.to_csv(out, index=False)

    print(f"Medias |SHAP| (mayor = más impulso del modelo):")
    for _, row in importance.iterrows():
        print(f"  {row.feature:16s} {row.mean_abs_shap:.6f}")
    print(f"Guardado: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())