"""Tests de la capa SQLite: win rate realizado sobre trade_logs."""

import pytest

from bot import db


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    return tmp_path / "test.db"


def _log(result, market_type="NORMAL"):
    db.log_trade(
        pair="EURUSD-op",
        market_type=market_type,
        signal="call",
        result=result,
        pnl=0.86 if result == "WIN" else -1.0,
    )


def test_get_win_rate_sin_operaciones(tmp_db):
    assert db.get_win_rate() == (None, 0)


def test_get_win_rate_ignora_skipped(tmp_db):
    for result in ("WIN", "WIN", "WIN", "LOSS", "SKIPPED"):
        _log(result)
    rate, resolved = db.get_win_rate()
    assert resolved == 4
    assert rate == pytest.approx(0.75)


def test_get_win_rate_filtra_por_mercado(tmp_db):
    _log("WIN", "NORMAL")
    _log("LOSS", "OTC")
    assert db.get_win_rate("NORMAL") == (1.0, 1)
    assert db.get_win_rate("OTC") == (0.0, 1)
