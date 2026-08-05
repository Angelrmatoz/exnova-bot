"""Ingeniería de features técnicos para el modelo XGBoost.

Recibe velas OHLC (como las descarga fetch_history) y devuelve el mismo
DataFrame enriquecido con indicadores calculados con la librería `ta`
(sustituto de pandas-ta, que está abandonado y no soporta Python 3.14).

Cada fila t queda lista para predecir la dirección de la vela t+1:
el target se construye en la tarea de entrenamiento, no aquí.
"""

from __future__ import annotations

import pandas as pd
import ta


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Añade indicadores técnicos y features derivadas a un DF de velas OHLC.

    Requiere columnas: time (epoch seg), open, close, high, low.
    Devuelve una copia con columnas nuevas; las filas sin historia suficiente
    (periodos de warm-up de los indicadores) quedan con NaN.
    """
    out = df.copy().sort_values("time").reset_index(drop=True)
    close, high, low = out["close"], out["high"], out["low"]

    # Indicadores de momento y tendencia
    out["rsi_14"] = ta.momentum.RSIIndicator(close, window=14).rsi()
    out["willr_14"] = ta.momentum.WilliamsRIndicator(high, low, close, lbp=14).williams_r()
    out["ema_9"] = ta.trend.EMAIndicator(close, window=9).ema_indicator()
    out["ema_21"] = ta.trend.EMAIndicator(close, window=21).ema_indicator()
    out["ema_50"] = ta.trend.EMAIndicator(close, window=50).ema_indicator()
    out["macd"] = ta.trend.MACD(close).macd()
    out["macd_signal"] = ta.trend.MACD(close).macd_signal()
    out["macd_hist"] = ta.trend.MACD(close).macd_diff()
    out["atr_14"] = ta.volatility.AverageTrueRange(high, low, close, window=14).average_true_range()

    # Features derivadas sin estados: rentabilidades y rango relativo
    out["ret_1"] = close.pct_change(1)
    out["ret_5"] = close.pct_change(5)
    out["ret_10"] = close.pct_change(10)
    out["range_pct"] = (high - low) / close
    out["body_pct"] = (close - out["open"]) / close
    out["upper_wick_pct"] = (high - close) / close
    out["lower_wick_pct"] = (out["open"] - low) / close

    return out


def load_csv(path) -> pd.DataFrame:
    """Carga un CSV de velas (time epoch seg + OHLC) y lo ordena por tiempo."""
    return pd.read_csv(path).sort_values("time").reset_index(drop=True)


FEATURE_COLUMNS = [
    "rsi_14",
    "willr_14",
    "ema_9",
    "ema_21",
    "ema_50",
    "macd",
    "macd_signal",
    "macd_hist",
    "atr_14",
    "ret_1",
    "ret_5",
    "ret_10",
    "range_pct",
    "body_pct",
    "upper_wick_pct",
    "lower_wick_pct",
]