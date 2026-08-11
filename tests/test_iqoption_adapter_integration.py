"""Paridad: IqOptionAdapter (BrokerClient) sobre IqOptionWSClient contra el mock server."""

import pytest


def _connect(adapter):
    adapter._client._start()
    assert adapter._client._connected.is_set()


def test_adapter_get_candles(iq_adapter, iq_mock_server):
    _connect(iq_adapter)
    candles = iq_adapter.get_candles("EURUSD-OTC", "5m", 10)
    assert len(candles) == len(iq_mock_server.candles)
    required = {"time", "open", "close", "high", "low"}
    assert required <= set(candles[0].keys())
    assert candles[0]["time"] == iq_mock_server.candles[0]["from"]


def test_adapter_get_available_assets(iq_adapter):
    _connect(iq_adapter)
    assert iq_adapter.get_available_assets() == ["EURUSD-OTC"]


def test_adapter_buy_and_result_loose(iq_adapter, iq_mock_server):
    _connect(iq_adapter)
    order_id = iq_adapter.place_order("EURUSD-OTC", "call", 1.0, "1m")
    assert order_id is not None and order_id.startswith("op-")
    iq_mock_server.push_position_changed(order_id, result="loose", amount=1.0)
    win, pnl = iq_adapter.check_result(order_id)
    assert win == "loose"
    assert pnl == pytest.approx(-1.0)


def test_adapter_buy_rejects_on_error(iq_adapter, iq_mock_server):
    _connect(iq_adapter)

    def fail_order(conn, req_id):
        conn.send_json({"name": "option", "msg": {"message": "too fast"}, "request_id": req_id})

    iq_mock_server._deliver_order = fail_order
    assert iq_adapter.place_order("EURUSD-OTC", "call", 1.0, "1m") is None


def test_adapter_balance_and_payout(iq_adapter):
    _connect(iq_adapter)
    assert iq_adapter.get_balance() == pytest.approx(10000.0)
    assert iq_adapter.get_payout("EURUSD-OTC") == pytest.approx(0.86)


def test_adapter_check_connect(iq_adapter):
    assert iq_adapter.check_connect() is False
    _connect(iq_adapter)
    assert iq_adapter.check_connect() is True
