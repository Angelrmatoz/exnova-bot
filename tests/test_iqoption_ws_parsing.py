"""Tests unitarios de IqOptionWSClient: parsing de mensajes y helpers sin red."""

import json
import time

import pytest

from bot.broker.iqoption_ws import IqOptionWSClient, get_expiration_time


class FakeApp:
    def __init__(self):
        self.sent = []

    def send(self, raw):
        self.sent.append(json.loads(raw))


def client_factory(**kwargs):
    c = IqOptionWSClient(kwargs.pop("ssid", "test"), kwargs.pop("account_type", "PRACTICE"))
    for k, v in kwargs.items():
        setattr(c, k, v)
    return c


def feed(client, name, msg, request_id="9"):
    client._on_message(None, json.dumps({"name": name, "msg": msg, "request_id": request_id}))


def respond(client, name, msg):
    def fake_send(name_, msg_, request_id=""):
        client._on_message(None, json.dumps({"name": name, "msg": msg, "request_id": request_id}))

    client._send = fake_send


def test_timeframe_helpers():
    assert IqOptionWSClient._to_seconds("1m") == 60
    assert IqOptionWSClient._to_seconds("1h") == 3600
    assert IqOptionWSClient._to_minutes("90s") == 2
    assert IqOptionWSClient._to_minutes("1m") == 1


def test_expiration_aligned_and_margin():
    ts = 1_786_237_700
    exp = get_expiration_time(ts, 60)
    assert exp > ts
    assert exp % 60 == 0
    assert exp - ts >= 30


def test_expiration_adds_step_when_close():
    ts = 1_786_237_720  # 20s antes del cierre -> margen < 30
    exp = get_expiration_time(ts, 60)
    assert exp - ts >= 30
    assert exp % 60 == 0


def test_authenticated_sets_event():
    c = client_factory()
    feed(c, "authenticated", True)
    assert c._auth_event.is_set()


def test_time_sync_sets_timestamp():
    c = client_factory()
    feed(c, "timeSync", 1700000000000)
    assert c.server_timestamp == 1700000000.0
    assert c._ts_event.is_set()


def test_candles_stored():
    c = client_factory()
    candles = [{"from": 1, "open": 1.0, "close": 1.0, "max": 1.0, "min": 1.0}]
    feed(c, "candles", {"candles": candles})
    assert c._candles_data == candles
    assert c._candles_event.is_set()


def test_first_candles_stored():
    c = client_factory()
    feed(c, "first-candles", [{"from": 1}])
    assert c._first_candles_data == [{"from": 1}]
    assert c._first_candles_event.is_set()


def test_balances_stored():
    c = client_factory()
    feed(c, "balances", [{"id": 4, "amount": 100}])
    assert c._balances_data[0]["id"] == 4
    assert c._balances_event.is_set()


def test_underlying_stored():
    c = client_factory()
    feed(c, "underlying-list", {"underlying": [{"name": "EURUSD-OTC"}]})
    assert c._underlying_data == [{"name": "EURUSD-OTC"}]
    assert c._underlying_event.is_set()


def test_trading_params_stored():
    c = client_factory()
    feed(c, "trading-params", {"commissions": [{"active_id": 76, "value": 14}]})
    assert c._trading_params_data["commissions"][0]["value"] == 14
    assert c._trading_params_event.is_set()


def test_positions_and_history_positions_stored():
    c = client_factory()
    feed(c, "positions", [{"id": 1}])
    assert c._positions_data == [{"id": 1}]
    c._positions_event.clear()
    feed(c, "history-positions", {"positions": [{"id": 2}]})
    assert c._positions_data == {"positions": [{"id": 2}]}
    assert c._positions_event.is_set()


def test_initialization_data_stored():
    c = client_factory()
    feed(c, "initialization-data", {"binary": {}})
    assert c._init_data == {"binary": {}}
    assert c._init_event.is_set()


def test_candle_generated_realtime():
    c = client_factory()
    c._actives = {"EURUSD-OTC": 76}
    feed(c, "candle-generated", {"active_id": 76, "size": 60, "close": 1.23})
    assert c.get_realtime_candle("EURUSD-OTC", 60)["close"] == 1.23
    assert c.get_realtime_candle("EURUSD-OTC", 999) is None


