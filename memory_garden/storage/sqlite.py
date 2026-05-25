"""SQLite implementation of the GardenRepository contract.

The public import path remains ``memory_garden.storage.sqlite``.  The
entity-specific methods live in sibling modules so persistence behavior can be
reviewed and tested in smaller units.
"""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from typing import Iterator

from memory_garden.storage.base import GardenRepository, RepositoryError
from memory_garden.storage.sqlite_events import SQLiteGardenEventMixin
from memory_garden.storage.sqlite_memory_cards import SQLiteMemoryCardMixin
from memory_garden.storage.sqlite_records import SQLiteDomainRecordMixin
from memory_garden.storage.sqlite_schema import initialize_schema
from memory_garden.storage.sqlite_seeds import SQLiteSeedMixin
from memory_garden.storage.sqlite_support import ALLOWED_TABLES


class SQLiteGardenRepository(
    SQLiteSeedMixin,
    SQLiteMemoryCardMixin,
    SQLiteDomainRecordMixin,
    SQLiteGardenEventMixin,
    GardenRepository,
):
    """Local SQLite repository with one table per domain entity."""

    def __init__(self, database_path: str) -> None:
        self._database_path = database_path
        self._conn = sqlite3.connect(
            database_path,
            check_same_thread=False,
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._transaction_level = 0
        self._tx_lock = threading.Lock()
        self._init_schema()

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        self._conn.close()

    def _maybe_commit(self) -> None:
        """仅在未处于显式事务中时提交（事务由 begin/commit/rollback 管理）。"""
        if self._transaction_level == 0:
            self._conn.commit()

    def _sp_name(self, level: int) -> str:
        return f"_mg_{threading.get_ident()}_{level}"

    def begin(self) -> None:
        with self._tx_lock:
            if self._transaction_level == 0:
                self._conn.execute("BEGIN IMMEDIATE")
            else:
                self._conn.execute(f"SAVEPOINT {self._sp_name(self._transaction_level)}")
            self._transaction_level += 1

    def commit(self) -> None:
        with self._tx_lock:
            if self._transaction_level == 0:
                raise RepositoryError("commit() called without active transaction")
            self._transaction_level -= 1
            if self._transaction_level == 0:
                self._conn.commit()
            else:
                self._conn.execute(f"RELEASE {self._sp_name(self._transaction_level)}")

    def rollback(self) -> None:
        with self._tx_lock:
            if self._transaction_level == 0:
                raise RepositoryError("rollback() called without active transaction")
            self._transaction_level -= 1
            if self._transaction_level == 0:
                self._conn.rollback()
            else:
                self._conn.execute(f"ROLLBACK TO {self._sp_name(self._transaction_level)}")

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        self.begin()
        try:
            yield self._conn
        except Exception:
            self.rollback()
            raise
        else:
            self.commit()

    def _init_schema(self) -> None:
        initialize_schema(self._conn)

    def _exists(self, table: str, row_id: str) -> bool:
        """Return whether *row_id* exists in one of the fixed repository tables."""

        if table not in ALLOWED_TABLES:
            raise RepositoryError(f"table is not allowed: {table}")
        try:
            row = self._conn.execute(
                f"SELECT 1 FROM {table} WHERE id = ? LIMIT 1",
                (row_id,),
            ).fetchone()
        except sqlite3.Error as exc:
            raise RepositoryError(str(exc)) from exc
        return row is not None
