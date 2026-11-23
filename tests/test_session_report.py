"""Tests del resumen post-sesion (session_report.py) y su webhook de Discord."""

import datetime
import importlib
import json
import sqlite3

import bot.scripts.session_report as sr


def _db(path, rows):
    c = sqlite3.connect(path)
    c.execute(
        "create table trade_logs (id integer primary key, timestamp text, pair text,"
        " market_type text, signal text, confidence real, gate_passed text,"
        " result text, pnl real, features_snapshot text, model_version_id integer)"
    )
    for i, row in enumerate(rows, 1):
        ts, pair, sig, conf, result, pnl = row[:6]
        snap = json.dumps(row[6]) if len(row) > 6 and row[6] else None
        c.execute(
            "insert into trade_logs (id, timestamp, pair, market_type, signal, confidence,"
            " result, pnl, features_snapshot) values (?,?,?,?,?,?,?,?,?)",
            (i, ts, pair, "NORMAL", sig, conf, result, pnl, snap),
        )
    c.commit()
    c.close()


def _reload(monkeypatch, tmp_path, rows, webhook=""):
    db = tmp_path / "db.sqlite"
    _db(db, rows)
    jr = tmp_path / "j.txt"
    jr.write_text(
        "Nov 18 08:00:00 angelino docker[1]: connect: True None\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("BOT_DB_PATH", str(db))
    monkeypatch.setenv("SESSION_JOURNAL", str(jr))
    monkeypatch.setenv("DISCORD_WEBHOOK_URL", webhook)
    return importlib.reload(sr)


def test_sin_webhook_imprime_fallback(tmp_path, monkeypatch, capsys):
    m = _reload(
        monkeypatch, tmp_path,
        [("2026-01-01T08:00:00+00:00", "EURUSD-op", "call", 2.5, "WIN", 900.0)],
    )
    assert m.main() == 0
    out = capsys.readouterr().out
    assert "sin DISCORD_WEBHOOK_URL; no se envia" in out
    assert "Acumulado NORMAL: 1 ops, 1W/0L" in out
    assert "connect: True" in out


def test_reporte_hoy_acumulado_y_kill_switch(tmp_path, monkeypatch, capsys):
    today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    m = _reload(
        monkeypatch, tmp_path,
        [
            (f"{today}T08:45:00+00:00", "EURGBP-op", "call", 2.02, "LOSS", -1000.0),
            (f"{today}T09:30:00+00:00", "EURUSD-op", "put", 2.01, "WIN", 900.0),
            ("2026-01-05T08:45:00+00:00", "EURGBP-op", "call", 2.07, "WIN", 8600.0),
        ],
    )
    assert m.main() == 0
    out = capsys.readouterr().out
    assert "Hoy: sin operaciones" not in out
    assert "Hoy: 2 ops, 1W/1L, pnl -100.00" in out
    assert "z=2.02" in out
    assert "Acumulado NORMAL: 3 ops, 2W/1L" in out
    assert "Kill-switch: 3/30 resueltas" in out


def test_side_outcomes_en_linea_del_trade(tmp_path, monkeypatch, capsys):
    today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    m = _reload(
        monkeypatch, tmp_path,
        [
            (
                f"{today}T08:45:00+00:00", "EURGBP-op", "call", 2.31, "LOSS", -10000.0,
                {"5m": "WIN", "10m": "WIN", "15m": "LOSS", "30m": "LOSS"},
            ),
        ],
    )
    assert m.main() == 0
    out = capsys.readouterr().out
    assert "z=2.31  [5m=W/10m=W/15m=L/30m=L]" in out


def test_webhook_post_json_con_user_agent(tmp_path, monkeypatch, capsys):
    m = _reload(monkeypatch, tmp_path, [], webhook="https://discord.com/api/webhooks/1/abc")
    captured = {}

    class R:
        status = 204

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=None):
        captured["req"] = req
        return R()

    monkeypatch.setattr(m.urllib.request, "urlopen", fake_urlopen)
    m.send("hola")
    out = capsys.readouterr().out
    req = captured["req"]
    assert req.full_url == "https://discord.com/api/webhooks/1/abc"
    assert json.loads(req.data) == {"content": "hola"}
    assert req.get_header("Content-type") == "application/json"
    assert req.get_header("User-agent") == "exnova-session-report/1.0"
    assert "discord: 204" in out


def test_webhook_recorta_mensajes_largos(tmp_path, monkeypatch):
    m = _reload(monkeypatch, tmp_path, [], webhook="https://discord.com/api/webhooks/1/abc")
    captured = {}

    class R:
        status = 204

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=None):
        captured["req"] = req
        return R()

    monkeypatch.setattr(m.urllib.request, "urlopen", fake_urlopen)
    m.send("x" * 3000)
    content = json.loads(captured["req"].data)["content"]
    assert len(content) < 2000
