"""Capa de persistencia SQLite (esquema mínimo para model_versions).

La tabla trade_logs (auditoría de operaciones) se añade en Fase 3; aquí solo
existe lo que Fase 2 necesita para registrar versiones de modelo.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "bot_data.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS model_versions (
    id INTEGER PRIMARY KEY,
    trained_at DATETIME NOT NULL,
    deployed_at DATETIME,
    is_active BOOLEAN NOT NULL DEFAULT 0,
    val_accuracy FLOAT,
    val_logloss FLOAT,
    feature_list TEXT,
    notes TEXT
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