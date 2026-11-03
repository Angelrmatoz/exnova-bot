"""Tests del anclaje OTC: horario de entrada, lado y bucle de operación."""

import pytest

from bot.anchor import (
    ANCHORS,
    LEAD_SECONDS,
    MIN_SAMPLE,
    MIN_WIN_RATE,
    anchor_alive,
    decide,
    next_entry_ts,
    run_anchors,
)


def test_next_entry_ts_antes_del_anclaje():
    now = 1793664000  # 2026-11-03 00:00 UTC
    assert next_entry_ts(now, 8, 10) == now + 8 * 3600 + 10 * 60 - LEAD_SECONDS
    assert next_entry_ts(now, 1, 10) == now + 3600 + 10 * 60 - LEAD_SECONDS


def test_next_entry_ts_salta_al_dia_siguiente():
    now = 1793664000 + 9 * 3600  # 09:00 UTC, el anclaje de 08:10 ya pasó
    assert next_entry_ts(now, 8, 10) == now + 86400 - 50 * 60 - LEAD_SECONDS


def test_decide_por_signo_del_desvio():
    assert decide(0.01, 1.1) == "call"
    assert decide(-0.01, 1.1) == "put"


def test_decide_ignora_desvio_pequeno():
    assert decide(0.0004, 1.1) is None
    assert decide(0.0006, 1.1) == "call"


def test_anchor_alive_umbral():
    assert anchor_alive(None, 0)
    assert anchor_alive(0.5, MIN_SAMPLE - 1)
    assert not anchor_alive(0.5, MIN_SAMPLE)
    assert anchor_alive(MIN_WIN_RATE, MIN_SAMPLE)


class _FakeBroker:
    def __init__(self, otc_price, real_price):
        self.prices = {"AUDUSD-OTC": otc_price, "AUDUSD-op": real_price}
        self.orders = []

    def get_candles(self, pair, timeframe, n):
        price = self.prices.get(pair)
        if price is None:
            return []
        return [{"time": 0, "open": price, "close": price, "high": price, "low": price}]

    def place_order(self, pair, side, stake, duration):
        self.orders.append((pair, side, stake, duration))
        return 1

    def check_result(self, order_id):
        return "win", 0.87 * 1000


class _Clock:
    """Reloj falso que avanza al dormir, para no colgar el bucle de espera."""

    def __init__(self, start):
        self.now = start
        self.slept = 0.0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds
        self.slept += seconds


def test_run_anchors_opera_en_la_direccion_del_desvio():
    broker = _FakeBroker(otc_price=0.7000, real_price=0.7100)
    clk = _Clock(1793664000.0)  # 00:00 UTC, antes del anclaje de 01:10

    res = run_anchors(broker, 1000.0, pairs=["AUDUSD"], clock=clk, sleep=clk.sleep)

    assert broker.orders == [("AUDUSD-OTC", "call", 1000.0, "15m")]
    assert res["trades"] == 1
    assert res["wins"] == 1
    assert clk.slept > 0


def test_run_anchors_omite_desvio_pequeno():
    broker = _FakeBroker(otc_price=0.7000, real_price=0.7001)
    clk = _Clock(1793664000.0)
    res = run_anchors(broker, 1000.0, pairs=["AUDUSD"], clock=clk, sleep=clk.sleep)
    assert broker.orders == []
    assert res["trades"] == 0
