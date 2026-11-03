"""Sesión de trading con límite duro: máximo 3 operaciones.

Parada: 2 WINs (take-profit de sesión) o 2 LOSSes (stop-loss de sesión) o
3 operaciones. Los resultados DRAW (equal/tie) cuentan como operación pero
no rompen la regla.

Con wait=True cada vela cerrada se escanea en TODOS los pares y se opera el
primer setup encontrado; el resto de la vela la sesión duerme. Las entradas
solo se permiten en TRADING_HOURS_UTC (18-24 UTC); fuera de esa ventana la
sesión espera sin operar. Con wait=False (tests/backtest) opera directamente
sobre la última vela disponible, sin filtro horario.
"""

from __future__ import annotations

import time
from typing import Any, Callable

import pandas as pd

from bot.broker.base import BrokerClient
from bot.ml.features import build_features

MAX_TRADES = 3
TAKE_PROFIT = 2
STOP_LOSS = 2

HISTORY_N = 50
MIN_HISTORY = 30
VALIDATED_BASES = {
    "EURUSD",
    "GBPUSD",
    "USDJPY",
    "AUDUSD",
    "EURGBP",
    "EURJPY",
    "GBPJPY",
    "USDCAD",
    "NZDUSD",
    "EURAUD",
    "CADCHF",
}
MIN_PAYOUT = 0.86

_STEP_SECONDS = {"1m": 60, "5m": 300}

MIN_BODY_PCT = 0.0002

MIN_SAMPLE = 60
MIN_WIN_RATE = 0.538

TRADING_HOURS_UTC = frozenset(range(18, 24))

OnTrade = Callable[..., None]


def entry_in_window(clock: float, step: int) -> bool:
    """True si la hora UTC de la vela de entrada cae en la ventana validada."""
    return time.gmtime(clock + step).tm_hour in TRADING_HOURS_UTC


def should_stop(wins: int, losses: int, trades: int, max_trades: int = MAX_TRADES) -> bool:
    return trades >= max_trades or wins >= TAKE_PROFIT or losses >= STOP_LOSS


def edge_alive(win_rate: float | None, resolved: int) -> bool:
    """False si hay muestra suficiente y el win rate realizado no cubre el breakeven."""
    return resolved < MIN_SAMPLE or (win_rate is not None and win_rate >= MIN_WIN_RATE)


def signal_for(close: float, open_: float) -> tuple[str, float]:
    """Dirección + confianza proxy de una vela."""
    direction = "call" if close > open_ else "put"
    magnitude = abs(close - open_) / open_
    confidence = min(0.5 + magnitude, 0.99)
    return direction, confidence


def confirmed_signal(closed: dict[str, Any], prev: dict[str, Any] | None) -> tuple[str, float] | None:
    """Señal solo si la vela cerrada tiene cuerpo y confirma la dirección previa.

    None = sin setup confirmado: saltar y esperar la siguiente vela.
    """
    if prev is None:
        return None
    body_pct = abs(closed["close"] - closed["open"]) / closed["open"]
    if body_pct < MIN_BODY_PCT:
        return None
    side, confidence = signal_for(closed["close"], closed["open"])
    prev_side, _ = signal_for(prev["close"], prev["open"])
    if prev_side != side:
        return None
    return side, confidence


def _base_pair(pair: str) -> str:
    """EURUSD-op -> EURUSD (normaliza sufijos de mercado del bróker)."""
    p = pair.upper()
    for suf in ("-OTC", "-OP"):
        if p.endswith(suf):
            p = p[: -len(suf)]
    return p


