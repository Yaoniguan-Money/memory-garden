"""Append-only domain record persistence for SQLiteGardenRepository."""

from __future__ import annotations

from typing import Any

from memory_garden.core.models import (
    CompostRecord,
    CourtCase,
    DreamRecord,
    GreenhouseRecord,
    PruningRecord,
)
from memory_garden.storage.base import DuplicateIdError, NotFoundError
from memory_garden.storage.sqlite_support import dump_payload, load_payload, wrap_sqlite_exc


class SQLiteDomainRecordMixin:
    """Persist court, dream, compost, greenhouse, and pruning records."""

    def save_court_case(self, case: CourtCase) -> CourtCase:
        return self._save_court_case_impl(case)

    @wrap_sqlite_exc
    def _save_court_case_impl(self, case: CourtCase) -> CourtCase:
        if self._exists("court_cases", case.id):
            raise DuplicateIdError(case.id)
        dump, payload = dump_payload(case)
        verdict_val = case.judge_verdict.verdict.value
        self._conn.execute(
            """
            INSERT INTO court_cases (id, created_at, seed_id, verdict, payload)
            VALUES (?, ?, ?, ?, ?)
            """,
            (case.id, dump["created_at"], case.seed_id, verdict_val, payload),
        )
        self._maybe_commit()
        return case

    def get_court_case(self, case_id: str) -> CourtCase:
        return self._get_court_case_impl(case_id)

    @wrap_sqlite_exc
    def _get_court_case_impl(self, case_id: str) -> CourtCase:
        row = self._conn.execute(
            "SELECT payload FROM court_cases WHERE id = ?",
            (case_id,),
        ).fetchone()
        if row is None:
            raise NotFoundError(case_id)
        return load_payload(CourtCase, row)

    def list_court_cases(
        self,
        seed_id: str | None = None,
        limit: int | None = None,
    ) -> list[CourtCase]:
        return self._list_court_cases_impl(seed_id, limit)

    @wrap_sqlite_exc
    def _list_court_cases_impl(
        self,
        seed_id: str | None,
        limit: int | None,
    ) -> list[CourtCase]:
        sql = "SELECT payload FROM court_cases WHERE 1 = 1"
        params: list[Any] = []
        if seed_id is not None:
            sql += " AND seed_id = ?"
            params.append(seed_id)
        sql += " ORDER BY created_at DESC"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        rows = self._conn.execute(sql, params).fetchall()
        return [load_payload(CourtCase, row) for row in rows]

    def save_dream_record(self, record: DreamRecord) -> DreamRecord:
        return self._save_dream_record_impl(record)

    @wrap_sqlite_exc
    def delete_court_case(self, case_id: str) -> None:
        self._delete_court_case_impl(case_id)

    @wrap_sqlite_exc
    def _delete_court_case_impl(self, case_id: str) -> None:
        cur = self._conn.execute("DELETE FROM court_cases WHERE id = ?", (case_id,))
        if cur.rowcount == 0:
            raise NotFoundError(case_id)
        self._maybe_commit()

    @wrap_sqlite_exc
    def _save_dream_record_impl(self, record: DreamRecord) -> DreamRecord:
        if self._exists("dream_records", record.id):
            raise DuplicateIdError(record.id)
        dump, payload = dump_payload(record)
        self._conn.execute(
            """
            INSERT INTO dream_records (id, created_at, payload)
            VALUES (?, ?, ?)
            """,
            (record.id, dump["created_at"], payload),
        )
        self._maybe_commit()
        return record

    def get_dream_record(self, record_id: str) -> DreamRecord:
        return self._get_dream_record_impl(record_id)

    @wrap_sqlite_exc
    def _get_dream_record_impl(self, record_id: str) -> DreamRecord:
        row = self._conn.execute(
            "SELECT payload FROM dream_records WHERE id = ?",
            (record_id,),
        ).fetchone()
        if row is None:
            raise NotFoundError(record_id)
        return load_payload(DreamRecord, row)

    def list_dream_records(self, limit: int | None = None) -> list[DreamRecord]:
        return self._list_dream_records_impl(limit)

    @wrap_sqlite_exc
    def _list_dream_records_impl(self, limit: int | None) -> list[DreamRecord]:
        sql = "SELECT payload FROM dream_records ORDER BY created_at DESC"
        params: list[Any] = []
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        rows = self._conn.execute(sql, params).fetchall()
        return [load_payload(DreamRecord, row) for row in rows]

    def save_compost_record(self, record: CompostRecord) -> CompostRecord:
        return self._save_compost_record_impl(record)

    @wrap_sqlite_exc
    def _save_compost_record_impl(self, record: CompostRecord) -> CompostRecord:
        if self._exists("compost_records", record.id):
            raise DuplicateIdError(record.id)
        dump, payload = dump_payload(record)
        self._conn.execute(
            """
            INSERT INTO compost_records (
                id, created_at, source_seed_id, source_memory_id, payload
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                record.id,
                dump["created_at"],
                dump["source_seed_id"],
                dump["source_memory_id"],
                payload,
            ),
        )
        self._maybe_commit()
        return record

    def get_compost_record(self, record_id: str) -> CompostRecord:
        return self._get_compost_record_impl(record_id)

    @wrap_sqlite_exc
    def _get_compost_record_impl(self, record_id: str) -> CompostRecord:
        row = self._conn.execute(
            "SELECT payload FROM compost_records WHERE id = ?",
            (record_id,),
        ).fetchone()
        if row is None:
            raise NotFoundError(record_id)
        return load_payload(CompostRecord, row)

    def list_compost_records(
        self,
        source_seed_id: str | None = None,
        source_memory_id: str | None = None,
        limit: int | None = None,
    ) -> list[CompostRecord]:
        return self._list_compost_records_impl(source_seed_id, source_memory_id, limit)

    @wrap_sqlite_exc
    def _list_compost_records_impl(
        self,
        source_seed_id: str | None,
        source_memory_id: str | None,
        limit: int | None,
    ) -> list[CompostRecord]:
        sql = "SELECT payload FROM compost_records WHERE 1 = 1"
        params: list[Any] = []
        if source_seed_id is not None:
            sql += " AND source_seed_id = ?"
            params.append(source_seed_id)
        if source_memory_id is not None:
            sql += " AND source_memory_id = ?"
            params.append(source_memory_id)
        sql += " ORDER BY created_at DESC"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        rows = self._conn.execute(sql, params).fetchall()
        return [load_payload(CompostRecord, row) for row in rows]

    def save_greenhouse_record(self, record: GreenhouseRecord) -> GreenhouseRecord:
        return self._save_greenhouse_record_impl(record)

    @wrap_sqlite_exc
    def _save_greenhouse_record_impl(self, record: GreenhouseRecord) -> GreenhouseRecord:
        if self._exists("greenhouse_records", record.id):
            raise DuplicateIdError(record.id)
        dump, payload = dump_payload(record)
        self._conn.execute(
            """
            INSERT INTO greenhouse_records (
                id, created_at, memory_id, sensitivity_level, payload
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                record.id,
                dump["created_at"],
                record.memory_id,
                record.sensitivity_level.value,
                payload,
            ),
        )
        self._maybe_commit()
        return record

    def get_greenhouse_record(self, record_id: str) -> GreenhouseRecord:
        return self._get_greenhouse_record_impl(record_id)

    @wrap_sqlite_exc
    def _get_greenhouse_record_impl(self, record_id: str) -> GreenhouseRecord:
        row = self._conn.execute(
            "SELECT payload FROM greenhouse_records WHERE id = ?",
            (record_id,),
        ).fetchone()
        if row is None:
            raise NotFoundError(record_id)
        return load_payload(GreenhouseRecord, row)

    def list_greenhouse_records(
        self,
        memory_id: str | None = None,
        limit: int | None = None,
    ) -> list[GreenhouseRecord]:
        return self._list_greenhouse_records_impl(memory_id, limit)

    @wrap_sqlite_exc
    def _list_greenhouse_records_impl(
        self,
        memory_id: str | None,
        limit: int | None,
    ) -> list[GreenhouseRecord]:
        sql = "SELECT payload FROM greenhouse_records WHERE 1 = 1"
        params: list[Any] = []
        if memory_id is not None:
            sql += " AND memory_id = ?"
            params.append(memory_id)
        sql += " ORDER BY created_at DESC"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        rows = self._conn.execute(sql, params).fetchall()
        return [load_payload(GreenhouseRecord, row) for row in rows]

    def save_pruning_record(self, record: PruningRecord) -> PruningRecord:
        return self._save_pruning_record_impl(record)

    @wrap_sqlite_exc
    def _save_pruning_record_impl(self, record: PruningRecord) -> PruningRecord:
        if self._exists("pruning_records", record.id):
            raise DuplicateIdError(record.id)
        dump, payload = dump_payload(record)
        self._conn.execute(
            """
            INSERT INTO pruning_records (
                id, created_at, memory_id, old_lifecycle, new_lifecycle, payload
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                record.id,
                dump["created_at"],
                record.memory_id,
                record.old_lifecycle.value,
                record.new_lifecycle.value,
                payload,
            ),
        )
        self._maybe_commit()
        return record

    def get_pruning_record(self, record_id: str) -> PruningRecord:
        return self._get_pruning_record_impl(record_id)

    @wrap_sqlite_exc
    def _get_pruning_record_impl(self, record_id: str) -> PruningRecord:
        row = self._conn.execute(
            "SELECT payload FROM pruning_records WHERE id = ?",
            (record_id,),
        ).fetchone()
        if row is None:
            raise NotFoundError(record_id)
        return load_payload(PruningRecord, row)

    def list_pruning_records(
        self,
        memory_id: str | None = None,
        limit: int | None = None,
    ) -> list[PruningRecord]:
        return self._list_pruning_records_impl(memory_id, limit)

    @wrap_sqlite_exc
    def _list_pruning_records_impl(
        self,
        memory_id: str | None,
        limit: int | None,
    ) -> list[PruningRecord]:
        sql = "SELECT payload FROM pruning_records WHERE 1 = 1"
        params: list[Any] = []
        if memory_id is not None:
            sql += " AND memory_id = ?"
            params.append(memory_id)
        sql += " ORDER BY created_at DESC"
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        rows = self._conn.execute(sql, params).fetchall()
        return [load_payload(PruningRecord, row) for row in rows]
