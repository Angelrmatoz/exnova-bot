"""Helpers compartidas de WebSocket para los mock servers de los tests."""

import base64
import hashlib
import json
import struct
import threading
import time

WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


def _read_accept(key: str) -> str:
    return base64.b64encode(hashlib.sha1((key + WS_GUID).encode()).digest()).decode()


def _frame(opcode: int, payload: bytes) -> bytes:
    b0 = 0x80 | opcode
    n = len(payload)
    if n < 126:
        header = bytes([b0, n])
    elif n < 65536:
        header = bytes([b0, 126]) + struct.pack(">H", n)
    else:
        header = bytes([b0, 127]) + struct.pack(">Q", n)
    return header + payload


class ClientConn:
    """Conexión aceptada por el servidor; lee frames enmascarados del cliente."""

    def __init__(self, sock):
        self.sock = sock
        self.closed = threading.Event()
        self._buf = b""

    def _exact(self, n):
        while len(self._buf) < n:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("cliente cerró conexión")
            self._buf += chunk
        data, self._buf = self._buf[:n], self._buf[n:]
        return data

    def recv_json(self):
        b0 = self._exact(1)[0]
        if b0 == 0x88:
            self.closed.set()
            return None
        if b0 == 0x89:
            length = self._exact(1)[0] & 0x7F
            payload = self._exact(length)
            self.sock.sendall(_frame(0xA, payload))
            return self.recv_json()
        b1 = self._exact(1)[0]
        masked = bool(b1 & 0x80)
        length = b1 & 0x7F
        if length == 126:
            length = struct.unpack(">H", self._exact(2))[0]
        elif length == 127:
            length = struct.unpack(">Q", self._exact(8))[0]
        mask = self._exact(4) if masked else None
        payload = bytearray(self._exact(length))
        if mask:
            for i in range(length):
                payload[i] ^= mask[i % 4]
        try:
            return json.loads(bytes(payload))
        except json.JSONDecodeError:
            return None

    def send_json(self, obj):
        self.sock.sendall(_frame(0x1, json.dumps(obj).encode()))

    def close(self):
        self.closed.set()
        try:
            self.sock.close()
        except OSError:
            pass


def wait_for(predicate, timeout=5.0, interval=0.01):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()