def reversion_signal(hist: list[dict[str, Any]]) -> tuple[str, float] | None:
    """Unión Double Reversal + Exhaustion sobre la última vela de hist.

    hist va de antigua a nueva y termina en la vela cerrada. Reglas
    validadas en 1m real (EURUSD/GBPUSD, ~53-58% a expiración 2-5 velas):
    cierre fuera de Bollinger(20,2) + RSI(14) extremo 25/75, o vela de
    exaustión (rango >= 2xATR, cuerpo >= 60%) cerrando fuera de banda.
    None = sin setup o sin historial suficiente.
    """
    if len(hist) < MIN_HISTORY:
        return None
    df = build_features(pd.DataFrame(hist)).dropna(subset=["rsi_14", "atr_14"]).reset_index(drop=True)
    if len(df) < 20:
        return None
    close = df["close"]
    sma = close.rolling(20).mean().iloc[-1]
    sd = close.rolling(20).std().iloc[-1]
    if pd.isna(sma) or pd.isna(sd):
        return None
    row = df.iloc[-1]
    lo, hi, rsi = sma - 2 * sd, sma + 2 * sd, row["rsi_14"]
    side = None
    if row["close"] < lo and rsi < 25:
        side = "call"
    elif row["close"] > hi and rsi > 75:
        side = "put"
    else:
        rng = row["high"] - row["low"]
        body = abs(row["close"] - row["open"]) / rng if rng else 0
        if rng >= 2 * row["atr_14"] and body >= 0.6:
            if row["close"] > hi:
                side = "put"
            elif row["close"] < lo:
                side = "call"
    if side is None:
        return None
    _, confidence = signal_for(row["close"], row["open"])
    return side, confidence


def normalize_result(result: str) -> str:
    """Unifica formatos de resultado de los brokers (win/loose/equal/lose/tie)."""
    r = result.upper()
    if r in ("LOOSE", "LOSE"):
        return "LOSS"
    if r in ("EQUAL", "TIE"):
        return "DRAW"
    return r


def _scan(
    broker: BrokerClient,
    assets: list[str],
    timeframe: str,
    clock: float,
) -> tuple[str, str, float, str] | None:
    """Primer par de `assets` con señal en la vela cerrada `clock`.

    Devuelve (pair, side, confidence, gate) o None si ningún par tiene setup.
    """
    for pair in assets:
        candles = broker.get_candles(pair, timeframe, HISTORY_N)
        if len(candles) < 2:
            continue
        hist = candles[:-1]
        if hist[-1]["time"] != clock:
            continue
        if len(hist) >= MIN_HISTORY:
            signal = reversion_signal(hist)
            gate = "reversion"
        else:
            signal = signal_for(hist[-1]["close"], hist[-1]["open"])
            gate = "momentum"
        if signal is not None:
            return pair, signal[0], signal[1], gate
    return None


