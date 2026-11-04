"""Anclas OTC operables y horarios de los pares de divisas OTC.

uv run python -m bot.scripts.anchor_scan
uv run python -m bot.scripts.anchor_scan --days 3 --min-ratio 20
uv run python -m bot.scripts.anchor_scan --fx
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from bot.anchor import LEAD_SECONDS
from bot.broker.exnova_ws import ExnovaWSClient, _asset_name
from bot.config import exnova_credentials
from bot.schedule import is_open, windows

ANCHORS_PATH = Path(__file__).with_name("otc_anchors.json")

CCY = {
    "AED", "ARS", "AUD", "BDT", "BOB", "BRL", "CAD", "CHF", "CLP", "COP",
    "DOP", "EUR", "GBP", "HKD", "IDR", "INR", "JPY", "MXN", "MYR", "NGN",
    "NOK", "NZD", "PHP", "PLN", "SAR", "SEK", "SGD", "THB", "TRY", "USD",
    "VND", "ZAR",
}


def is_fx(pair: str) -> bool:
    base = pair[:-4] if pair.endswith("-OTC") else pair
    return len(base) == 6 and base[:3] in CCY and base[3:] in CCY


def parse_anchor(text: str) -> int:
    hour, minute = text.split(":")
    return int(hour) * 3600 + int(minute) * 60


def open_windows(schedule: list | None, start: int, end: int) -> list[tuple[int, int]]:
    return [(max(s, start), min(e, end)) for s, e in windows(schedule) if e > start and s < end]


def fmt_windows(blocks: list[tuple[int, int]], day: int) -> str:
    def hm(ts: int) -> str:
        if ts == day + 86400:
            return "24:00"
        offset = (ts - day) // 86400
        text = datetime.fromtimestamp(ts, timezone.utc).strftime("%H:%M")
        return f"{text}+1d" if offset else text

    return ", ".join(f"{hm(s)}-{hm(e)}" for s, e in blocks) or "-"


def main() -> int:
    ap = argparse.ArgumentParser(description="Anclas OTC y horarios FX OTC.")
    ap.add_argument("--days", type=int, default=2, help="días a comprobar desde hoy")
    ap.add_argument("--min-ratio", type=float, default=10.0, help="salto mínimo sobre la mediana")
    ap.add_argument("--fx", action="store_true", help="solo horarios de pares FX")
    args = ap.parse_args()

    anchors = json.loads(ANCHORS_PATH.read_text(encoding="utf-8"))
    creds = exnova_credentials()
    client = ExnovaWSClient(creds["email"], creds["password"], account_type="PRACTICE")
    ok, reason = client.connect()
    if not ok:
        print(f"Error de conexión: {reason}")
        return 1

    try:
        data = client.get_all_init_v2()
        now = int(client.server_timestamp)
        actives: dict[str, dict] = {}
        for option in ("binary", "turbo"):
            for active in data.get(option, {}).get("actives", {}).values():
                name = _asset_name(active.get("name"))
                if not name.upper().endswith("-OTC"):
                    continue
                actives.setdefault(name, {
                    "schedule": active.get("schedule") or [],
                })
    finally:
        client.close()

    day0 = now // 86400 * 86400
    days = [day0 + i * 86400 for i in range(args.days)]

    if not args.fx:
        print(f"Anclas OTC con salto >= {args.min_ratio:g}x (UTC)")
        header = f"{'PAR':24s} {'ANCLA':>5s} {'SALTO':>7s}  " + "  ".join(
            datetime.fromtimestamp(d, timezone.utc).strftime("%a") for d in days
        )
        print(header)
        rows = []
        for pair, meta in anchors.items():
            active = actives.get(pair)
            if active is None:
                continue
            if meta["ratio"] < args.min_ratio:
                continue
            ts = [d + parse_anchor(meta["anchor"]) for d in days]
            opens = [
                is_open(active["schedule"], t - LEAD_SECONDS) and is_open(active["schedule"], t)
                for t in ts
            ]
            rows.append((any(opens), meta["ratio"], pair, meta["anchor"], opens))
        rows.sort(key=lambda r: (not r[0], -r[1]))
        for _, ratio, pair, anchor, opens in rows:
            marks = "  ".join(" SI" if o else " --" for o in opens)
            print(f"{pair:24s} {anchor:>5s} {ratio:>6.1f}x  {marks}")
        print(f"\n{len(rows)} anclas fuertes; {sum(1 for r in rows if r[0])} operables en los próximos {args.days} días.")

    fx = [p for p in actives if is_fx(p)]
    if fx:
        print("\nHorarios FX OTC (UTC): ventanas abiertas")
        print(f"{'PAR':24s} {'ANCLA':>5s}  {'HOY':26s}  MAÑANA")
        for pair in sorted(fx):
            active = actives[pair]
            anchor = anchors.get(pair, {}).get("anchor", "-")
            today = fmt_windows(open_windows(active["schedule"], day0, day0 + 86400), day0)
            tomorrow = fmt_windows(
                open_windows(active["schedule"], day0 + 86400, day0 + 172800), day0 + 86400
            )
            print(f"{pair:24s} {anchor:>5s}  {today:26s}  {tomorrow}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
