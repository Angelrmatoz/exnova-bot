"""Tests unitarios de ExnovaWSClient: parsing de mensajes y helpers sin red."""

import json
import time

import pytest

from bot.broker import exnova_ws
from bot.broker.exnova_ws import ExnovaWSClient, _asset_name, get_expiration_time


class FakeApp:
    def __init__(self):
        self.sent = []

    def send(self, raw):
        self.sent.append(json.loads(raw))


def client_factory(**kwargs):
    c = ExnovaWSClient(kwargs.pop("email", "t@t.com"), kwargs.pop("password", "pw"), "PRACTICE")
    for k, v in kwargs.items():
        setattr(c, k, v)
    return c


def feed(client, name, msg, request_id="9"):
    client._on_message(None, json.dumps({"name": name, "msg": msg, "request_id": request_id}))


def test_asset_name_variants():
    assert _asset_name("EUR.USD-OTC") == "USD-OTC"
    assert _asset_name("XAU.USD") == "USD"
    assert _asset_name("EURUSD") == "EURUSD"


def test_timeframe_helpers():
    assert ExnovaWSClient._to_seconds("1m") == 60
    assert ExnovaWSClient._to_seconds("5h") == 18000
    assert ExnovaWSClient._to_minutes("90s") == 2
    assert ExnovaWSClient._to_minutes("1m") == 1


def test_expiration_turbo_type():
    ts = int(time.time())
    exp, idx = get_expiration_time(ts, 1)
    assert isinstance(exp, int) and isinstance(idx, int)
    assert exp > ts
    # duración <=5m -> opción turbo (idx < 5)
    assert idx < 5


def test_expiration_more_than_5min_binary():
    ts = int(time.time())
    exp, idx = get_expiration_time(ts, 60)
    assert exp > ts
    # duración 60m -> apunta a una marca de 15m (idx >= 5)
    assert idx >= 5


def test_timestamp():
    from datetime import datetime
    assert int(exnova_ws._date_to_timestamp(datetime.now())) > 0


def test_profile_sets_balance_id():
    c = client_factory()
    feed(c, "profile", {"balances": [
        {"id": 1, "type": 1},
        {"id": 4, "type": 4},
    ]})
    assert c.profile["balances"][0]["type"] == 1
    assert c.balance_id == 4
    assert c._profile_event.is_set()


def test_time_sync_sets_timestamp():
    c = client_factory()
    feed(c, "timeSync", 1700000000000)
    assert c.server_timestamp == 1700000000.0
    assert c._ts_event.is_set()


def test_candles_stored_and_event():
    c = client_factory()
    assert c._candles_event is not None
    c._candles_event.clear()
    candles = [{"from": 1, "open": 1.0, "close": 1.0, "max": 1.0, "min": 1.0}]
    feed(c, "candles", {"candles": candles})
    assert c._candles_data == candles
    assert c._candles_event.is_set()


def test_balances_stored():
    c = client_factory()
    feed(c, "balances", [{"id": 4, "amount": 100}])
    assert c._balances_data[0]["id"] == 4
    assert c._balances_event.is_set()


def test_candle_generated_realtime():
    c = client_factory()
    c._actives = {"EURUSD": 100}
    feed(c, "candle-generated", {"active_id": 100, "size": 5, "close": 1.23})
    assert c.get_realtime_candle("EURUSD", 5)["close"] == 1.23
    assert c.get_realtime_candle("EURUSD", 999) is None


def test_buy_complete_success_and_fail():
    c = client_factory()
    feed(c, "buyComplete", {"isSuccessful": True, "result": {"id": "op-1"}}, request_id="555")
    assert c._buy_option["555"] == {"id": "op-1"}
    feed(c, "buyComplete", {"isSuccessful": False, "result": {}}, request_id="556")
    assert "556" not in c._buy_option


def test_option_message_assigns_by_request():
    c = client_factory()
    feed(c, "option", {"id": "op-2"}, request_id="777")
    assert c._buy_option["777"]["id"] == "op-2"


def test_result_message():
    c = client_factory()
    feed(c, "result", {"success": True})
    assert c._buy_result is True


def test_socket_option_closed_and_check_result_win():
    c = client_factory()
    feed(c, "socket-option-closed", {
        "id": "op-7",
        "msg": {"win": "win", "sum": 1.0, "win_amount": 1.8},
    })
    win, pnl = c.check_result("op-7", timeout=1)
    assert win == "win"
    assert pnl == pytest.approx(0.8)


def test_socket_option_closed_loose():
    c = client_factory()
    feed(c, "socket-option-closed", {
        "id": "op-8",
        "msg": {"win": "loose", "sum": 1.0, "win_amount": 0},
    })
    win, pnl = c.check_result("op-8", timeout=1)
    assert win == "loose"
    assert pnl == pytest.approx(-1.0)


def test_socket_option_closed_equal_zero():
    c = client_factory()
    feed(c, "socket-option-closed", {
        "id": "op-9",
        "msg": {"win": "equal", "sum": 1.0, "win_amount": 1.0},
    })
    win, pnl = c.check_result("op-9", timeout=1)
    assert win == "equal"
    assert pnl == 0.0


def test_sold_options_event():
    c = client_factory()
    feed(c, "sold-options", [{"id": 1}])
    assert c._sold == [{"id": 1}]
    assert c._sold_event.is_set()


def test_init_v2():
    c = client_factory()
    feed(c, "initialization-data", {"binary": {}})
    assert c._init_v2 == {"binary": {}}
    assert c._init_v2_event.is_set()


def test_init_all():
    c = client_factory()
    feed(c, "api_option_init_all_result", {"result": {}})
    assert c._init_all == {"result": {}}
    assert c._init_event.is_set()


def test_heartbeat_reply():
    c = client_factory()
    c._app = FakeApp()
    c.server_timestamp = 1700000000000  # ms
    feed(c, "heartbeat", 1700000000123)
    assert len(c._app.sent) == 1
    reply = c._app.sent[0]
    assert reply["name"] == "heartbeat"
    assert reply["msg"]["msg"]["heartbeatTime"] == 1700000000123
    assert reply["msg"]["msg"]["userTime"] == 1700000000000 * 1000


def test_non_json_frame_ignored():
    c = client_factory()
    c._on_message(None, "{not json")


def test_unknown_name_ignored():
    c = client_factory()
    c._on_message(None, json.dumps({"name": "completely-unknown", "msg": {}}))


def test_send_with_app_none_noop():
    c = client_factory()
    c._send_raw({"name": "x"})  # app None -> no op, no crash


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


def test_set_options():
    c = client_factory()
    c._app = FakeApp()
    c._set_options(True)
    assert c._app.sent[0] == {"name": "setOptions", "msg": {"sendResults": True}, "request_id": "1"}


def test_get_balances_timeout_raises():
    c = client_factory()
    with pytest.raises(TimeoutError):
        c.get_balances(timeout=0.01)