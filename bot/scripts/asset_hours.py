"""Muestra las ventanas de apertura y cierres de los activos del bróker.

uv run python -m bot.scripts.asset_hours
uv run python -m bot.scripts.asset_hours AUDUSD-OTC GBPUSD-OTC --hours 48
"""

import argparse
import time
from datetime import datetime, timedelta, timezone

from bot.broker.exnova_ws import ExnovaWSClient, _asset_name
from bot.config import exnova_credentials
from bot.schedule import closure_around, is_open, next_close, next_open

ANCHORS = {
    "AUDUSD-OTC": (1, 10),
    "EURUSD-OTC": (8, 10),
    "USDCAD-OTC": (8, 10),
    "EURAUD-OTC": (8, 10),
    "CADCHF-OTC": (8, 10),
    "EURGBP-OTC": (4, 5),
    "EURJPY-OTC": (4, 5),
    "NZDUSD-OTC": (4, 5),
    "USDJPY-OTC": (4, 5),
    "GBPJPY-OTC": (4, 5),
    "GBPUSD-OTC": (4, 5),
}
REVERSION = [f"{b}-op" for b in (
    "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "EURGBP", "EURJPY",
    "GBPJPY", "USDCAD", "NZDUSD", "EURAUD", "CADCHF",
)]


def fmt(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%d-%m %H:%M")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("pairs", nargs="*", default=None)
    ap.add_argument("--hours", type=float, default=24.0)
    ap.add_argument("--anchors", action="store_true", help="solo los pares con anclaje")
    args = ap.parse_args()

    targets = args.pairs or (list(ANCHORS) if args.anchors else list(ANCHORS) + REVERSION)

    c = exnova_credentials()
    client = ExnovaWSClient(c["email"], c["password"], account_type="PRACTICE")
    ok, reason = client.connect()
    print("connect:", ok, reason)
    if not ok:
        return 2

    try:
        init = client.get_all_init_v2()
        now = client.server_timestamp
        horizon = now + args.hours * 3600
        assets = {}
        for a in init.get("binary", {}).get("actives", {}).values():
            assets[_asset_name(a["name"])] = a

        print(f"UTC ahora: {fmt(now)}   horizonte {args.hours:.0f}h\n")
        for name in targets:
            a = assets.get(name)
            if not a:
                print(f"{name:12} no existe")
                continue
            sched = a.get("schedule")
            estado = "ABIERTO" if is_open(sched, now) else "CERRADO"
            extra = ""
            if estado == "ABIERTO":
                close = next_close(sched, now)
                if close and close < horizon:
                    extra = f" cierra {fmt(close)}"
            else:
                gap = closure_around(sched, now)
                op = next_open(sched, now)
                if gap:
                    extra = f" hueco {fmt(gap[0])} .. {fmt(gap[1])}"
                elif op:
                    extra = f" abre {fmt(op)}"
            anchor = ANCHORS.get(name)
            if anchor:
                hh, mm = anchor
                t = datetime.now(timezone.utc).replace(hour=hh, minute=mm, second=0, microsecond=0)
                if t.timestamp() <= now:
                    t += timedelta(days=1)
                extra += f" | ancla {fmt(t.timestamp())}: " + (
                    "abierto" if is_open(sched, t.timestamp()) else "CERRADO"
                )
            print(f"{name:12} {estado:8}{extra}")
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
