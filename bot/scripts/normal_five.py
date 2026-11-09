"""Reversión 5m en NORMAL: exhaustion, 19-22 UTC, 5 pares.

uv run python -m bot.scripts.normal_five
uv run python -m bot.scripts.normal_five --dry-run
"""

import argparse
import time
from datetime import datetime, timezone

import pandas as pd

from bot.broker.factory import build_broker
from bot.db import get_win_rate, log_trade
from bot.ml.features import build_features
from bot.session import normalize_result, should_stop

PAIRS = ("EURUSD-op", "NZDUSD-op", "EURGBP-op")
HOURS_UTC = frozenset((8, 9, 10, 13))
MARKET = "NORMAL"
STEP = 300
MIN_PAYOUT = 0.86
MIN_SAMPLE = 30
MIN_WIN_RATE = 0.56
IDLE_LIMIT = 30 * 60


def exhaustion_signal(hist: list[dict]) -> tuple[str, float] | None:
    """Exhaustion puro: rango >= 2xATR, cuerpo >= 60%, cierre fuera de Bollinger.

    Excluye las velas que ya disparan la regla RSI para no mezclar señales.
    """
    if len(hist) < 30:
        return None
    df = build_features(pd.DataFrame(hist)).dropna(subset=["rsi_14", "atr_14"]).reset_index(drop=True)
    if len(df) < 20:
        return None
    close = df["close"]
    sma = close.rolling(20).mean().iloc[-1]
    sd = close.rolling(20).std().iloc[-1]
    if pd.isna(sma) or pd.isna(sd):
        return None
    row = df.iloc[-1]
    lo, hi = sma - 2 * sd, sma + 2 * sd
    rsi = row["rsi_14"]
    if (row["close"] < lo and rsi < 25) or (row["close"] > hi and rsi > 75):
        return None
    rng = row["high"] - row["low"]
    body = abs(row["close"] - row["open"]) / rng if rng else 0
    if rng >= 2 * row["atr_14"] and body >= 0.6:
        if row["close"] > hi:
            return "put", rng / row["atr_14"]
        if row["close"] < lo:
            return "call", rng / row["atr_14"]
    return None


def entry_hour(clock: float) -> int:
    return time.gmtime(clock + STEP).tm_hour


def scan(broker, pairs: list[str], clock: float) -> tuple[str, str, float] | None:
    for pair in pairs:
        try:
            candles = broker.get_candles(pair, "5m", 50)
        except Exception:
            continue
        if len(candles) < 2:
            continue
        hist = candles[:-1]
        if hist[-1]["time"] != clock:
            continue
        found = exhaustion_signal(hist)
        if found is not None:
            return pair, found[0], found[1]
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--stake", type=float, default=10000.0)
    ap.add_argument("--broker", default="exnova", choices=("exnova", "iqoption"))
    args = ap.parse_args()

    rate, resolved = get_win_rate(MARKET)
    if resolved >= MIN_SAMPLE and (rate or 0) < MIN_WIN_RATE:
        print(f"Kill-switch: win rate {rate:.1%} en {resolved} operaciones. No se opera.")
        return 1

    broker = build_broker(args.broker, "NORMAL", "PRACTICE")
    ok, reason = broker.connect()
    print("connect:", ok, reason, flush=True)
    if not ok:
        return 2

    try:
        balance = broker.get_balance()
        stake = round(args.stake, -2)
        low = [p for p in PAIRS if (broker.get_payout(p) or 0) < MIN_PAYOUT]
        closed = [p for p in PAIRS if p not in low and not broker.is_open(p)]
        pairs = [p for p in PAIRS if p not in low and p not in closed]
        print(f"balance={balance:,.2f} stake={stake:,.0f} pares={','.join(pairs)}", flush=True)
        if low:
            print(f"payout bajo: {','.join(low)}", flush=True)
        if closed:
            print(f"cerrados: {','.join(closed)}", flush=True)
        if not pairs:
            print("sin pares operables (cerrado); fin.", flush=True)
            return 0

        if args.dry_run:
            probe = broker.get_candles(pairs[0], "5m", 2) if pairs else []
            clock = probe[-2]["time"] if len(probe) >= 2 else None
            if clock:
                print(f"última cerrada={datetime.fromtimestamp(clock, timezone.utc):%H:%M} UTC"
                      f" entrada={entry_hour(clock):02d}h", flush=True)
            for pair in pairs:
                candles = broker.get_candles(pair, "5m", 50)
                sig = exhaustion_signal(candles[:-1]) if len(candles) > 30 else None
                print(f"[{pair}] señal={sig}", flush=True)
            return 0

        wins = losses = trades = 0
        pnl_total = 0.0
        prev = None
        idle_deadline = time.time() + IDLE_LIMIT
        while not should_stop(wins, losses, trades):
            clock = None
            for pair in pairs:
                try:
                    candles = broker.get_candles(pair, "5m", 2)
                except Exception as e:
                    print(f"velas error: {e}; reintento.", flush=True)
                    time.sleep(5)
                    continue
                if len(candles) >= 2:
                    clock = candles[-2]["time"]
                    break
            if clock is None:
                print("sin velas; fin.")
                break
            if clock == prev:
                if time.time() > idle_deadline:
                    print("sin velas nuevas; fin.")
                    break
                time.sleep(2)
                continue
            prev = clock
            idle_deadline = time.time() + IDLE_LIMIT
            hour = entry_hour(clock)
            if hour not in HOURS_UTC:
                if hour > max(HOURS_UTC):
                    print("ventana cerrada; fin.")
                    break
                time.sleep(5)
                continue
            found = scan(broker, pairs, clock)
            if found is None:
                print(f"vela {clock:.0f}: sin setup.", flush=True)
                continue
            pair, side, conf = found
            if not broker.is_open(pair):
                print(f"[{pair}] cerrado; se omite.", flush=True)
                continue
            order_id = broker.place_order(pair, side, stake, "30m")
            if order_id is None:
                print(f"[{pair}] orden rechazada; fin.")
                break
            result, pnl = broker.check_result(order_id, timeout=2400)
            result = normalize_result(result)
            wins += result == "WIN"
            losses += result == "LOSS"
            trades += 1
            pnl_total += pnl
            log_trade(pair=pair, market_type=MARKET, signal=side, result=result, pnl=pnl,
                      confidence=conf, gate_passed="exhaustion")
            print(f"[{pair}] {side.upper()} -> {result} pnl {pnl:+.2f}  ({wins}W/{losses}L)", flush=True)
        print(f"=== NORMAL: {trades} ops, {wins}W {losses}L, pnl {pnl_total:+.2f}")
        return 0
    finally:
        broker.disconnect()


if __name__ == "__main__":
    raise SystemExit(main())
