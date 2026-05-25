"""Legacy SQLite payload reader for old or synthetic garden databases.

Current code should prefer ``GardenRepository``.  This module exists only as a
storage-layer compatibility shim for databases whose payloads predate the
current strict domain models.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

_TABLES = {
    "memory_cards",
    "seeds",
    "court_cases",
    "dream_records",
    "greenhouse_records",
    "compost_records",
    "pruning_records",
    "garden_events",
}
_ORDER_COLUMNS = {"updated_at", "created_at"}


def load_legacy_payload_summary(database_path: str | Path, *, limit: int = 50) -> dict[str, Any]:
    """Return raw legacy payload rows grouped by table.

    The caller receives plain dictionaries and never touches SQLite payload
    columns directly.
    """
    path = Path(database_path)
    if not path.is_file():
        return {}

    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        return {
            "memory_cards": _rows(conn, "memory_cards", "updated_at", limit),
            "seeds": _rows(conn, "seeds", "created_at", limit),
            "court_cases": _rows(conn, "court_cases", "created_at", limit),
            "dream_records": _rows(conn, "dream_records", "created_at", limit),
            "greenhouse_records": _rows(conn, "greenhouse_records", "created_at", limit),
            "compost_records": _rows(conn, "compost_records", "created_at", limit),
            "pruning_records": _rows(conn, "pruning_records", "created_at", limit),
            "garden_events": _rows(conn, "garden_events", "created_at", limit),
        }
    finally:
        conn.close()


def _rows(conn: sqlite3.Connection, table: str, order_column: str, limit: int) -> list[dict[str, Any]]:
    if table not in _TABLES or order_column not in _ORDER_COLUMNS:
        return []
    if not _table_exists(conn, table):
        return []
    try:
        rows = conn.execute(
            f"SELECT payload FROM {table} ORDER BY {order_column} DESC LIMIT ?",
            (max(1, limit),),
        ).fetchall()
    except sqlite3.Error:
        return []
    out: list[dict[str, Any]] = []
    for row in rows:
        try:
            payload = json.loads(row["payload"])
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(payload, dict):
            out.append(payload)
    return out


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


__all__ = ["load_legacy_payload_summary"]
