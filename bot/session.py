"""Sesión de trading con límite duro: máximo 3 operaciones.

Parada: 2 WINs (take-profit de sesión) o 2 LOSSes (stop-loss de sesión) o
3 operaciones. Los resultados DRAW (equal/tie) cuentan como operación pero
no rompen la regla. La señal es momentum sobre la última vela cerrada.
"""

from __future__ import annotations

import time
from typing import Any, Callable

from bot.broker.base import BrokerClient

MAX_TRADES = 3
TAKE_PROFIT = 2
STOP_LOSS = 2

_STEP_SECONDS = {"1m": 60, "5m": 300}

OnTrade = Callable[..., None]


def should_stop(wins: int, losses: int, trades: int, max_trades: int = MAX_TRADES) -> bool:
    return trades >= max_trades or wins >= TAKE_PROFIT or losses >= STOP_LOSS


def signal_for(close: float, open_: float) -> tuple[str, float]:
    """Dirección + confianza proxy de la última vela cerrada."""
    direction = "call" if close > open_ else "put"
    magnitude = abs(close - open_) / open_
    confidence = min(0.5 + magnitude, 0.99)
    return direction, confidence


def normalize_result(result: str) -> str:
    """Unifica formatos de resultado de los brokers (win/loose/equal/lose/tie)."""
    r = result.upper()
    if r in ("LOOSE", "LOSE"):
        return "LOSS"
    if r in ("EQUAL", "TIE"):
        return "DRAW"
    return r


def _seconds_until_next(timeframe: str) -> float:
    step = _STEP_SECONDS[timeframe]
    return step - (time.time() % step)


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
    while not should_stop(wins, losses, trades):
        pair = assets[trades % len(assets)]
        candles = broker.get_candles(pair, timeframe, 2)
        if not candles:
            print(f"[{pair}] sin velas, terminando sesión.")
            break
        last = candles[-1]
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
        if wait and not should_stop(wins, losses, trades):
            # ponytail: alinea al borde de vela con reloj local, no server time;
            # mejora con server_timestamp del WS client si el drift molesta.
            time.sleep(_seconds_until_next(timeframe))
    print(f"=== Sesión terminada: {trades} operaciones, {wins}W {losses}L, pnl {pnl_total:+.2f}")
    return {"trades": trades, "wins": wins, "losses": losses, "pnl": pnl_total}
