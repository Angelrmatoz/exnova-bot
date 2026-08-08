"""Paridad: ExnovaAdapter (BrokerClient) sobre ExnovaWSClient contra el mock server."""

import pytest

from bot.broker.exnova import ExnovaAdapter


def _connect(adapter):
    adapter._client._start()
    assert adapter._client._connected.is_set()


def test_adapter_get_candles(adapter, mock_server):
    _connect(adapter)
    candles = adapter.get_candles("USD-OTC", "5m", 10)
    assert len(candles) == len(mock_server.candles)
    required = {"time", "open", "close", "high", "low"}
    assert required <= set(candles[0].keys())
    assert candles[0]["time"] == mock_server.candles[0]["from"]


def test_adapter_get_available_assets_filters_otc(adapter, mock_server):
    mock_server.init = {
        "binary": {
            "actives": {
                "1": {"name": "EUR.USD-OTC", "enabled": True, "is_suspended": False},
                "2": {"name": "EUR.USD", "enabled": True, "is_suspended": False},
            }
        },
        "turbo": {"actives": {"100": {"name": "XAU.USD", "enabled": True, "is_suspended": False}}},
    }
    _connect(adapter)
    assert adapter.get_available_assets() == ["USD-OTC"]


def test_adapter_get_available_assets_normal(adapter, mock_server):
    adapter.market_type = "NORMAL"
    mock_server.init = {
        "binary": {
            "actives": {
                "1": {"name": "EUR.USD-OTC", "enabled": True, "is_suspended": False},
                "2": {"name": "EUR.USD", "enabled": True, "is_suspended": False},
            }
        },
        "turbo": {"actives": {"100": {"name": "EUR.USD", "enabled": True, "is_suspended": False}}},
    }
    _connect(adapter)
    assert adapter.get_available_assets() == ["USD"]


def test_adapter_buy_and_result(adapter):
    _connect(adapter)
    order_id = adapter.place_order("USD-OTC", "call", 1.0, "1m")
    assert order_id is not None and order_id.startswith("result-")
    win, pnl = adapter.check_result(order_id)
    assert win == "loose"
    assert pnl == pytest.approx(-1.0)


def test_adapter_balance_and_payout(adapter):
    _connect(adapter)
    assert adapter.get_balance() == pytest.approx(10000.0)
    payout = adapter.get_payout("USD-OTC")
    assert payout == 0.8


def test_adapter_check_connect(adapter):
    assert adapter.check_connect() is False
    _connect(adapter)
    assert adapter.check_connect() is True