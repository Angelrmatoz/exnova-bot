"""Reporte de la senal exhaustion sobre CSVs 5m locales. Read-only.

uv run python -m bot.scripts.signal_report
uv run python -m bot.scripts.signal_report --pairs EURUSD-op
"""

import argparse
from pathlib import Path

import pandas as pd

from bot.ml.features import build_features

DATA = Path("data/5m")
HOURS = frozenset((8, 9, 10, 13))
DEFAULT_PAIRS = (
    "EURUSD-op",
    "NZDUSD-op",
    "EURGBP-op",
    "GBPUSD-op",
    "CADCHF-op",
)
Z_CUT = 2.2
PAYOUT = 0.86


def load_signals(pair: str) -> pd.DataFrame:
    df = pd.read_csv(DATA / f"{pair}.csv")
    f = build_features(df).dropna(subset=["rsi_14", "atr_14"]).reset_index(drop=True)
    close = f["close"]
    sma = close.rolling(20).mean()
    sd = close.rolling(20).std()
    rng = f["high"] - f["low"]
    body = (f["close"] - f["open"]).abs() / rng.replace(0, pd.NA)
    ok = (
        sd.notna()
        & (rng >= 2 * f["atr_14"])
        & (body >= 0.6)
        & ~((f["close"] < sma - 2 * sd) & (f["rsi_14"] < 25))
        & ~((f["close"] > sma + 2 * sd) & (f["rsi_14"] > 75))
    )
    up = ok & (f["close"] > sma + 2 * sd)
    dn = ok & (f["close"] < sma - 2 * sd)
    s = f[up | dn].copy()
    s["side"] = ["put" if u else "call" for u in up[up | dn]]
    s["z"] = rng[up | dn] / f["atr_14"][up | dn]
    s["hour"] = ((s["time"] + 300) // 3600) % 24
    s["entry"] = f["open"].shift(-1)[s.index]
    s["expiry"] = f["close"].shift(-6)[s.index]
    s = s.dropna(subset=["entry", "expiry"])
    s["win"] = (s["side"].eq("call") & (s["expiry"] > s["entry"])) | (
        s["side"].eq("put") & (s["expiry"] < s["entry"])
    )
    return s


def _agg(sel: pd.DataFrame, label: str) -> None:
    n = len(sel)
    if n == 0:
        print(f"{label:<24} n=0")
        return
    w = sel["win"].mean()
    exp = w * PAYOUT - (1 - w)
    print(f"{label:<24} n={n:>4}  win={w:6.1%}  exp86={exp:+.3f}")


def _streak(g: pd.DataFrame) -> int:
    run = worst = 0
    for w in g["win"]:
        run = run + 1 if not w else 0
        worst = max(worst, run)
    return worst


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", default=",".join(DEFAULT_PAIRS))
    args = ap.parse_args()
    pairs = args.pairs.split(",")

    frames = {}
    for p in pairs:
        path = DATA / f"{p}.csv"
        if not path.exists():
            print(f"{p}: sin CSV; se omite.")
            continue
        frames[p] = load_signals(p)
    if not frames:
        print("sin datos.")
        return 1

    prod = pd.concat([f[f["hour"].isin(HOURS)] for f in frames.values()])
    print(f"=== base (horas {sorted(HOURS)}) ===")
    for p, f in frames.items():
        _agg(f[f["hour"].isin(HOURS)], p)
    _agg(prod, "TOTAL")

    print("\n=== hora ===")
    for h in sorted(set(prod["hour"])):
        _agg(prod[prod["hour"] == h], f"h{h:02d}")

    print("\n=== buckets z ===")
    for lo, hi in [(2.0, 2.2), (2.2, 2.5), (2.5, 3.0), (3.0, 99)]:
        _agg(prod[(prod["z"] >= lo) & (prod["z"] < hi)], f"z {lo}-{hi}")
    _agg(prod[prod["z"] >= Z_CUT], f"z >= {Z_CUT}")

    print(f"\n=== robustez mensual: base vs z >= {Z_CUT} ===")
    by = prod.copy()
    by["mes"] = pd.to_datetime(by["time"], unit="s").dt.to_period("M")
    for mes, g in by.groupby("mes"):
        hi = g[g["z"] >= Z_CUT]
        print(
            f"{mes}  base {len(g):>3} {g['win'].mean():6.1%}  "
            f"| z>={Z_CUT} {len(hi):>3} "
            f"{(hi['win'].mean() if len(hi) else float('nan')):6.1%}"
        )

    print("\n=== rachas ===")
    print(f"base: perdida max {_streak(prod)}")
    print(f"z >= {Z_CUT}: perdida max {_streak(prod[prod['z'] >= Z_CUT])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
