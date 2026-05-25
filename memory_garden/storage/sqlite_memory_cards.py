"""MemoryCard persistence methods for SQLiteGardenRepository."""

from __future__ import annotations

import sqlite3
from typing import Any

from memory_garden.core.growth.lifecycle import MemoryLifecycle
from memory_garden.core.models import MemoryCard
from memory_garden.storage.base import DuplicateIdError, NotFoundError
from memory_garden.storage.sqlite_support import dump_payload, load_payload, wrap_sqlite_exc


class SQLiteMemoryCardMixin:
    """Persist and query long-term memory card rows."""

    def save_memory_card(self, memory: MemoryCard) -> MemoryCard:
        return self._save_memory_card_impl(memory)

    @wrap_sqlite_exc
    def _save_memory_card_impl(self, memory: MemoryCard) -> MemoryCard:
        dump, payload = dump_payload(memory)
        try:
            self._conn.execute(
                """
                INSERT INTO memory_cards (
                    id, created_at, lifecycle, memory_type, sensitivity, updated_at, payload
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    memory.id,
                    dump["created_at"],
                    memory.lifecycle.value,
                    memory.memory_type.value,
                    memory.sensitivity.value,
                    dump["updated_at"],
                    payload,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise DuplicateIdError(memory.id) from exc
        self._maybe_commit()
        return memory

    def get_memory_card(self, memory_id: str) -> MemoryCard:
        return self._get_memory_card_impl(memory_id)

    @wrap_sqlite_exc
    def _get_memory_card_impl(self, memory_id: str) -> MemoryCard:
        row = self._conn.execute(
            "SELECT payload FROM memory_cards WHERE id = ?",
            (memory_id,),
        ).fetchone()
        if row is None:
            raise NotFoundError(memory_id)
        return load_payload(MemoryCard, row)

    def list_memory_cards(
        self,
        lifecycle: MemoryLifecycle | None = None,
        include_greenhouse: bool = False,
        limit: int | None = None,
    ) -> list[MemoryCard]:
        return self._list_memory_cards_impl(lifecycle, include_greenhouse, limit, offset=0)

    def list_memory_cards_paged(
        self,
        *,
        lifecycle: MemoryLifecycle | None = None,
        include_greenhouse: bool = False,
        limit: int,
        offset: int = 0,
    ) -> list[MemoryCard]:
        return self._list_memory_cards_impl(lifecycle, include_greenhouse, limit, offset)

    def count_memory_cards(
        self,
        lifecycle: MemoryLifecycle | None = None,
        include_greenhouse: bool = False,
    ) -> int:
        return self._count_memory_cards_impl(lifecycle, include_greenhouse)

    @wrap_sqlite_exc
    def _memory_card_filter_sql(
        self,
        lifecycle: MemoryLifecycle | None,
        include_greenhouse: bool,
    ) -> tuple[str, list[Any]]:
        sql = " FROM memory_cards WHERE 1 = 1"
        params: list[Any] = []
        if lifecycle is not None:
            sql += " AND lifecycle = ?"
            params.append(lifecycle.value)
        if not include_greenhouse:
            sql += " AND lifecycle != ?"
            params.append(MemoryLifecycle.greenhouse.value)
        return sql, params

    @wrap_sqlite_exc
    def _count_memory_cards_impl(
        self,
        lifecycle: MemoryLifecycle | None,
        include_greenhouse: bool,
    ) -> int:
        where_sql, params = self._memory_card_filter_sql(lifecycle, include_greenhouse)
        row = self._conn.execute(f"SELECT COUNT(*){where_sql}", params).fetchone()
        return int(row[0]) if row is not None else 0

    @wrap_sqlite_exc
    def _list_memory_cards_impl(
        self,
        lifecycle: MemoryLifecycle | None,
        include_greenhouse: bool,
        limit: int | None,
        offset: int,
    ) -> list[MemoryCard]:
        where_sql, params = self._memory_card_filter_sql(lifecycle, include_greenhouse)
        sql = f"SELECT payload{where_sql} ORDER BY created_at DESC, id ASC"
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params = [*params, limit, max(0, offset)]
        elif offset:
            sql += " LIMIT -1 OFFSET ?"
            params = [*params, max(0, offset)]
        rows = self._conn.execute(sql, params).fetchall()
        return [load_payload(MemoryCard, row) for row in rows]

    def update_memory_card(self, memory: MemoryCard) -> MemoryCard:
        return self._update_memory_card_impl(memory)

    @wrap_sqlite_exc
    def _update_memory_card_impl(self, memory: MemoryCard) -> MemoryCard:
        if not self._exists("memory_cards", memory.id):
            raise NotFoundError(memory.id)
        dump, payload = dump_payload(memory)
        self._conn.execute(
            """
            UPDATE memory_cards
            SET created_at = ?, lifecycle = ?, memory_type = ?, sensitivity = ?,
                updated_at = ?, payload = ?
            WHERE id = ?
            """,
            (
                dump["created_at"],
                memory.lifecycle.value,
                memory.memory_type.value,
                memory.sensitivity.value,
                dump["updated_at"],
                payload,
                memory.id,
            ),
        )
        self._maybe_commit()
        return memory

    def delete_memory_card(self, memory_id: str) -> None:
        return self._delete_memory_card_impl(memory_id)

    @wrap_sqlite_exc
    def _delete_memory_card_impl(self, memory_id: str) -> None:
        cur = self._conn.execute("DELETE FROM memory_cards WHERE id = ?", (memory_id,))
        if cur.rowcount == 0:
            raise NotFoundError(memory_id)
        self._maybe_commit()