def test_option_message_by_request():
    c = client_factory()
    feed(c, "option", {"id": "op-1"}, request_id="777")
    assert c._buy_option["777"]["id"] == "op-1"


def test_result_message():
    c = client_factory()
    feed(c, "result", {"success": True})
    assert c._buy_result is True


def test_position_changed_win_stores_closed():
    c = client_factory()
    feed(c, "position-changed", {"raw_event": {
        "binary_options_option_changed1": {
            "option_id": 7, "result": "win", "amount": 1.0, "profit_amount": 1.86,
        }}})
    assert c._closed["7"]["result"] == "win"


def test_position_changed_opened_ignored():
    c = client_factory()
    feed(c, "position-changed", {"raw_event": {
        "binary_options_option_changed1": {"option_id": 7, "result": "opened"}}})
    assert "7" not in c._closed


def test_position_changed_no_option_id_noop():
    c = client_factory()
    feed(c, "position-changed", {"raw_event": {
        "binary_options_option_changed1": {"result": "win"}}})
    assert c._closed == {}


def test_check_result_win():
    c = client_factory()
    feed(c, "position-changed", {"raw_event": {
        "binary_options_option_changed1": {
            "option_id": 7, "result": "win", "amount": 1.0, "profit_amount": 1.86}}})
    result, pnl = c.check_result("7", timeout=1)
    assert result == "win"
    assert pnl == pytest.approx(1.86)


def test_check_result_loose():
    c = client_factory()
    feed(c, "position-changed", {"raw_event": {
        "binary_options_option_changed1": {
            "option_id": 8, "result": "loose", "amount": 1.0}}})
    result, pnl = c.check_result("8", timeout=1)
    assert result == "loose"
    assert pnl == pytest.approx(-1.0)


def test_check_result_tie():
    c = client_factory()
    feed(c, "position-changed", {"raw_event": {
        "binary_options_option_changed1": {
            "option_id": 9, "result": "tie", "amount": 1.0}}})
    result, pnl = c.check_result("9", timeout=1)
    assert result == "tie"
    assert pnl == 0.0


def test_check_result_timeout_raises():
    c = client_factory()
    with pytest.raises(TimeoutError):
        c.check_result("nope", timeout=0.1)


def test_send_with_app_none_noop():
    c = client_factory()
    c._send_raw({"name": "x"})


def test_send_build_payload():
    c = client_factory()
    c._app = FakeApp()
    c._send("hello", {"a": 1}, request_id="42")
    assert c._app.sent == [{"name": "hello", "msg": {"a": 1}, "request_id": "42"}]


def test_send_auto_request_id():
    c = client_factory()
    c._app = FakeApp()
    c._send("hello", {})
    sent = c._app.sent[0]
    assert sent["name"] == "hello"
    assert isinstance(sent["request_id"], int)


def test_non_json_frame_ignored():
    c = client_factory()
    c._on_message(None, "{not json")


def test_unknown_name_ignored():
    c = client_factory()
    c._on_message(None, json.dumps({"name": "completely-unknown", "msg": {}}))


def test_get_candles_normalized():
    c = client_factory()
    c._actives = {"EURUSD-OTC": 76}
    c.server_timestamp = 1_700_000_000
    respond(c, "candles", {"candles": [
        {"from": 300, "open": 1.0, "close": 1.1, "max": 1.2, "min": 0.9}]})
    candles = c.get_candles("EURUSD-OTC", "5m", 10)
    assert candles[0] == {"time": 300, "open": 1.0, "close": 1.1, "high": 1.2, "low": 0.9}


def test_get_available_assets_filters_suspended():
    c = client_factory()
    respond(c, "underlying-list", {"underlying": [
        {"name": "EURUSD-OTC", "is_suspended": False},
        {"name": "GBPUSD-OTC", "is_suspended": True},
    ]})
    assert c.get_available_assets() == ["EURUSD-OTC"]


def test_get_payout_commission():
    c = client_factory()
    c._actives = {"EURUSD-OTC": 76}
    respond(c, "trading-params", {"commissions": [{"active_id": 76, "value": 14}]})
    assert c.get_payout("EURUSD-OTC") == pytest.approx(0.86)


def test_get_balances_timeout_raises():
    c = client_factory()
    with pytest.raises(TimeoutError):
        c.get_balances(timeout=0.01)
