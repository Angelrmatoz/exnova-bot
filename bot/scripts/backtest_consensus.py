"""Backtest offline del sistema de consenso 3/3 sobre velas históricas.

Evalúa la estrategia acordada en plan.md sin tocar el bróker:

- RSI 30/70 (reversión): RSI > 70 => PUT, RSI < 30 => CALL.
- Confirmación EMA: para CALL el precio debe estar por encima de ema_21
  (rebote alcista iniciado), para PUT por debajo.
- Confirmación MACD: macd_hist > 0 para CALL, < 0 para PUT.
- Consenso 3/3: solo opera cuando las tres señales apuntan al mismo lado.
- Gate ATR opcional: filtra por percentil rodante de atr_14 (evita micro
  volatilidad y vol extrema, según la investigación previa).

La operación se abre en la vela cerrada t y se resuelve con la vela t+1:
CALL gana si close[t+1] > close[t], PUT si close[t+1] < close[t].

Reporta por par: operaciones, win rate, expectancy, PnL y drawdown, y lo
compara contra el baseline de momentum (signal_for) del mismo set.

Uso:
    uv run python -m bot.scripts.backtest_consensus --pairs data/5m/EURUSD.csv,data/5m/GBPUSD.csv
    uv run python -m bot.scripts.backtest_consensus --pairs data/5m/EURUSD.otc.csv --payout 0.95
    uv run python -m bot.scripts.backtest_consensus --pairs <otc_76_60.csv> --atr-min 0.2 --atr-max 0.8
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from bot.ml.features import build_features, load_csv


def load_frame(path: str) -> pd.DataFrame:
    """Carga CSV de velas, normalizando el formato OTC (from/to/min/max)."""
    raw = pd.read_csv(path)
    rename = {"from": "time", "min": "low", "max": "high"}
    return raw.rename(columns=rename).sort_values("time").reset_index(drop=True)


def consensus_signal(row: pd.Series, rsi_hi: float = 70.0, rsi_lo: float = 30.0) -> str | None:
    """Dirección del consenso 3/3 sobre la vela cerrada, o None si no converge.

    Reversión RSI 30/70: la vela cerrada ya gira en contra de la tendencia
    (roja tras sobrecompra, verde tras sobreventa) y el MACD lo confirma.
    La EMA de tendencia NO se usa aquí: RSI>70 implica precio sobre la media
    en la misma vela, así que close<ema sería imposible (0 hits reales).
    rsi_hi/rsi_lo ajustan el umbral de extremo (70/30 = estándar).
    """
    rsi, macd_hist = row["rsi_14"], row["macd_hist"]
    close, open_ = row["close"], row["open"]

    if rsi > rsi_hi and close < open_ and macd_hist < 0:
        return "put"
    if rsi < rsi_lo and close > open_ and macd_hist > 0:
        return "call"
    return None


def trend_signal(row: pd.Series, rsi_hi: float = 70.0, rsi_lo: float = 30.0) -> str | None:
    """Consenso 3/3 de TENDENCIA (Trinity): RSI 50 + EMA + MACD alineados.

    RSI en zona de tendencia (50-rsi_hi CALL / rsi_lo-50 PUT), precio
    sobre/bajo ema_21, y MACD en el mismo lado. No persigue extremos.
    """
    rsi, ema21, macd_hist = row["rsi_14"], row["ema_21"], row["macd_hist"]
    close = row["close"]

    if 50 <= rsi < rsi_hi and close > ema21 and macd_hist > 0:
        return "call"
    if rsi_lo < rsi <= 50 and close < ema21 and macd_hist < 0:
        return "put"
    return None


def run_pair(frame: pd.DataFrame, payout: float, atr_min: float, atr_max: float, mode: str,
             rsi_hi: float = 70.0, rsi_lo: float = 30.0) -> dict:
    df = build_features(frame)
    df = df.dropna(subset=["rsi_14", "macd_hist", "atr_14"]).reset_index(drop=True)

    if atr_min > 0 or atr_max < 1.0:
        atr_pct = df["atr_14"] / df["atr_14"].rolling(500, min_periods=500).mean()
        df = df[atr_pct.between(atr_min, atr_max)].reset_index(drop=True)

    signal_fn = {"reversion": consensus_signal, "trend": trend_signal}[mode]
    kwargs = {"rsi_hi": rsi_hi, "rsi_lo": rsi_lo}

    trades = wins = 0
    pnl = 0.0
    cum = []
    peak = 0.0
    max_dd = 0.0
    closed = df["close"].to_numpy()

    for i in range(1, len(df)):
        signal = signal_fn(df.iloc[i - 1], **kwargs)
        if signal is None:
            continue
        up = closed[i] > closed[i - 1]
        win = (signal == "call") == up
        trades += 1
        wins += win
        trade_pnl = payout if win else -1.0
        pnl += trade_pnl
        cum.append(pnl)
        peak = max(peak, pnl)
        max_dd = max(max_dd, peak - pnl)

    return {
        "trades": trades,
        "wins": wins,
        "win_rate": wins / trades if trades else 0.0,
        "expectancy": pnl / trades if trades else 0.0,
        "pnl": pnl,
        "max_drawdown": max_dd,
    }


def baseline_run(frame: pd.DataFrame, payout: float) -> dict:
    """Baseline momentum (signal_for) sobre el mismo set de velas."""
    df = frame.dropna(subset=["close"]).reset_index(drop=True)
    trades = wins = 0
    pnl = 0.0
    closed = df["close"].to_numpy()
    for i in range(1, len(df)):
        up = closed[i] > closed[i - 1]
        signal = "call" if closed[i - 1] > df["open"].iloc[i - 1] else "put"
        win = (signal == "call") == up
        trades += 1
        wins += win
        pnl += payout if win else -1.0
    return {
        "trades": trades,
        "wins": wins,
        "win_rate": wins / trades if trades else 0.0,
        "expectancy": pnl / trades if trades else 0.0,
        "pnl": pnl,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest de consenso 3/3 offline")
    parser.add_argument("--pairs", required=True, help="CSV de velas (coma = varios)")
    parser.add_argument("--payout", type=float, default=0.80, help="Payout por ganar (0.80 = 80%%)")
    parser.add_argument("--atr-min", type=float, default=0.0, help="Percentil ATR mínimo (0-1)")
    parser.add_argument("--atr-max", type=float, default=1.0, help="Percentil ATR máximo (0-1)")
    parser.add_argument("--mode", default="reversion", choices=["reversion", "trend"],
                        help="reversion = RSI 30/70; trend = RSI 50 (Trinity)")
    parser.add_argument("--rsi-hi", type=float, default=70.0, help="Umbral RSI superior (70 = estándar)")
    parser.add_argument("--rsi-lo", type=float, default=30.0, help="Umbral RSI inferior (30 = estándar)")
    args = parser.parse_args()

    rows = []
    for path in args.pairs.split(","):
        pair = Path(path).stem
        frame = load_frame(path)
        if len(frame) < 600:
            print(f"[{pair}] pocas velas ({len(frame)}), saltando.")
            continue
        r = run_pair(frame, args.payout, args.atr_min, args.atr_max, args.mode,
                     args.rsi_hi, args.rsi_lo)
        b = baseline_run(frame, args.payout)
        rows.append((pair, r, b))

    print(f"Payout: {args.payout:.0%} | ATR gate: [{args.atr_min:.2f}, {args.atr_max:.2f}] "
          f"| Modo: {args.mode} | RSI: [{args.rsi_lo:.0f}, {args.rsi_hi:.0f}]")
    print(f"\n{'Par':<12}{'modo':<10}{'ops':>6}{'win%':>8}{'expect':>9}{'pnl':>9}{'maxDD':>8}")
    for pair, r, b in rows:
        print(f"{pair:<12}{'consenso':<10}{r['trades']:>6}{r['win_rate']:>7.1%}"
              f"{r['expectancy']:>+9.3f}{r['pnl']:>+9.1f}{r['max_drawdown']:>8.1f}")
        print(f"{'':<12}{'baseline':<10}{b['trades']:>6}{b['win_rate']:>7.1%}"
              f"{b['expectancy']:>+9.3f}{b['pnl']:>+9.1f}{'':>8}")

    total_ops = sum(r["trades"] for _, r, _ in rows)
    total_pnl = sum(r["pnl"] for _, r, _ in rows)
    print(f"\nTotal consenso: {total_ops} ops, PnL {total_pnl:+.2f}")
    print(f"Necesario: win_rate > {1 / (1 + args.payout):.1%} para expectancy positiva con payout {args.payout:.0%}.")


if __name__ == "__main__":
    main()