def run_session(
    broker: BrokerClient,
    assets: list[str],
    timeframe: str,
    stake: float,
    market_type: str = "NORMAL",
    on_trade: OnTrade | None = None,
    wait: bool = True,
    expiry: str | None = None,
) -> dict[str, float]:
    """Opera sobre los assets hasta que la regla de 3 pare la sesión.

    Señal: unión Double Reversal + Exhaustion en velas de 5m, validada en 11
    pares NORMAL (55.13% ±0.81%, expectancy +2.54% con payout 0.86, estable
    70/30). Solo opera con entrada entre las 18 y las 24 UTC, donde la misma
    regla sube a 62.89% (n=2781, +17% por operación, positiva en los 11 pares
    y en los 11 meses). `expiry` fija la expiración de la orden (None =
    timeframe). Pares sin edge validado y mercado OTC (feed sintético, 48-49%)
    se omiten.
    Con wait=True cada vela cerrada se escanea en TODOS los pares y se opera el
    primer setup; el resto de la vela se espera en reposo.
    `on_trade` recibe kwargs {pair, market_type, signal, result, pnl, confidence,
    gate_passed} y se llama por operación (None = no persistir).
    Devuelve resumen {trades, wins, losses, pnl}.
    """
    if market_type.upper() == "OTC":
        print("Mercado OTC sin edge validado (feed ~50%): sesión no opera.")
        return {"trades": 0, "wins": 0, "losses": 0, "pnl": 0.0}
    tradable = [a for a in assets if _base_pair(a) in VALIDATED_BASES]
    for a in assets:
        if a not in tradable:
            print(f"[{a}] par sin edge validado, se omite.")
    get_payout = getattr(broker, "get_payout", None)
    if get_payout is not None:
        low = [a for a in tradable if (get_payout(a) or 0) < MIN_PAYOUT]
        for a in low:
            print(f"[{a}] payout bajo mínimo {MIN_PAYOUT:.0%}, se omite.")
        tradable = [a for a in tradable if a not in low]
    if not tradable:
        print("Sin activos operables, terminando sesión.")
        return {"trades": 0, "wins": 0, "losses": 0, "pnl": 0.0}
    if timeframe != "5m":
        print("Señal validada solo en velas 5m: operando sin edge confirmado.")
    duration = expiry or timeframe
    assets = tradable
    wins = losses = trades = 0
    pnl_total = 0.0
    prev_candle_time: float | None = None
    idle_limit = 4 * _STEP_SECONDS.get(timeframe, 300)
    idle_deadline = time.time() + idle_limit
    step = _STEP_SECONDS.get(timeframe, 300)
    in_window = True
    skipped_hour: int | None = None
    if wait and not TRADING_HOURS_UTC >= set(range(24)):
        print(f"Ventana operativa: {sorted(TRADING_HOURS_UTC)} UTC (resto, en reposo).")
    while not should_stop(wins, losses, trades):
        gate = "reversion"
        if wait:
            clock = None
            for probe in assets:
                candles = broker.get_candles(probe, timeframe, 2)
                if len(candles) >= 2:
                    clock = candles[-2]["time"]
                    break
            if clock is None:
                print("Sin velas en ningún par, terminando sesión.")
                break
            if clock == prev_candle_time:
                if in_window and time.time() > idle_deadline:
                    print("Sin velas nuevas, terminando sesión.")
                    break
                time.sleep(2 if in_window else 30)
                continue
            prev_candle_time = clock
            in_window = entry_in_window(clock, step)
            if not in_window:
                if time.gmtime(clock + step).tm_hour != skipped_hour:
                    skipped_hour = time.gmtime(clock + step).tm_hour
                    print(f"Fuera de ventana ({skipped_hour:02d}h UTC): esperando.")
                continue
            skipped_hour = None
            idle_deadline = time.time() + idle_limit
            found = _scan(broker, assets, timeframe, clock)
            if found is None:
                print(f"Vela {clock:.0f}: sin setup en {len(assets)} pares, esperando...")
                continue
            pair, side, confidence, gate = found
        else:
            pair = assets[trades % len(assets)]
            candles = broker.get_candles(pair, timeframe, 2)
            if not candles:
                print(f"[{pair}] sin velas, terminando sesión.")
                break
            last = candles[-1]
            prev_candle_time = last["time"]
            gate = "momentum"
            side, confidence = signal_for(last["close"], last["open"])
        order_id = broker.place_order(pair, side, stake, duration)
        if order_id is None:
            print(f"[{pair}] orden rechazada, terminando sesión.")
            break
        result, trade_pnl = broker.check_result(order_id)
        result = normalize_result(result)
        wins += result == "WIN"
        losses += result == "LOSS"
        trades += 1
        pnl_total += trade_pnl
        if on_trade:
            on_trade(
                pair=pair,
                market_type=market_type,
                signal=side,
                result=result,
                pnl=trade_pnl,
                confidence=confidence,
                gate_passed=gate,
            )
        print(
            f"[{pair}] {side.upper()} -> {result} pnl {trade_pnl:+.2f}"
            f"  ({wins}W/{losses}L, {trades}/{MAX_TRADES})"
        )
    print(f"=== Sesión terminada: {trades} operaciones, {wins}W {losses}L, pnl {pnl_total:+.2f}")
    return {"trades": trades, "wins": wins, "losses": losses, "pnl": pnl_total}
