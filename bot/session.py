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

from bot.broker.base import BrokerClient

MAX_TRADES = 3
TAKE_PROFIT = 2
STOP_LOSS = 2

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
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Espera a que se cierre una vela NUEVA y devuelve la recién cerrada + la anterior.

    La vela en formación (candles[-1]) es ruido: la señal se toma de la vela
    que acaba de cerrar (candles[-2]) y su predecesora para confirmar
    dirección. Se espera hasta que candles[-2] sea distinta a prev_time, es
    decir, hasta que haya cerrado una vela nueva desde el último análisis.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        candles = broker.get_candles(pair, timeframe, 3)
        if len(candles) >= 2 and candles[-2]["time"] != prev_time:
            prev_closed = candles[-3] if len(candles) >= 3 else None
            return candles[-2], prev_closed
        time.sleep(2)
    return None, None


def run_session(
    broker: BrokerClient,
    assets: list[str],
    timeframe: str,
    stake: float,
    market_type: str = "NORMAL",
    on_trade: OnTrade | None = None,
    wait: bool = True,
) -> dict[str, float]:
    """Opera sobre los assets hasta que la regla de 3 pare la sesión.

    `on_trade` recibe kwargs {pair, market_type, signal, result, pnl, confidence,
    gate_passed} y se llama por operación (None = no persistir).
    Devuelve resumen {trades, wins, losses, pnl}.
    """
    wins = losses = trades = 0
    pnl_total = 0.0
    prev_candle_time: float | None = None
    while not should_stop(wins, losses, trades):
        pair = assets[trades % len(assets)]
        if wait and prev_candle_time is None:
            base = broker.get_candles(pair, timeframe, 2)
            if not base:
                print(f"[{pair}] sin velas, terminando sesión.")
                break
            prev_candle_time = base[-1]["time"]
        if wait:
            wait_timeout = 2 * _STEP_SECONDS.get(timeframe, 60)
            closed, prev_closed = _wait_for_closed_candle(broker, pair, timeframe, prev_candle_time, wait_timeout)
            if closed is None:
                print(f"[{pair}] timeout esperando vela nueva, terminando sesión.")
                break
            signal = confirmed_signal(closed, prev_closed)
            if signal is None:
                print(f"[{pair}] sin confirmación de setup, esperando siguiente vela...")
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
            side, confidence = signal_for(last["close"], last["open"])
        order_id = broker.place_order(pair, side, stake, timeframe)
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
                gate_passed="session",
            )
        print(
            f"[{pair}] {side.upper()} -> {result} pnl {trade_pnl:+.2f}"
            f"  ({wins}W/{losses}L, {trades}/{MAX_TRADES})"
        )
    print(f"=== Sesión terminada: {trades} operaciones, {wins}W {losses}L, pnl {pnl_total:+.2f}")
    return {"trades": trades, "wins": wins, "losses": losses, "pnl": pnl_total}
