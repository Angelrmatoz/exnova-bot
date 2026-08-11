"""Tests de la sesión de trading: regla de 3 operaciones (session.py).

La regla: parar con 2 WINs, 2 LOSSes o 3 operaciones (lo que primero).
Se testea la lógica pura y el flujo completo sobre MockBrokerAdapter.
"""

import pandas as pd
import pytest

from bot.broker.mock import MockBrokerAdapter
from bot.menu import choose_stake
from bot.session import (
    MIN_BODY_PCT,
    confirmed_signal,
    normalize_result,
    run_session,
    should_stop,
    signal_for,
)


def _frame(closes, opens):
    return pd.DataFrame(
        {
            "time": list(range(len(closes))),
            "open": opens,
            "close": closes,
            "high": [max(o, c) for o, c in zip(opens, closes)],
            "low": [min(o, c) for o, c in zip(opens, closes)],
        }
    )


def test_should_stop_limites():
    assert not should_stop(0, 0, 0)
    assert not should_stop(1, 1, 2)
    assert should_stop(2, 0, 2)   # 2 WINs → take-profit de sesión
    assert should_stop(0, 2, 2)   # 2 LOSSes → stop-loss de sesión
    assert should_stop(1, 1, 3)   # tope de 3 operaciones
    assert should_stop(1, 1, 5)   # nunca sobrepasa el tope


def test_normalize_result_unifica_brokers():
    assert normalize_result("win") == "WIN"
    assert normalize_result("WIN") == "WIN"
    assert normalize_result("loose") == "LOSS"
    assert normalize_result("lose") == "LOSS"
    assert normalize_result("equal") == "DRAW"
    assert normalize_result("tie") == "DRAW"


def test_signal_for_direccion():
    assert signal_for(1.1, 1.0)[0] == "call"
    assert signal_for(0.9, 1.0)[0] == "put"


def _candle(open_, close):
    return {"time": 0.0, "open": open_, "close": close}


def test_confirmed_signal_requiere_previo():
    assert confirmed_signal(_candle(1.0, 1.1), None) is None


def test_confirmed_signal_doji_se_descarta():
    candle = _candle(1.0, 1.0 + MIN_BODY_PCT / 2)
    assert confirmed_signal(candle, _candle(1.0, 1.0)) is None


def test_confirmed_signal_direccion_opuesta_se_descarta():
    assert confirmed_signal(_candle(1.0, 1.1), _candle(1.0, 0.9)) is None


def test_confirmed_signal_confirma_direccion():
    side, _ = confirmed_signal(_candle(1.0, 1.1), _candle(1.0, 1.05))
    assert side == "call"


def test_confirmed_signal_respeta_umbral():
    big = 10.0 * MIN_BODY_PCT
    assert confirmed_signal(_candle(1.0, 1.0 + big), _candle(1.0, 1.0 + big)) is not None


def test_choose_stake_valida_rango(monkeypatch):
    inputs = iter(["0", "25000", "20,000", "abc", "50"])
    monkeypatch.setattr("builtins.input", lambda _=None: next(inputs))
    assert choose_stake(1.0, 20000.0) == 50.0


def test_choose_stake_acepta_extremos(monkeypatch):
    inputs = iter(["1", "20000.00", "20000"])
    monkeypatch.setattr("builtins.input", lambda _=None: next(inputs))
    assert choose_stake(1.0, 20000.0) == 1.0
    assert choose_stake(1.0, 20000.0) == pytest.approx(20000.0)
    assert choose_stake(1.0, 20000.0) == pytest.approx(20000.0)


def test_choose_stake_acepta_decimales(monkeypatch):
    inputs = iter(["20,000.45", "18370.45"])
    monkeypatch.setattr("builtins.input", lambda _=None: next(inputs))
    assert choose_stake(1.0, 20000.0) == pytest.approx(18370.45)


def test_run_session_para_con_2_wins():
    df = _frame([1.0, 1.1, 1.2, 1.3], [0.9, 1.0, 1.1, 1.2])
    broker = MockBrokerAdapter({"EURUSD": df})
    res = run_session(broker, ["EURUSD"], "1m", 10.0, wait=False)
    assert res["wins"] == 2
    assert res["losses"] == 0
    assert res["trades"] == 2
    assert res["pnl"] > 0


def test_run_session_para_con_2_losses():
    df = _frame([1.0, 1.1, 0.9, 1.0], [0.9, 1.0, 1.1, 1.0])
    broker = MockBrokerAdapter({"EURUSD": df})
    res = run_session(broker, ["EURUSD"], "1m", 10.0, wait=False)
    assert res["wins"] == 0
    assert res["losses"] == 2
    assert res["trades"] == 2
    assert res["pnl"] < 0


def test_run_session_no_supera_3_trades():
    data = {
        "EURUSD": _frame([1.0, 1.1, 0.9, 1.0], [0.9, 1.0, 1.1, 1.2]),
        "GBPUSD": _frame([1.3, 1.2, 1.1, 1.0], [1.2, 1.3, 1.2, 1.1]),
    }
    broker = MockBrokerAdapter(data)
    res = run_session(broker, ["EURUSD", "GBPUSD"], "1m", 10.0, wait=False)
    assert res["trades"] <= 3
