"""GardenEvent persistence methods for SQLiteGardenRepository."""

from __future__ import annotations

from typing import Any

from memory_garden.core.models import GardenEvent, GardenEventType, GardenObjectType
from memory_garden.storage.base import DuplicateIdError, NotFoundError
from memory_garden.storage.sqlite_support import dump_payload, load_payload, wrap_sqlite_exc


class SQLiteGardenEventMixin:
    """Persist and query the append-only garden event log."""

    def save_garden_event(self, event: GardenEvent) -> GardenEvent:
        return self._save_garden_event_impl(event)

    @wrap_sqlite_exc
    def _save_garden_event_impl(self, event: GardenEvent) -> GardenEvent:
        if self._exists("garden_events", event.id):
            raise DuplicateIdError(event.id)
        dump, payload = dump_payload(event)
        self._conn.execute(
            """
            INSERT INTO garden_events (
                id, created_at, event_type, object_type, object_id, payload
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                event.id,
                dump["created_at"],
                event.event_type.value,
                event.object_type.value,
                event.object_id,
                payload,
            ),
        )
        self._maybe_commit()
        return event

    def get_garden_event(self, event_id: str) -> GardenEvent:
        return self._get_garden_event_impl(event_id)

    @wrap_sqlite_exc
    def _get_garden_event_impl(self, event_id: str) -> GardenEvent:
        row = self._conn.execute(
            "SELECT payload FROM garden_events WHERE id = ?",
            (event_id,),
        ).fetchone()
        if row is None:
            raise NotFoundError(event_id)
        return load_payload(GardenEvent, row)

    def list_garden_events(
        self,
        event_type: GardenEventType | None = None,
        object_type: GardenObjectType | None = None,
        object_id: str | None = None,
        limit: int | None = None,
    ) -> list[GardenEvent]:
        return self._list_garden_events_impl(event_type, object_type, object_id, limit)

    @wrap_sqlite_exc
    def _list_garden_events_impl(
        self,
        event_type: GardenEventType | None,
        object_type: GardenObjectType | None,
        object_id: str | None,
        limit: int | None,
    ) -> list[GardenEvent]:
        sql = "SELECT payload FROM garden_events WHERE 1 = 1"
        params: list[Any] = []
        if event_type is not None:
            sql += " AND event_type = ?"
            params.append(event_type.value)
        if object_type is not None:
            sql += " AND object_type = ?"
            params.append(object_type.value)
        if object_id is not None:
            sql += " AND object_id = ?"
            params.append(object_id)
        sql += " ORDER BY created_at DESC"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        rows = self._conn.execute(sql, params).fetchall()
        return [load_payload(GardenEvent, row) for row in rows]
