"""Estudio read-only: senales de la hora 13 en dias con evento tier-1 USD.

Sin calendario historico: el evento se detecta por su firma en precio, el
rango 5m de las 13:30-13:40 UTC (hora tipica de NFP/CPI/PCE/GDP) comparado
con la mediana movil de 20 dias. Los pares USD reaccionan a la vez; se usa la
mediana entre pares para que un spike idiosincratico no marque el dia.

uv run python -m bot.scripts.event_filter_study
uv run python -m bot.scripts.event_filter_study --threshold 2.5
"""

import argparse
import math

import pandas as pd

from bot.scripts.signal_report import DATA, DEFAULT_PAIRS, load_signals

EVENT_START = 13 * 3600 + 25 * 60
EVENT_END = 13 * 3600 + 45 * 60
REACTION_START = 13 * 3600 + 30 * 60
REACTION_END = 13 * 3600 + 40 * 60
PAYOUT = 0.86


def wilson(wins: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = wins / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    m = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((c - m) / d, (c + m) / d)


def load_ranges() -> pd.DataFrame:
    frames = []
    for pair in DEFAULT_PAIRS:
        path = DATA / f"{pair}.csv"
        if not path.exists():
            continue
        df = pd.read_csv(path)
        df["pair"] = pair
        frames.append(df[["time", "high", "low", "pair"]])
    allp = pd.concat(frames, ignore_index=True)
    allp["rng"] = allp["high"] - allp["low"]
    allp["day"] = pd.to_datetime(allp["time"], unit="s").dt.strftime("%Y-%m-%d")
    allp["sec"] = allp["time"] % 86400
    return allp


def event_days(allp: pd.DataFrame) -> pd.Series:
    """Rango mediano entre pares en 13:30-13:40 / mediana movil 20 dias."""
    reaction = allp[(allp["sec"] >= REACTION_START) & (allp["sec"] < REACTION_END)]
    per_day = reaction.groupby(["day", "pair"])["rng"].mean().unstack()
    ratio = per_day.median(axis=1) / per_day.median(axis=1).rolling(20, min_periods=10).median()
    return ratio.dropna()


def _agg(sel: pd.DataFrame, label: str) -> None:
    n = len(sel)
    if n == 0:
        print(f"{label:<34} n=0")
        return
    w = sel["win"].mean()
    lo, hi = wilson(int(sel["win"].sum()), n)
    print(
        f"{label:<34} n={n:>3}  win={w:6.1%}  IC95 {lo:4.1%}-{hi:4.1%}"
        f"  exp86={w * PAYOUT - (1 - w):+.3f}"
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--threshold", type=float, default=2.0)
    args = ap.parse_args()

    allp = load_ranges()
    ratio = event_days(allp)
    events = set(ratio[ratio >= args.threshold].index)
    print(f"dias con evento (ratio >= {args.threshold}): {len(events)} de {len(ratio)}")
    print("ultimos 10 eventos:", ", ".join(sorted(events)[-10:]))

    frames = [load_signals(p) for p in DEFAULT_PAIRS if (DATA / f"{p}.csv").exists()]
    sig = pd.concat(frames, ignore_index=True)
    sig["day"] = pd.to_datetime(sig["time"], unit="s").dt.strftime("%Y-%m-%d")
    sig["is_event"] = sig["day"].isin(events)
    h13 = sig[sig["hour"] == 13]
    hctl = sig[sig["hour"].isin((8, 9, 10))]

    print(f"\n=== hora 13: {len(h13)} senales, {h13['is_event'].sum()} en dia de evento ===")
    _agg(h13[~h13["is_event"]], "h13 dia limpio")
    _agg(h13[h13["is_event"]], "h13 dia de evento")

    print("\n=== hora 13, bloque 13:25-13:45 (entrada en reaccion) ===")
    in_block = h13[(h13["time"] % 86400 >= EVENT_START) & (h13["time"] % 86400 < EVENT_END)]
    _agg(in_block, "h13 dentro del bloque")
    _agg(h13[~h13.index.isin(in_block.index)], "h13 fuera del bloque")

    print("\n=== control horas 8-10 (el evento no deberia afectar) ===")
    _agg(hctl[~hctl["is_event"]], "h8-10 dia limpio")
    _agg(hctl[hctl["is_event"]], "h8-10 dia de evento")

    print("\n=== sensibilidad del umbral (h13 evento vs limpio) ===")
    for t in (1.5, 2.0, 2.5, 3.0):
        ev = set(ratio[ratio >= t].index)
        sel = h13[h13["day"].isin(ev)]
        other = h13[~h13["day"].isin(ev)]
        we = sel["win"].mean() if len(sel) else float("nan")
        wo = other["win"].mean() if len(other) else float("nan")
        print(f"umbral {t:>3}: evento n={len(sel):>3} win={we:6.1%} | limpio n={len(other):>3} win={wo:6.1%}")
    return 0


def _selftest() -> None:
    lo, hi = wilson(8, 10)
    assert lo < 0.8 < hi and lo > 0.4
    assert wilson(0, 0) == (0.0, 0.0)


if __name__ == "__main__":
    _selftest()
    raise SystemExit(main())
