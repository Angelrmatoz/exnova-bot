"""Tests de las ventanas de apertura del bróker."""

from bot.schedule import closure_around, is_open, next_close, next_open


def test_is_open_dentro_y_fuera():
    sched = [[100, 200], [300, 400]]
    assert is_open(sched, 150)
    assert is_open(sched, 300)
    assert not is_open(sched, 250)
    assert not is_open(sched, 99)


def test_next_close_y_next_open():
    sched = [[100, 200], [300, 400]]
    assert next_close(sched, 150) == 200
    assert next_close(sched, 250) is None
    assert next_open(sched, 150) == 300
    assert next_open(sched, 350) is None


def test_closure_around():
    sched = [[100, 200], [300, 400]]
    assert closure_around(sched, 250) == (200, 300)
    assert closure_around(sched, 150) is None


def test_schedule_vacio_o_malformado():
    assert not is_open([], 1)
    assert not is_open(None, 1)
    assert next_close(None, 1) is None
    assert next_open([], 1) is None
