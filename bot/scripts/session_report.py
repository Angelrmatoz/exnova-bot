"""Resumen post-sesion para Telegram: trades del dia, acumulado NORMAL, journal.

Lo invoca systemd (exnova-check.timer) via deploy/check_session.sh.
Variables: BOT_DB_PATH, SESSION_JOURNAL, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID.
"""

import datetime
import os
import sqlite3
import urllib.parse
import urllib.request

DB = os.environ.get("BOT_DB_PATH", "/app/db/bot_data.db")
JOURNAL = os.environ.get("SESSION_JOURNAL", "/tmp/session_journal.txt")
TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
CHAT = os.environ.get("TELEGRAM_CHAT_ID", "")
MIN_SAMPLE = 30


def send(text: str) -> None:
    if not TOKEN or not CHAT:
        print(text)
        print("sin TELEGRAM_TOKEN/CHAT_ID; no se envia")
        return
    url = "https://api.telegram.org/bot" + TOKEN + "/sendMessage"
    data = urllib.parse.urlencode(
        {"chat_id": CHAT, "text": text, "disable_notification": "false"}
    ).encode()
    with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=20) as r:
        print("telegram:", r.status)


def main() -> int:
    today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    conn = sqlite3.connect(DB)
    rows = conn.execute(
        "select timestamp,pair,signal,confidence,result,pnl from trade_logs "
        "where market_type='NORMAL' order by id"
    ).fetchall()
    today_rows = [r for r in rows if r[0][:10] == today]
    wins = sum(1 for r in rows if r[4] == "WIN")
    losses = sum(1 for r in rows if r[4] == "LOSS")
    pnl = sum(r[5] or 0 for r in rows)
    lines = [f"Exnova post-sesion {today}", ""]
    if today_rows:
        tw = sum(1 for r in today_rows if r[4] == "WIN")
        tl = sum(1 for r in today_rows if r[4] == "LOSS")
        tp = sum(r[5] or 0 for r in today_rows)
        lines.append(f"Hoy: {len(today_rows)} ops, {tw}W/{tl}L, pnl {tp:+,.2f}")
        for r in today_rows:
            z = f" z={r[3]:.2f}" if r[3] else ""
            lines.append(f"  {r[1]} {r[2]} {r[4]} {r[5]:+,.2f}{z}")
    else:
        lines.append("Hoy: sin operaciones")
    lines.append("")
    lines.append(f"Acumulado NORMAL: {wins + losses} ops, {wins}W/{losses}L, pnl {pnl:+,.2f}")
    lines.append(f"Kill-switch: {wins + losses}/{MIN_SAMPLE} resueltas")
    streak = 0
    for r in rows:
        streak = 0 if r[4] == "WIN" else streak + 1
    if streak:
        lines.append(f"Racha perdida abierta: {streak}")
    try:
        with open(JOURNAL, encoding="utf-8", errors="ignore") as f:
            jl = [l.rstrip() for l in f if l.strip()]
        if jl:
            lines.append("")
            lines.append("Journal hoy:")
            lines.extend("  " + l.split("docker[", 1)[-1].split("]: ", 1)[-1] for l in jl[-25:])
    except OSError:
        pass
    send("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
