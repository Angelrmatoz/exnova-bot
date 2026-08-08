"""Pruebas de integración: ExnovaWSClient contra un servidor WS local que emula Exnova."""

import json
import time

import pytest

from bot.broker import exnova_ws


def wait_for(predicate, timeout=5.0, interval=0.01):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


def connect(ws_client):
    ws_client._start()
    assert ws_client._connected.is_set()


def test_full_handshake_and_profile(ws_client):
    connect(ws_client)
    assert ws_client.profile is not None
    assert ws_client.balance_id == 4
    assert ws_client.server_timestamp > 0


def test_get_available_assets(ws_client, mock_server):
    mock_server.init = {
        "binary": {
            "actives": {
                "1": {"name": "EUR.USD-OTC", "enabled": True, "is_suspended": False},
                "2": {"name": "GBP.USD-OTC", "enabled": False, "is_suspended": False},
                "3": {"name": "AUD.USD", "enabled": True, "is_suspended": True},
            }
        },
        "turbo": {"actives": {"100": {"name": "EUR.USD", "enabled": True, "is_suspended": False}}},
    }
    connect(ws_client)
    assets = ws_client.get_available_assets()
    assert assets == ["USD", "USD-OTC"]


def test_get_candles_normalized(ws_client, mock_server):
    connect(ws_client)
    candles = ws_client.get_candles("USD-OTC", "5m", 10)
    assert len(candles) == len(mock_server.candles)
    required = {"time", "open", "close", "high", "low"}
    assert required <= set(candles[0].keys())
    assert candles[0]["time"] == mock_server.candles[0]["from"]
    assert candles[0]["high"] == mock_server.candles[0]["max"]
    assert candles[0]["low"] == mock_server.candles[0]["min"]


def test_get_candles_unknown_asset_raises(ws_client):
    connect(ws_client)
    with pytest.raises(ValueError):
        ws_client.get_candles("NOPE-NOPE", "5m", 10)


def test_buy_and_check_result(ws_client, mock_server):
    connect(ws_client)
    ok, order_id = ws_client.buy("USD-OTC", "call", 1.0, "1m")
    assert ok is True
    assert order_id.startswith("result-")
    win, pnl = ws_client.check_result(order_id, timeout=2)
    assert win == "loose"
    assert pnl == pytest.approx(-1.0)


def test_sell(ws_client):
    connect(ws_client)
    assert ws_client.sell(["op-1"]) == []


def test_balance(ws_client, mock_server):
    connect(ws_client)
    assert ws_client.get_balance() == pytest.approx(10000.0)


def test_balance_zero_when_unknown(ws_client, mock_server):
    connect(ws_client)
    mock_server.profile = {"balances": [{"id": 999, "type": 4, "amount": 1.0}]}
    assert ws_client.get_balance() == 0.0


def test_subscribe_sends_message(ws_client, mock_server):
    connect(ws_client)
    ws_client.subscribe("USD-OTC", 300)
    assert wait_for(lambda: len(mock_server.subscriptions) >= 1)
    sub = mock_server.subscriptions[0]
    assert sub["msg"]["name"] == "candle-generated"
    assert sub["msg"]["params"]["routingFilters"]["active_id"] == "2"


def test_reconnect_after_forced_disconnect(ws_client, mock_server):
    ws_client._reconnect_backoff = 0.1
    ws_client._max_backoff = 0.2
    connect(ws_client)
    first_accepted = mock_server.accepted
    mock_server.force_disconnect()
    assert wait_for(lambda: mock_server.accepted > first_accepted, timeout=5)
    assert wait_for(lambda: ws_client._connected.is_set(), timeout=5)
    assert ws_client.server_timestamp > 0


def test_profile_setoptions_sent_on_connect(ws_client, mock_server):
    connect(ws_client)
    names = [m.get("name") for m in mock_server.received]
    assert "ssid" in names
    assert wait_for(lambda: any(m.get("name") == "setOptions" for m in mock_server.received))


def test_close_stops_threads(ws_client):
    connect(ws_client)
    ws_client.close()
    assert ws_client._stop.is_set()