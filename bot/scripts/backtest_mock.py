"""Backtest sin conexión usando MockBrokerAdapter + SQLite (Fase 3).

Carga CSVs de velas, simula el ciclo señal→orden→resultado contra el mock
bróker y registra cada operación en trade_logs. Útil para validar el flujo
completo (velas, adaptador, DB) con datos históricos reales sin tocar Exnova.

Estrategia incluida: momentum básico (CALL si la última vela cerró al alza,
PUT si a la baja). Curva de payouts por par vía CSV opcional.

Uso:
    uv run python -m bot.scripts.backtest_mock --pairs data/5m/EURUSD.csv,data/5m/GBPUSD.csv
    uv run python -m bot.scripts.backtest_mock --pairs data/5m/EURUSD.csv --payouts payouts.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from bot.broker.mock import MockBrokerAdapter
from bot.db import log_trades


def load_payouts(path: str | None) -> dict[str, float]:
    if not path:
        return {}
    df = pd.read_csv(path)
    return dict(zip(df["pair"], df["payout"]))


def signal_for(close: float, open_: float) -> tuple[str, float]:
    """Dirección + confianza proxy de la última vela cerrada."""
    direction = "call" if close > open_ else "put"
    magnitude = abs(close - open_) / open_
    confidence = min(0.5 + magnitude, 0.99)
    return direction, confidence


def main() -> None:
    parser = argparse.ArgumentParser(description="Backtest sobre MockBrokerAdapter")
    parser.add_argument("--pairs", required=True, help="CSV de velas (coma = varios)")
    parser.add_argument("--payout", type=float, default=0.80, help="Payout por defecto")
    parser.add_argument("--payouts", help="CSV con columnas pair,payout")
    parser.add_argument("--stake", type=float, default=10.0, help="Importe por operación")
    parser.add_argument("--no-db", action="store_true", help="No escribir en SQLite")
    args = parser.parse_args()

    payouts = load_payouts(args.payouts)
    data: dict[str, pd.DataFrame] = {}
    for path in args.pairs.split(","):
        pair = Path(path).stem
        data[pair] = pd.read_csv(path).sort_values("time").reset_index(drop=True)

    broker = MockBrokerAdapter(data, default_payout=args.payout, payouts=payouts)
    summary: dict[str, dict] = {}

    for pair, frame in data.items():
        trades = wins = pnl = 0
        rows = []
        for idx in range(1, len(frame) - 1):
            broker.set_cursor(pair, idx)
            row = frame.iloc[idx]
            side, confidence = signal_for(row["close"], row["open"])
            order_id = broker.place_order(pair, side, args.stake, "5m")
            if order_id is None:
                continue
            result, trade_pnl = broker.check_result(order_id)
            trades += 1
            pnl += trade_pnl
            wins += result == "WIN"
            if not args.no_db:
                rows.append(
                    {
                        "pair": pair,
                        "market_type": "MOCK",
                        "signal": side,
                        "confidence": confidence,
                        "gate_passed": "none",
                        "result": result,
                        "pnl": trade_pnl,
                    }
                )
        if rows:
            log_trades(rows)
        rate = wins / trades if trades else 0.0
        expectancy = pnl / trades if trades else 0.0
        summary[pair] = {
            "trades": trades,
            "wins": wins,
            "win_rate": rate,
            "pnl": pnl,
            "expectancy": expectancy,
            "payout": broker.get_payout(pair),
        }

    print(f"{'Par':<10}{'Trades':>8}{'WinRate':>10}{'Payout':>8}{'P&L':>10}{'Exp':>9}")
    total_pnl = total_trades = 0
    for pair, s in summary.items():
        total_pnl += s["pnl"]
        total_trades += s["trades"]
        print(
            f"{pair:<10}{s['trades']:>8}{s['win_rate']:>9.1%}"
            f"{s['payout']:>7.2f}{s['pnl']:>10.2f}{s['expectancy']:>9.3f}"
        )
    print(f"\nTotal: {total_trades} operaciones, P&L {total_pnl:.2f}")
    print(f"Balance final mock: {broker.get_balance():.2f}")


if __name__ == "__main__":
    main()