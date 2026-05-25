"""Seed persistence methods for SQLiteGardenRepository."""

from __future__ import annotations

from typing import Any

from memory_garden.core.models import Seed, SeedStatus
from memory_garden.storage.base import DuplicateIdError, NotFoundError
from memory_garden.storage.sqlite_support import dump_payload, load_payload, wrap_sqlite_exc


class SQLiteSeedMixin:
    """Persist and query Seed rows."""

    def save_seed(self, seed: Seed) -> Seed:
        return self._save_seed_impl(seed)

    @wrap_sqlite_exc
    def _save_seed_impl(self, seed: Seed) -> Seed:
        if self._exists("seeds", seed.id):
            raise DuplicateIdError(seed.id)
        dump, payload = dump_payload(seed)
        self._conn.execute(
            """
            INSERT INTO seeds (id, created_at, status, signal_type, payload)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                seed.id,
                dump["created_at"],
                seed.status.value,
                seed.signal_type.value,
                payload,
            ),
        )
        self._maybe_commit()
        return seed

    def get_seed(self, seed_id: str) -> Seed:
        return self._get_seed_impl(seed_id)

    @wrap_sqlite_exc
    def _get_seed_impl(self, seed_id: str) -> Seed:
        row = self._conn.execute(
            "SELECT payload FROM seeds WHERE id = ?",
            (seed_id,),
        ).fetchone()
        if row is None:
            raise NotFoundError(seed_id)
        return load_payload(Seed, row)

    def list_seeds(
        self,
        status: SeedStatus | None = None,
        limit: int | None = None,
    ) -> list[Seed]:
        return self._list_seeds_impl(status, limit)

    @wrap_sqlite_exc
    def _list_seeds_impl(
        self,
        status: SeedStatus | None,
        limit: int | None,
    ) -> list[Seed]:
        sql = "SELECT payload FROM seeds WHERE 1 = 1"
        params: list[Any] = []
        if status is not None:
            sql += " AND status = ?"
            params.append(status.value)
        sql += " ORDER BY created_at DESC"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        rows = self._conn.execute(sql, params).fetchall()
        return [load_payload(Seed, row) for row in rows]

    def update_seed(self, seed: Seed) -> Seed:
        return self._update_seed_impl(seed)

    @wrap_sqlite_exc
    def _update_seed_impl(self, seed: Seed) -> Seed:
        if not self._exists("seeds", seed.id):
            raise NotFoundError(seed.id)
        dump, payload = dump_payload(seed)
        self._conn.execute(
            """
            UPDATE seeds
            SET created_at = ?, status = ?, signal_type = ?, payload = ?
            WHERE id = ?
            """,
            (
                dump["created_at"],
                seed.status.value,
                seed.signal_type.value,
                payload,
                seed.id,
            ),
        )
        self._maybe_commit()
        return seed
