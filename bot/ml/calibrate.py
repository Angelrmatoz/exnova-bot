"""Curva de calibración de probabilidades del modelo walk-forward.

Muestra el win rate real por 'bin' de confianza predicha y el Brier score.
El umbral de operación no se fija aquí: se decide con esta curva.

Uso:
    uv run python -m bot.ml.calibrate --in data/5m/EURUSD.features.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
from sklearn.calibration import calibration_curve
from sklearn.metrics import brier_score_loss

from bot.ml.features import load_csv
from bot.ml.train import walk_forward

ROOT = Path(__file__).resolve().parents[2]


def calibration_table(y_true: pd.Series, proba: pd.Series, n_bins: int = 10) -> pd.DataFrame:
    freq, pred = calibration_curve(y_true, proba, n_bins=n_bins, strategy="uniform")
    return pd.DataFrame({"bin_confianza_inf": pred, "win_rate_real": freq})


def main() -> int:
    parser = argparse.ArgumentParser(description="Genera curva de calibración walk-forward.")
    parser.add_argument("--in", dest="src", default=None, help="CSV de features de entrada")
    parser.add_argument("--bins", type=int, default=10, help="Número de bins de confianza")
    args = parser.parse_args()

    src = Path(args.src) if args.src else ROOT / "data" / "5m" / "EURUSD.features.csv"
    df = load_csv(src)

    _, _, y_oos, proba_oos = walk_forward(df)
    oos = pd.DataFrame({"y_true": y_oos, "y_prob": proba_oos})
    oos.to_csv(src.with_name(src.stem + ".oos.csv"), index=False)

    brier = brier_score_loss(y_oos, proba_oos)
    tab = calibration_table(y_oos, proba_oos, n_bins=args.bins)

    print(f"Datos OOS: {len(oos)} | Brier score: {brier:.4f}")
    print(f"{'conf_prom_bin':>13} | {'win_rate_real':>13}")
    for _, row in tab.iterrows():
        print(f"{row.bin_confianza_inf:13.3f} | {row.win_rate_real:13.3f}")
    print(f"OOS guardado: {oos_path(src)}")
    return 0


def oos_path(src: Path) -> Path:
    return src.with_name(src.stem + ".oos.csv")


if __name__ == "__main__":
    sys.exit(main())