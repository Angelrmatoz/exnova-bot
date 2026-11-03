"""Anclaje OTC: el precio sintético vuelve al real una vez al día.

Medido sobre 2026 (11 pares OTC, 5m): cada par se desvía del par NORMAL con
un random walk y a su hora UTC salta de golpe al precio real. En los pares de
esta tabla el signo del salto coincide con `real - otc` el 96,9-98,1% de los
días (n=153-209), estable a expiración 15m.

La dirección se conoce ANTES del salto: se entra LEAD_SECONDS antes con el
desvío aún abierto. El edge es un artefacto del feed OTC, no del mercado.
"""

from __future__ import annotations

import time
from typing import Any, Callable

from bot.broker.base import BrokerClient

ANCHORS: dict[str, tuple[int, int]] = {
    "AUDUSD": (1, 10),
    "EURUSD": (8, 10),
    "USDCAD": (8, 10),
    "EURAUD": (8, 10),
    "CADCHF": (8, 10),
}

LEAD_SECONDS = 120
MIN_GAP_REL = 5e-4

MIN_SAMPLE = 15
MIN_WIN_RATE = 0.90

MARKET_TYPE = "ANCHOR"

OnTrade = Callable[..., None]


def next_entry_ts(now: float, hour: int, minute: int) -> float:
    """Epoch de la próxima entrada: anclaje del día menos LEAD_SECONDS."""
    day = int(now // 86400) * 86400
    ts = day + hour * 3600 + minute * 60 - LEAD_SECONDS
    return ts + 86400 if ts <= now else ts


def decide(gap: float, price: float) -> str | None:
    """Lado a operar según el desvío, o None si es demasiado pequeño."""
    if price <= 0 or abs(gap) < MIN_GAP_REL * price:
        return None
    return "call" if gap > 0 else "put"


def anchor_alive(win_rate: float | None, resolved: int) -> bool:
    """Kill-switch propio: 90% de acierto tras 15 operaciones resueltas."""
    return resolved < MIN_SAMPLE or (win_rate is not None and win_rate >= MIN_WIN_RATE)


def run_anchors(
    broker: BrokerClient,
    stake: float,
    on_trade: OnTrade | None = None,
    pairs: list[str] | None = None,
    rounds: int = 1,
    duration: str = "15m",
    clock: Callable[[], float] = time.time,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, float]:
    """Opera un anclaje por par y ronda. Bloquea hasta cada hora de entrada.

    Los anclajes cuya hora ya pasó se programan para el día siguiente: nunca
    se entra con el salto ya ocurrido.
    """
    bases = list(pairs or ANCHORS)
    wins = losses = trades = 0
    pnl_total = 0.0
    for _ in range(rounds):
        schedule = sorted(
            (next_entry_ts(clock(), *ANCHORS[base]), base) for base in bases
        )
        for ts, base in schedule:
            otc, real = f"{base}-OTC", f"{base}-op"
            while clock() < ts:
                sleep(min(5.0, max(0.05, ts - clock())))
            otc_candles = broker.get_candles(otc, "1m", 1)
            real_candles = broker.get_candles(real, "1m", 1)
            if not otc_candles or not real_candles:
                print(f"[{base}] sin precios, se omite.")
                continue
            price = otc_candles[-1]["close"]
            gap = real_candles[-1]["close"] - price
            side = decide(gap, price)
            if side is None:
                print(f"[{base}] desvio {gap:+.5f} insuficiente, se omite.")
                continue
            order_id = broker.place_order(otc, side, stake, duration)
            if order_id is None:
                print(f"[{base}] orden rechazada.")
                continue
            result, trade_pnl = broker.check_result(order_id)
            result = result.upper()
            if result in ("LOOSE", "LOSE"):
                result = "LOSS"
            wins += result == "WIN"
            losses += result == "LOSS"
            trades += 1
            pnl_total += trade_pnl
            if on_trade:
                on_trade(
                    pair=otc,
                    market_type=MARKET_TYPE,
                    signal=side,
                    result=result,
                    pnl=trade_pnl,
                    confidence=abs(gap),
                    gate_passed="anchor",
                )
            print(
                f"[{otc}] gap {gap:+.5f} {side.upper()} -> {result} pnl {trade_pnl:+.2f}"
                f"  ({wins}W/{losses}L)"
            )
    print(f"=== Anclajes: {trades} operaciones, {wins}W {losses}L, pnl {pnl_total:+.2f}")
    return {"trades": trades, "wins": wins, "losses": losses, "pnl": pnl_total}
