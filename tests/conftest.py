"""Fixtures y servidores WebSocket locales que emulan los protocolos de los brokers."""

import json
import socket
import threading
import time

import pytest

import bot.broker.exnova_ws as exnova_ws

from wsutil import ClientConn, _frame, _read_accept


def _active(name, active_id, enabled=True):
    return {
        "name": name,
        "id": active_id,
        "enabled": enabled,
        "is_suspended": False,
        "option": {"profit": {"commission": 20}},
    }


DEFAULT_INIT = {
    "binary": {
        "actives": {
            "1": _active("EUR.USD-OTC", 1),
            "2": _active("GBP.USD-OTC", 2, enabled=False),
            "3": _active("AUD.USD", 3),
        }
    },
    "turbo": {
        "actives": {
            "100": _active("EUR.USD", 100),
            "101": _active("XAU.USD", 101),
        }
    },
}

DEFAULT_CANDLES = [
    {"from": t, "open": 1.1000, "max": 1.1100, "min": 1.0900, "close": 1.1050,
     "size": 300, "active_id": 100}
    for t in range(1_700_000_000, 1_700_000_000 + 3000, 300)
]


class MockExnovaServer:
    """Servidor WS local: handshake + respuestas a los mensajes que el bot usa."""

    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.port = self.sock.getsockname()[1]
        self.url = f"ws://127.0.0.1:{self.port}/echo/websocket"
        self.sock.listen(5)

        self._accepting = True
        self._conns = []
        self._threads = []
        self.received = []
        self.accepted = 0

        self.profile = {"balances": [{"id": 4, "type": 4, "amount": 10000.0}]}
        self.init = DEFAULT_INIT
        self.candles = DEFAULT_CANDLES
        self.init_all = None
        self.subscriptions = []

        self._threads.append(threading.Thread(target=self._accept_loop, daemon=True))
        self._threads[-1].start()

    # -------------------------------------------------------------- handshake

    def _accept_loop(self):
        while self._accepting:
            try:
                client, _ = self.sock.accept()
            except OSError:
                return
            conn = ClientConn(client)
            self._conns.append(conn)
            self._threads.append(threading.Thread(target=self._session, args=(conn,), daemon=True))
            self._threads[-1].start()

    def _session(self, conn):
        try:
            request = b""
            while b"\r\n\r\n" not in request:
                chunk = conn.sock.recv(4096)
                if not chunk:
                    return
                request += chunk
            key = None
            for line in request.split(b"\r\n"):
                if line.lower().startswith(b"sec-websocket-key:"):
                    key = line.split(b":", 1)[1].strip().decode()
                    break
            if key is None:
                return
            conn.sock.sendall(
                "HTTP/1.1 101 Switching Protocols\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                f"Sec-WebSocket-Accept: {_read_accept(key)}\r\n\r\n".encode()
            )
            self.accepted += 1
            self._serve(conn)
        except OSError:
            pass
        finally:
            conn.close()

    # ------------------------------------------------------------ msg handling

    def _serve(self, conn):
        while not conn.closed.is_set():
            msg = conn.recv_json()
            if msg is None:
                return
            self.received.append(msg)
            self._dispatch(conn, msg)

    def _dispatch(self, conn, msg):
        name = msg.get("name")
        req_id = msg.get("request_id")
        if name == "ssid":
            conn.send_json({"name": "profile", "msg": self.profile, "request_id": req_id})
            conn.send_json({"name": "timeSync", "msg": int(time.time() * 1000), "request_id": req_id})
        elif name == "api_option_init_all":
            conn.send_json({"name": "api_option_init_all_result",
                            "msg": self.init_all or {"result": DEFAULT_INIT},
                            "request_id": req_id})
        elif name == "sendMessage":
            inner = msg.get("msg") or {}
            sub = inner.get("name")
            if sub == "get-candles":
                conn.send_json({"name": "candles", "msg": {"candles": self.candles}, "request_id": req_id})
            elif sub == "get-initialization-data":
                conn.send_json({"name": "initialization-data", "msg": self.init, "request_id": req_id})
            elif sub == "get-balances":
                conn.send_json({"name": "balances", "msg": self.profile["balances"], "request_id": req_id})
            elif sub == "binary-options.open-option":
                self._deliver_offer(conn, req_id)
            elif sub == "sell-options":
                conn.send_json({"name": "sold-options", "msg": [], "request_id": req_id})
        elif name == "subscribeMessage":
            self.subscriptions.append(msg)

    def _deliver_offer(self, conn, req_id):
        order = {"id": f"result-{req_id}", "msg": {"win": "loose", "sum": 1.0, "win_amount": 0}}
        conn.send_json({"name": "option", "msg": {"id": order["id"]}, "request_id": req_id})
        conn.send_json({"name": "result", "msg": {"success": True}, "request_id": req_id})
        conn.send_json({"name": "socket-option-closed", "msg": order, "request_id": req_id})

    @staticmethod
    def _send(conn, obj):
        conn.send_json(obj)

    # -------------------------------------------------------- test helpers

    def send_json(self, conn, obj):
        conn.send_json(obj)

    def force_disconnect(self):
        for conn in list(self._conns):
            conn.close()

    def wait_accepted(self, count=1, timeout=2.0):
        deadline = time.time() + timeout
        while self.accepted < count and time.time() < deadline:
            time.sleep(0.01)
        return self.accepted >= count

    def close(self):
        self._accepting = False
        for conn in list(self._conns):
            conn.close()
        try:
            self.sock.close()
        except OSError:
            pass
        for t in self._threads:
            t.join(timeout=1)


@pytest.fixture
def mock_server():
    server = MockExnovaServer()
    yield server
    server.close()


@pytest.fixture
def ws_client(mock_server, monkeypatch):
    monkeypatch.setattr(exnova_ws, "WSS_URL", mock_server.url)
    client = exnova_ws.ExnovaWSClient("t@t.com", "pw", "PRACTICE")
    client.ssid = "test"
    client.balance_id = 4
    yield client
    client.close()


@pytest.fixture
def adapter(mock_server, monkeypatch):
    from bot.broker.exnova import ExnovaAdapter

    monkeypatch.setattr(exnova_ws, "WSS_URL", mock_server.url)
    ad = ExnovaAdapter("t@t.com", "pw", account_type="PRACTICE", market_type="OTC")
    ad._client.ssid = "test"
    ad._client.balance_id = 4
    yield ad
    ad.disconnect()


@pytest.fixture
def iq_mock_server():
    from iq_mock import MockIqOptionServer

    server = MockIqOptionServer()
    yield server
    server.close()


@pytest.fixture
def iq_ws_client(iq_mock_server, monkeypatch):
    import bot.broker.iqoption_ws as iqoption_ws

    monkeypatch.setattr(iqoption_ws, "WSS_URL", iq_mock_server.url)
    client = iqoption_ws.IqOptionWSClient("test-ssid", account_type="PRACTICE")
    client._reconnect_backoff = 0.1
    client._max_backoff = 0.2
    yield client
    client.close()


@pytest.fixture
def iq_adapter(iq_mock_server, monkeypatch):
    import bot.broker.iqoption_ws as iqoption_ws
    from bot.broker.iqoption import IqOptionAdapter

    monkeypatch.setattr(iqoption_ws, "WSS_URL", iq_mock_server.url)
    ad = IqOptionAdapter("test-ssid", account_type="PRACTICE")
    yield ad
    ad.disconnect()