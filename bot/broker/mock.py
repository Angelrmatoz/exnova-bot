"""MockBrokerAdapter: BrokerClient que resuelve órdenes sobre velas históricas.

Permite backtesting del ciclo completo (velas → señal → orden → resultado)
sin conexión a ningún bróker. Recibe un dict par → DataFrame OHLC
(time epoch seg + open/close/high/low). El cursor simula la vela cerrada
actual; una orden con duración D se resuelve con la vela en D segundos.

Es un adaptador de prueba (Fase 3): no conecta a nada, no usa red.
"""

from __future__ import annotations

import uuid
from collections import OrderedDict
from typing import Any

import pandas as pd

from bot.broker.base import BrokerClient


class MockBrokerAdapter(BrokerClient):
    def __init__(
        self,
        data: dict[str, pd.DataFrame],
        initial_balance: float = 1000.0,
        default_payout: float = 0.80,
        payouts: dict[str, float] | None = None,
    ):
        self._data = {pair: df.copy().reset_index(drop=True) for pair, df in data.items()}
        self._idx: dict[str, int] = {pair: 1 for pair in self._data}
        self._initial_balance = initial_balance
        self._default_payout = default_payout
        self._payouts = payouts or {}
        self._orders: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._results: dict[str, tuple[str, float]] = {}

    def _frame(self, pair: str) -> pd.DataFrame:
        try:
            return self._data[pair]
        except KeyError:
            raise KeyError(f"Par no cargado en el mock: {pair}")

    def set_cursor(self, pair: str, idx: int) -> None:
        n = len(self._frame(pair))
        self._idx[pair] = max(1, min(idx, n - 2))

    def cursor(self, pair: str) -> int:
        return self._idx[pair]

    def get_candles(self, pair: str, timeframe: str, count: int) -> list[dict[str, Any]]:
        idx = self._idx[pair]
        start = max(0, idx - count)
        frame = self._frame(pair).iloc[start:idx]
        return frame[["time", "open", "close", "high", "low"]].to_dict("records")

    def get_available_assets(self) -> list[str]:
        return sorted(self._data)

    def place_order(self, pair: str, side: str, amount: float, duration: str) -> str | None:
        steps = max(1, round(self._to_seconds(duration) / 300))
        expiry = self._idx[pair] + steps
        if expiry >= len(self._frame(pair)):
            return None
        order_id = uuid.uuid4().hex
        self._orders[order_id] = {
            "pair": pair,
            "side": side.lower(),
            "amount": amount,
            "expiry": expiry,
        }
        return order_id

    def check_result(self, order_id: str) -> tuple[str, float]:
        if order_id in self._results:
            return self._results[order_id]
        order = self._orders[order_id]
        frame = self._frame(order["pair"])
        row = frame.iloc[order["expiry"]]
        win = (row["close"] > row["open"]) if order["side"] == "call" else (row["close"] < row["open"])
        amount = order["amount"]
        pnl = self.get_payout(order["pair"]) * amount if win else -amount
        result = ("WIN", pnl) if win else ("LOSS", pnl)
        self._results[order_id] = result
        return result

    def get_balance(self) -> float:
        realized = sum(pnl for _, pnl in self._results.values())
        return self._initial_balance + realized

    def get_payout(self, pair: str) -> float:
        return self._payouts.get(pair, self._default_payout)

    @staticmethod
    def _to_seconds(timeframe: str) -> int:
        unit = timeframe[-1]
        value = int(timeframe[:-1])
        return {"s": 1, "m": 60, "h": 3600}[unit] * value