"""Tests del escaneo de anclas: clasificación FX, ancla y ventanas abiertas."""

from bot.scripts.anchor_scan import fmt_windows, is_fx, open_windows, parse_anchor


def test_is_fx_solo_divisas():
    assert is_fx("EURUSD-OTC")
    assert is_fx("USDARS-OTC")
    assert not is_fx("XAUUSD-OTC")
    assert not is_fx("ETHUSD-OTC")
    assert not is_fx("AMZN/ALIBABA-OTC")
    assert not is_fx("US30-OTC")


def test_parse_anchor():
    assert parse_anchor("00:00") == 0
    assert parse_anchor("08:10") == 29400
    assert parse_anchor("20:50") == 75000


def test_open_windows_recorta_al_dia():
    day = 86400
    schedule = [[1, 28800], [32400, 86400]]
    assert open_windows(schedule, 0, day) == [(1, 28800), (32400, 86400)]
    assert fmt_windows(open_windows(schedule, 0, day), 0) == "00:00-08:00, 09:00-24:00"


def test_open_windows_dia_cerrado():
    assert open_windows([[0, 100]], 86400, 172800) == []
    assert fmt_windows([], 86400) == "-"
