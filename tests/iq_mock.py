"""MockIqOptionServer: servidor WS local que emula el protocolo mínimo de IQ Option."""

import socket
import threading
import time

from wsutil import ClientConn, _frame, _read_accept

DEFAULT_UNDERLYING = [
    {"name": "EURUSD-OTC", "active_id": 76, "is_suspended": False},
    {"name": "GBPUSD-OTC", "active_id": 78, "is_suspended": True},
]

DEFAULT_COMMISSIONS = [{"active_id": 76, "value": 14}]

DEFAULT_CANDLES = [
    {"from": t, "open": 1.1000, "max": 1.1100, "min": 1.0900, "close": 1.1050,
     "size": 300, "active_id": 76}
    for t in range(1_700_000_000, 1_700_000_000 + 3000, 300)
]


class MockIqOptionServer:
    """Emula el protocolo WS de IQ Option: auth por ssid, velas, órdenes y resultado."""

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

        self.underlying = DEFAULT_UNDERLYING
        self.commissions = DEFAULT_COMMISSIONS
        self.candles = DEFAULT_CANDLES
        self.balances = [{"id": 4, "type": 4, "amount": 10000.0, "user_id": 42}]
        self.init_data = {}
        self.positions = []
        self.subscriptions = []
        self.option_counter = [0]
        self.last_option_id = None

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
        if name == "authenticate":
            conn.send_json({"name": "authenticated", "msg": True, "request_id": req_id})
            conn.send_json({"name": "timeSync", "msg": int(time.time() * 1000), "request_id": req_id})
        elif name == "sendMessage":
            self._handle_send_message(conn, msg, req_id)
        elif name == "subscribeMessage":
            self.subscriptions.append(msg)

    def _handle_send_message(self, conn, msg, req_id):
        sub = (msg.get("msg") or {}).get("name")
        if sub == "internal-billing.get-balances":
            conn.send_json({"name": "balances", "msg": self.balances, "request_id": req_id})
        elif sub == "get-initialization-data":
            conn.send_json({"name": "initialization-data", "msg": self.init_data, "request_id": req_id})
        elif sub == "digital-option-instruments.get-underlying-list":
            conn.send_json({"name": "underlying-list", "msg": {"underlying": self.underlying}, "request_id": req_id})
        elif sub == "trading-settings.get-trading-group-params":
            conn.send_json({"name": "trading-params", "msg": {"commissions": self.commissions}, "request_id": req_id})
        elif sub == "get-candles":
            conn.send_json({"name": "candles", "msg": {"candles": self.candles}, "request_id": req_id})
        elif sub == "get-first-candles":
            conn.send_json({"name": "first-candles", "msg": self.candles, "request_id": req_id})
        elif sub == "binary-options.open-option":
            self._deliver_order(conn, req_id)
        elif sub == "portfolio.get-history-positions":
            conn.send_json({"name": "history-positions", "msg": {"positions": self.positions}, "request_id": req_id})

    def _deliver_order(self, conn, req_id):
        self.option_counter[0] += 1
        option_id = f"op-{self.option_counter[0]}"
        self.last_option_id = option_id
        conn.send_json({"name": "option", "msg": {"id": option_id}, "request_id": req_id})
        conn.send_json({"name": "result", "msg": {"success": True}, "request_id": req_id})

    def push_position_changed(self, option_id, result="win", amount=1.0, profit_amount=None):
        event = {"name": "position-changed", "msg": {"raw_event": {
            "binary_options_option_changed1": {
                "option_id": option_id, "result": result, "amount": amount,
                "profit_amount": profit_amount,
            }}}}
        for conn in list(self._conns):
            try:
                conn.send_json(event)
            except OSError:
                pass

    def push_candle_generated(self, active_id=76, size=300, close=1.2):
        event = {"name": "candle-generated", "msg": {
            "active_id": active_id, "size": size, "open": 1.1, "close": close,
            "min": 1.0, "max": 1.3,
        }}
        for conn in list(self._conns):
            try:
                conn.send_json(event)
            except OSError:
                pass

    # -------------------------------------------------------- test helpers

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
