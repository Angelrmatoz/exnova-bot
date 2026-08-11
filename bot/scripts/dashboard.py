"""Dashboard Streamlit sobre bot_data.db (Fase 6).

Uso: uv run streamlit run bot/scripts/dashboard.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd
import streamlit as st

from bot.db import get_trades


@st.cache_data(show_spinner=False)
def trades_frame() -> pd.DataFrame:
    df = pd.DataFrame(get_trades())
    if not df.empty:
        df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


def closed(df: pd.DataFrame) -> pd.DataFrame:
    return df[df["result"].isin(["WIN", "LOSS"])].copy()


def equity_curve(df: pd.DataFrame) -> pd.DataFrame:
    c = closed(df).sort_values("timestamp")
    c["equity"] = c["pnl"].cumsum()
    return c


def max_drawdown(df: pd.DataFrame) -> float:
    c = equity_curve(df)
    if c.empty:
        return 0.0
    running_max = c["equity"].cummax()
    return float((c["equity"] - running_max).min())


def winrate_by_pair(df: pd.DataFrame) -> pd.DataFrame:
    c = closed(df)
    if c.empty:
        return pd.DataFrame()
    out = c.groupby("pair").agg(
        trades=("result", "size"),
        wins=("result", lambda s: int((s == "WIN").sum())),
    )
    out["winrate"] = out["wins"] / out["trades"]
    return out.sort_values("winrate", ascending=False).reset_index()


def calibration(df: pd.DataFrame) -> pd.DataFrame:
    c = closed(df)
    if c["confidence"].isna().all():
        return pd.DataFrame()
    c = c.dropna(subset=["confidence"])
    c["conf_bin"] = pd.cut(
        c["confidence"],
        bins=[0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
        include_lowest=True,
    )
    out = c.groupby("conf_bin", observed=True).agg(
        n=("result", "size"),
        mid=("confidence", "mean"),
        winrate=("result", lambda s: float((s == "WIN").mean())),
    )
    return out.reset_index()


def main() -> None:
    st.set_page_config(page_title="Exnova Bot — Dashboard", layout="wide")
    st.title("Exnova Bot — Dashboard")

    df = trades_frame()
    if df.empty:
        st.warning("bot_data.db no contiene operaciones todavía.")
        return

    market = st.sidebar.selectbox("Market type", ["Todos", "NORMAL", "OTC"])
    if market != "Todos":
        df = df[df["market_type"] == market]

    c = closed(df)
    if c.empty:
        st.warning("No hay operaciones resueltas (WIN/LOSS).")
        return

    total_pnl = float(c["pnl"].sum())
    global_winrate = float((c["result"] == "WIN").mean())
    max_dd = max_drawdown(df)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Operaciones resueltas", len(c))
    col2.metric("Win rate", f"{global_winrate:.1%}")
    col3.metric("PnL total", f"{total_pnl:+.2f}")
    col4.metric("Max drawdown", f"{max_dd:.2f}")

    st.subheader("Curva de equity (PnL acumulado)")
    eq = equity_curve(df)
    step = max(1, len(eq) // 2000)
    st.line_chart(eq.iloc[::step].set_index("timestamp")["equity"])

    st.subheader("Win rate por par")
    wr = winrate_by_pair(df)
    st.bar_chart(wr.set_index("pair")["winrate"])
    st.dataframe(
        wr.assign(winrate=wr["winrate"].map("{:.1%}".format)),
        use_container_width=True,
        hide_index=True,
    )

    st.subheader("Calibración: confianza vs resultado")
    cal = calibration(df)
    if cal.empty:
        st.info("No hay operaciones con confidence registrada.")
    else:
        cal["label"] = cal["conf_bin"].astype(str)
        st.scatter_chart(
            cal,
            x="mid",
            y="winrate",
            size="n",
            color="#ff4b4b",
            width="stretch",
        )
        st.dataframe(
            cal[["label", "n", "mid", "winrate"]].assign(
                mid=cal["mid"].map("{:.2f}".format),
                winrate=cal["winrate"].map("{:.1%}".format),
            ),
            use_container_width=True,
            hide_index=True,
        )
        st.caption("Línea diagonal perfecta = proba bien calibrada. Puntos bajo ella sobreestiman.")


if __name__ == "__main__":
    main()
