"""Features multi-timeframe de tendencia (15m, 1h) derivadas de velas 5m.

Resamplea las velas 5m a TFs superiores y calcula indicadores de tendencia
en cada uno. Para evitar data leakage, en cada vela base t solo se usan
indicadores de velas superiores YA CERRADAS (cierre <= t), unidas con
merge_asof hacia atrás.

Genera un CSV base enriquecido listo para train.py/backtest.py.

Uso:
    uv run python -m bot.ml.multi_tf --in data/5m/EURUSD.csv --out data/5m/EURUSD.mtl.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
import ta

from bot.ml.features import FEATURE_COLUMNS, build_features, load_csv

ROOT = Path(__file__).resolve().parents[1]

HIGHER_TFS = ["15min", "1h"]


def trend_features_higher(df: pd.DataFrame, tf: str) -> pd.DataFrame:
    """Indicadores de tendencia de un TF superior, indexados por close (epoch).

    Devuelve filas por vela superior ya cerrada con su columna 'time_close'.
    """
    base = df.copy()
    base["dt"] = pd.to_datetime(base["time"], unit="s")
    base = base.set_index("dt")

    h = base.resample(tf).agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "time": "last"}
    ).dropna()

    close = h["close"]
    h["ema_21"] = ta.trend.EMAIndicator(close, window=21).ema_indicator()
    h["ema_50"] = ta.trend.EMAIndicator(close, window=50).ema_indicator()
    h["rsi_14"] = ta.momentum.RSIIndicator(close, window=14).rsi()
    h["macd_hist"] = ta.trend.MACD(close).macd_diff()

    h["trend_ma"] = (h["ema_21"] - h["ema_50"]) / h["ema_50"]
    h["dist_ma"] = (close - h["ema_50"]) / h["ema_50"]
    h["macd_hist_norm"] = h["macd_hist"] / close

    h["time_close"] = h["time"].astype("int64")
    keep = ["time_close", "trend_ma", "dist_ma", "rsi_14", "macd_hist_norm"]
    higher = h[keep].dropna().rename(columns={c: f"{c}_{tf}" for c in keep if c != "time_close"})
    return higher


def merge_higher(base: pd.DataFrame, higher: pd.DataFrame, tf: str) -> pd.DataFrame:
    """Une por asof: para cada vela base t, el último cierre superior <= t."""
    merged = pd.merge_asof(
        base.sort_values("time"),
        higher.sort_values("time_close"),
        left_on="time",
        right_on="time_close",
        direction="backward",
    )
    return merged.drop(columns=["time_close"])


def build_mtl_features(df: pd.DataFrame) -> pd.DataFrame:
    out = build_features(df)
    for tf in HIGHER_TFS:
        higher = trend_features_higher(df, tf)
        out = merge_higher(out, higher, tf)
    return out


MTL_COLUMNS = (
    FEATURE_COLUMNS
    + [c for tf in HIGHER_TFS for c in (
        f"trend_ma_{tf}", f"dist_ma_{tf}", f"rsi_14_{tf}", f"macd_hist_norm_{tf}",
    )]
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Genera features multi-timeframe de tendencia.")
    parser.add_argument("--in", dest="src", default=None, help="CSV de velas 5m de entrada")
    parser.add_argument("--out", default=None, help="CSV de salida con features MTLF")
    args = parser.parse_args()

    src = Path(args.src) if args.src else ROOT / "data" / "5m" / "EURUSD.csv"
    out = Path(args.out) if args.out else src.with_name(src.stem + ".mtl.csv")

    df = load_csv(src)
    mtl = build_mtl_features(df)

    keep = ["time", "open", "close", "high", "low"] + MTL_COLUMNS
    mtl[keep].to_csv(out, index=False)
    print(f"Velas base: {len(df)} | Columnas MTLF: {len(MTL_COLUMNS)}")
    print(f"Guardado: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())