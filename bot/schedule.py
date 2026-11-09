"""Horarios de los activos: ventanas de apertura que publica el bróker.

`initialization-data` -> `binary.actives.*.schedule` es una lista de pares
[inicio, fin] en epoch UTC. Fuera de esas ventanas el activo está cerrado y
`buy` responde "the asset is not available at the moment".
"""

from __future__ import annotations

Window = tuple[int, int]


def windows(schedule: list | None) -> list[Window]:
    """Normaliza el schedule a una lista de (inicio, fin) ordenada."""
    out = []
    for item in schedule or []:
        if isinstance(item, dict):
            item = (item.get("open"), item.get("close"))
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            out.append((int(item[0]), int(item[1])))
    return sorted(out)


def is_open(schedule: list | None, ts: float) -> bool:
    """True si `ts` cae dentro de alguna ventana."""
    return any(start <= ts <= end for start, end in windows(schedule))


def next_close(schedule: list | None, ts: float) -> int | None:
    """Epoch en que cierra la ventana actual, o None si ya está cerrado."""
    ends = [end for start, end in windows(schedule) if start <= ts <= end]
    return min(ends) if ends else None


def next_open(schedule: list | None, ts: float) -> int | None:
    """Epoch en que abre la próxima ventana, o None si no hay ninguna."""
    starts = [start for start, _ in windows(schedule) if start > ts]
    return min(starts) if starts else None


def closure_around(schedule: list | None, ts: float) -> Window | None:
    """Ventana de cierre que contiene `ts`, inferida entre dos aperturas."""
    wins = windows(schedule)
    if is_open(schedule, ts):
        return None
    before = [end for _, end in wins if end < ts]
    after = [start for start, _ in wins if start > ts]
    if before and after:
        return max(before), min(after)
    return None
