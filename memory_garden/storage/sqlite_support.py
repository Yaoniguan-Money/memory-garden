"""Shared helpers for the SQLite repository implementation."""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Callable, TypeVar

from memory_garden.storage.base import DuplicateIdError, NotFoundError, RepositoryError

T = TypeVar("T")

ALLOWED_TABLES = frozenset(
    {
        "seeds",
        "memory_cards",
        "court_cases",
        "dream_records",
        "compost_records",
        "greenhouse_records",
        "pruning_records",
        "garden_events",
    }
)


def wrap_sqlite_exc(fn: Callable[..., T]) -> Callable[..., T]:
    """Translate sqlite3 failures into repository-level errors."""

    def _inner(*args: Any, **kwargs: Any) -> T:
        try:
            return fn(*args, **kwargs)
        except (NotFoundError, DuplicateIdError):
            raise
        except sqlite3.Error as exc:
            raise RepositoryError(str(exc)) from exc

    return _inner  # type: ignore[return-value]


def dump_payload(model: Any) -> tuple[dict[str, Any], str]:
    """Return a JSON-mode model dump and stable payload string."""

    dump = model.model_dump(mode="json")
    payload = json.dumps(dump, ensure_ascii=False, sort_keys=True)
    return dump, payload


def load_payload(model_type: type[T], row: sqlite3.Row) -> T:
    """Hydrate a Pydantic model from a repository payload row."""

    return model_type.model_validate(json.loads(row["payload"]))  # type: ignore[attr-defined]
