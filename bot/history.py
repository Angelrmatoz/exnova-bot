"""Descarga de historial de velas con paginación. Lógica pura, sin importar broker.

Para entrenar y validar el modelo XGBoost se necesitan 10,000+ velas.
El bróker devuelve como máximo ~1000 velas por petición, así que se pagina
hacia atrás reutilizando el timestamp de la vela más antigua como corte.

`fetch_candle_history` solo recibe un callable `getter(count, endtime) -> list[dict]`
para no acoplar el módulo a ningún broker concreto (el script que lo use decide
cómo leer del adaptador).
"""

from __future__ import annotations

import csv
import time
from pathlib import Path
from typing import Callable

# Máximo de velas por petición según comportamiento observado del bróker.
_BATCH = 1000


def fetch_candle_history(
    getter: Callable[[int, int | None], list[dict]],
    target: int,
    delay: float = 0.2,
) -> list[dict]:
    """Descarga velas hacia atrás hasta reunir `target` velas (deduplicadas).

    `delay` espacia las peticiones (segundos) para no golpear la API seguido.
    Devuelve lista de dicts {time, open, close, high, low} en orden antiguo->nuevo.
    """
    seen: list[dict] = []
    cut: int | None = None
    guard = 0
    while len(seen) < target and guard < 200:
        guard += 1
        batch = getter(_BATCH, cut)
        if not batch:
            break
        for c in batch:
            # dedupe por timestamp (una vela repetida en el borde entre páginas)
            if not any(existing["time"] == c["time"] for existing in seen):
                seen.append(c)
        oldest = min(c["time"] for c in batch)
        if cut is not None and oldest >= cut:
            break  # la API no avanzó; no hay más historial disponible
        cut = oldest
        if delay:
            time.sleep(delay)
    seen.sort(key=lambda c: c["time"])
    return seen[:target]


def save_history_csv(rows: list[dict], path: Path) -> None:
    """Escribe velas a CSV. Idempotente: reemplaza el archivo por completo."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["time", "open", "close", "high", "low"])
        writer.writeheader()
        writer.writerows(rows)