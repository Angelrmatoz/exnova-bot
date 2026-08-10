"""Pruebas de integración: IqOptionWSClient contra un servidor WS local que emula IQ Option."""

import pytest

from wsutil import wait_for


def connect(iq_ws_client):
    iq_ws_client._start()
    assert iq_ws_client._connected.is_set()


def test_full_handshake(iq_ws_client):
    connect(iq_ws_client)
    assert iq_ws_client.balance_id == 4
    assert iq_ws_client.user_id == 42
    assert iq_ws_client.server_timestamp > 0


def test_get_available_assets(iq_ws_client):
    connect(iq_ws_client)
    assert iq_ws_client.get_available_assets() == ["EURUSD-OTC"]


def test_get_candles_normalized(iq_ws_client, iq_mock_server):
    connect(iq_ws_client)
    candles = iq_ws_client.get_candles("EURUSD-OTC", "5m", 10)
    assert len(candles) == len(iq_mock_server.candles)
    required = {"time", "open", "close", "high", "low"}
    assert required <= set(candles[0].keys())
    assert candles[0]["time"] == iq_mock_server.candles[0]["from"]
    assert candles[0]["high"] == iq_mock_server.candles[0]["max"]


def test_get_candles_unknown_asset_raises(iq_ws_client):
    connect(iq_ws_client)
    with pytest.raises(ValueError):
        iq_ws_client.get_candles("NOPE-NOPE", "5m", 10)


def test_buy_and_check_result_win(iq_ws_client, iq_mock_server):
    connect(iq_ws_client)
    ok, order_id = iq_ws_client.buy("EURUSD-OTC", "call", 1.0, "1m")
    assert ok is True
    assert order_id.startswith("op-")
    iq_mock_server.push_position_changed(order_id, result="win", amount=1.0, profit_amount=1.86)
    result, pnl = iq_ws_client.check_result(order_id, timeout=2)
    assert result == "win"
    assert pnl == pytest.approx(1.86)


def test_buy_and_check_result_loose(iq_ws_client, iq_mock_server):
    connect(iq_ws_client)
    ok, order_id = iq_ws_client.buy("EURUSD-OTC", "put", 1.0, "1m")
    assert ok is True
    iq_mock_server.push_position_changed(order_id, result="loose", amount=1.0)
    result, pnl = iq_ws_client.check_result(order_id, timeout=2)
    assert result == "loose"
    assert pnl == pytest.approx(-1.0)


def test_get_balance(iq_ws_client):
    connect(iq_ws_client)
    assert iq_ws_client.get_balance() == pytest.approx(10000.0)


def test_get_payout(iq_ws_client):
    connect(iq_ws_client)
    assert iq_ws_client.get_payout("EURUSD-OTC") == pytest.approx(0.86)


def test_subscribe_sends_first_candles_and_subscription(iq_ws_client, iq_mock_server):
    connect(iq_ws_client)
    iq_ws_client.subscribe("EURUSD-OTC", 60)
    assert wait_for(lambda: any(
        (m.get("msg") or {}).get("name") == "get-first-candles"
        for m in iq_mock_server.received
    ))
    assert wait_for(lambda: any(
        m["msg"]["name"] == "candle-generated"
        for m in iq_mock_server.subscriptions
    ))
    sub = next(m for m in iq_mock_server.subscriptions if m["msg"]["name"] == "candle-generated")
    assert sub["msg"]["params"]["routingFilters"]["active_id"] == "76"


def test_subscribe_position_changed_on_handshake(iq_ws_client, iq_mock_server):
    connect(iq_ws_client)
    assert wait_for(lambda: len(iq_mock_server.subscriptions) >= 1)
    sub = iq_mock_server.subscriptions[0]
    assert sub["msg"]["name"] == "portfolio.position-changed"


def test_realtime_candle_via_push(iq_ws_client, iq_mock_server):
    connect(iq_ws_client)
    iq_ws_client.subscribe("EURUSD-OTC", 300)
    iq_mock_server.push_candle_generated(active_id=76, size=300, close=1.234)
    assert wait_for(lambda: iq_ws_client.get_realtime_candle("EURUSD-OTC", 300) is not None)
    assert iq_ws_client.get_realtime_candle("EURUSD-OTC", 300)["close"] == 1.234


def test_reconnect_after_forced_disconnect(iq_ws_client, iq_mock_server):
    connect(iq_ws_client)
    first_accepted = iq_mock_server.accepted
    iq_mock_server.force_disconnect()
    assert wait_for(lambda: iq_mock_server.accepted > first_accepted, timeout=5)
    assert wait_for(lambda: iq_ws_client._connected.is_set(), timeout=5)
    assert iq_ws_client.server_timestamp > 0


def test_close_stops_threads(iq_ws_client):
    connect(iq_ws_client)
    iq_ws_client.close()
    assert iq_ws_client._stop.is_set()
