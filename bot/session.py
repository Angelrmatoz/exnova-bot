"""Sesión de trading con límite duro: máximo 3 operaciones.

Parada: 2 WINs (take-profit de sesión) o 2 LOSSes (stop-loss de sesión) o
3 operaciones. Los resultados DRAW (equal/tie) cuentan como operación pero
no rompen la regla.

Con wait=True la sesión espera a que cierre una vela NUEVA y solo opera si
la vela cerrada confirma dirección (cuerpo mínimo + 2 velas seguidas en el
mismo sentido); si no, salta y espera la siguiente vela en vez de forzar
trades sobre ruido. Con wait=False (tests/backtest) opera directamente
sobre la última vela disponible.
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
VALIDATED_BASES = {"EURUSD", "GBPUSD"}
MIN_PAYOUT = 0.80

_STEP_SECONDS = {"1m": 60, "5m": 300}

MIN_BODY_PCT = 0.0002

OnTrade = Callable[..., None]


def should_stop(wins: int, losses: int, trades: int, max_trades: int = MAX_TRADES) -> bool:
    return trades >= max_trades or wins >= TAKE_PROFIT or losses >= STOP_LOSS


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


def _wait_for_new_candle(
    broker: BrokerClient,
    pair: str,
    timeframe: str,
    prev_time: float,
    timeout: float = 180.0,
) -> dict[str, Any] | None:
    """Espera a que el broker devuelva una vela con time distinto a prev_time.

    En vez de dormir hasta un borde de vela por reloj local (frágil con
    drift), se sondea get_candles hasta ver una vela nueva.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        candles = broker.get_candles(pair, timeframe, 2)
        if candles and candles[-1]["time"] != prev_time:
            return candles[-1]
        time.sleep(2)
    return None


def _wait_for_closed_candle(
    broker: BrokerClient,
    pair: str,
    timeframe: str,
    prev_time: float,
    timeout: float = 180.0,
) -> list[dict[str, Any]] | None:
    """Espera a que cierre una vela NUEVA y devuelve el historial hasta ella.

    La lista termina en la vela recién cerrada (se descarta la vela en
    formación, candles[-1], que es ruido). Trae HISTORY_N velas para que
    la señal de reversión tenga warm-up de indicadores.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        candles = broker.get_candles(pair, timeframe, HISTORY_N)
        if len(candles) >= 2 and candles[-2]["time"] != prev_time:
            return candles[:-1]
        time.sleep(2)
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

    Señal: unión Double Reversal + Exhaustion en velas 1m (validada en
    EURUSD/GBPUSD reales, ~56-58% a expiración 5m). `expiry` fija la
    expiración de la orden (None = timeframe). Pares sin edge validado
    y mercado OTC (feed aleatorio) se omiten.
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
    if timeframe != "1m":
        print("Señal validada solo en velas 1m: operando sin edge confirmado.")
    duration = expiry or timeframe
    assets = tradable
    wins = losses = trades = 0
    pnl_total = 0.0
    prev_candle_time: float | None = None
    while not should_stop(wins, losses, trades):
        pair = assets[trades % len(assets)]
        gate = "reversion"
        if wait and prev_candle_time is None:
            base = broker.get_candles(pair, timeframe, 2)
            if not base:
                print(f"[{pair}] sin velas, terminando sesión.")
                break
            prev_candle_time = base[-1]["time"]
        if wait:
            wait_timeout = 2 * _STEP_SECONDS.get(timeframe, 60)
            hist = _wait_for_closed_candle(broker, pair, timeframe, prev_candle_time, wait_timeout)
            if not hist:
                print(f"[{pair}] timeout esperando vela nueva, terminando sesión.")
                break
            closed = hist[-1]
            if len(hist) >= MIN_HISTORY:
                signal = reversion_signal(hist)
            else:
                gate = "momentum"
                signal = signal_for(closed["close"], closed["open"])
            if signal is None:
                print(f"[{pair}] sin setup de reversión, esperando siguiente vela...")
                prev_candle_time = closed["time"]
                continue
            side, confidence = signal
            prev_candle_time = closed["time"]
        else:
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
