"""Capa de persistencia SQLite. Esquema: model_versions (Fase 2) + trade_logs (Fase 3)."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "bot_data.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS model_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trained_at DATETIME NOT NULL,
    deployed_at DATETIME,
    is_active BOOLEAN NOT NULL DEFAULT 0,
    val_accuracy FLOAT,
    val_logloss FLOAT,
    feature_list TEXT,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS trade_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp DATETIME NOT NULL,
    pair TEXT NOT NULL,
    market_type TEXT NOT NULL,
    signal TEXT NOT NULL,
    confidence FLOAT,
    gate_passed TEXT,
    result TEXT NOT NULL,
    pnl FLOAT,
    features_snapshot TEXT,
    model_version_id INTEGER REFERENCES model_versions(id)
);
"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


def register_model(
    val_accuracy: float,
    val_logloss: float,
    feature_list: list[str],
    notes: str = "",
) -> int:
    """Inserta una versión de modelo y devuelve su id."""
    now = datetime.now(timezone.utc).isoformat()
    conn = _connect()
    cur = conn.execute(
        "INSERT INTO model_versions (trained_at, val_accuracy, val_logloss, feature_list, notes)"
        " VALUES (?, ?, ?, ?, ?)",
        (now, val_accuracy, val_logloss, json.dumps(feature_list), notes),
    )
    conn.commit()
    model_id = cur.lastrowid
    conn.close()
    return model_id


def log_trade(
    pair: str,
    market_type: str,
    signal: str,
    result: str,
    pnl: float,
    confidence: float | None = None,
    gate_passed: str | None = None,
    features_snapshot: dict | None = None,
    model_version_id: int | None = None,
    timestamp: str | None = None,
) -> int:
    """Registra una operación en trade_logs y devuelve su id."""
    ts = timestamp or datetime.now(timezone.utc).isoformat()
    snapshot = json.dumps(features_snapshot) if features_snapshot is not None else None
    conn = _connect()
    cur = conn.execute(
        "INSERT INTO trade_logs (timestamp, pair, market_type, signal, confidence,"
        " gate_passed, result, pnl, features_snapshot, model_version_id)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (ts, pair, market_type, signal, confidence, gate_passed, result, pnl, snapshot, model_version_id),
    )
    conn.commit()
    trade_id = cur.lastrowid
    conn.close()
    return trade_id


def log_trades(rows: list[dict]) -> int:
    """Inserta varias operaciones en una sola transacción. Devuelve n insertadas.

    Cada dict acepta las mismas claves que log_trade.
    """
    if not rows:
        return 0
    now = datetime.now(timezone.utc).isoformat()
    data = []
    for r in rows:
        snapshot = json.dumps(r["features_snapshot"]) if r.get("features_snapshot") is not None else None
        data.append(
            (
                r.get("timestamp") or now,
                r["pair"],
                r["market_type"],
                r["signal"],
                r.get("confidence"),
                r.get("gate_passed"),
                r["result"],
                r.get("pnl"),
                snapshot,
                r.get("model_version_id"),
            )
        )
    conn = _connect()
    cur = conn.executemany(
        "INSERT INTO trade_logs (timestamp, pair, market_type, signal, confidence,"
        " gate_passed, result, pnl, features_snapshot, model_version_id)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        data,
    )
    conn.commit()
    conn.close()
    return cur.rowcount


def get_trades() -> list[dict]:
    """Devuelve todas las operaciones de trade_logs como lista de dicts."""
    conn = _connect()
    rows = conn.execute(
        "SELECT id, timestamp, pair, market_type, signal, confidence, gate_passed,"
        " result, pnl FROM trade_logs ORDER BY timestamp"
    ).fetchall()
    conn.close()
    cols = ["id", "timestamp", "pair", "market_type", "signal", "confidence", "gate_passed", "result", "pnl"]
    return [dict(zip(cols, r)) for r in rows]


def get_today_pnl(market_type: str | None = None) -> float:
    """Suma del pnl del día (UTC). Solo WIN/LOSS contribuyen; SKIPPED aporta 0."""
    today = datetime.now(timezone.utc).date().isoformat()
    conn = _connect()
    if market_type:
        row = conn.execute(
            "SELECT COALESCE(SUM(pnl), 0) FROM trade_logs"
            " WHERE date(timestamp) = ? AND market_type = ? AND result IN ('WIN','LOSS')",
            (today, market_type),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT COALESCE(SUM(pnl), 0) FROM trade_logs"
            " WHERE date(timestamp) = ? AND result IN ('WIN','LOSS')",
            (today,),
        ).fetchone()
    conn.close()
    return float(row[0])


def get_loss_streak(market_type: str | None = None) -> int:
    """Rachas de LOSS consecutivos desde la última no-LOSS (SKIPPED no rompe la racha)."""
    conn = _connect()
    if market_type:
        rows = conn.execute(
            "SELECT result FROM trade_logs WHERE market_type = ? ORDER BY id DESC",
            (market_type,),
        ).fetchall()
    else:
        rows = conn.execute("SELECT result FROM trade_logs ORDER BY id DESC").fetchall()
    conn.close()
    streak = 0
    for (result,) in rows:
        if result == "LOSS":
            streak += 1
        elif result == "WIN":
            break
    return streak