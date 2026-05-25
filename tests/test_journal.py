"""GardenJournal（Stage 2A）单元测试。"""

from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from memory_garden.core.journal import GardenJournal
from memory_garden.core.models import GardenEvent, GardenEventType, GardenObjectType
from memory_garden.storage.sqlite import SQLiteGardenRepository


def test_record_event_seed_created() -> None:
    repo = SQLiteGardenRepository(":memory:")
    try:
        journal = GardenJournal(repo)
        ev = journal.record_event(
            event_type=GardenEventType.seed_created,
            object_type=GardenObjectType.seed,
            object_id="seed-1",
            summary="检测到新种子",
        )
        assert ev.event_type == GardenEventType.seed_created
        loaded = repo.get_garden_event(ev.id)
        assert loaded.summary == "检测到新种子"
    finally:
        repo.close()


def test_record_event_court_opened() -> None:
    repo = SQLiteGardenRepository(":memory:")
    try:
        journal = GardenJournal(repo)
        ev = journal.record_event(
            event_type=GardenEventType.court_opened,
            object_type=GardenObjectType.court_case,
            object_id="case-1",
            summary="法庭开庭",
        )
        assert ev.event_type == GardenEventType.court_opened
    finally:
        repo.close()


def test_record_event_memory_planted() -> None:
    repo = SQLiteGardenRepository(":memory:")
    try:
        journal = GardenJournal(repo)
        ev = journal.record_event(
            event_type=GardenEventType.memory_planted,
            object_type=GardenObjectType.memory_card,
            object_id="mem-1",
            summary="记忆已种下",
        )
        assert ev.event_type == GardenEventType.memory_planted
    finally:
        repo.close()


def test_metadata_roundtrip() -> None:
    repo = SQLiteGardenRepository(":memory:")
    try:
        journal = GardenJournal(repo)
        meta = {"层级": {"键": 1}, "tags": ["a", "b"]}
        ev = journal.record_event(
            event_type=GardenEventType.verdict_made,
            object_type=GardenObjectType.court_case,
            object_id="c1",
            summary="判决记录",
            metadata=meta,
        )
        again = repo.get_garden_event(ev.id)
        assert again.metadata == meta
    finally:
        repo.close()


def test_metadata_none_becomes_empty_dict() -> None:
    repo = SQLiteGardenRepository(":memory:")
    try:
        journal = GardenJournal(repo)
        ev = journal.record_event(
            event_type=GardenEventType.dream_completed,
            object_type=GardenObjectType.dream_record,
            object_id="d1",
            summary="梦境完成",
            metadata=None,
        )
        assert ev.metadata == {}
        assert repo.get_garden_event(ev.id).metadata == {}
    finally:
        repo.close()


def test_recent_events_returns_garden_event_instances() -> None:
    repo = SQLiteGardenRepository(":memory:")
    try:
        journal = GardenJournal(repo)
        journal.record_event(
            event_type=GardenEventType.seed_created,
            object_type=GardenObjectType.seed,
            object_id="s1",
            summary="一条",
        )
        rows = journal.recent_events(limit=10)
        assert len(rows) == 1
        assert isinstance(rows[0], GardenEvent)
        assert rows[0].object_id == "s1"
    finally:
        repo.close()


def test_recent_events_delegates_to_repository() -> None:
    repo = MagicMock()
    repo.list_garden_events.return_value = []
    journal = GardenJournal(repo)
    journal.recent_events(limit=15)
    repo.list_garden_events.assert_called_once_with(limit=15)


def test_empty_summary_validation_fails() -> None:
    repo = SQLiteGardenRepository(":memory:")
    try:
        journal = GardenJournal(repo)
        with pytest.raises(ValidationError):
            journal.record_event(
                event_type=GardenEventType.seed_created,
                object_type=GardenObjectType.seed,
                object_id="x",
                summary="   ",
            )
    finally:
        repo.close()


def test_journal_does_not_use_print_or_logging(monkeypatch: pytest.MonkeyPatch) -> None:
    """事件记录须走仓储，不得依赖 print/logging。"""
    printed: list[str] = []

    def fake_print(*_a: object, **_k: object) -> None:
        printed.append("x")

    monkeypatch.setattr("builtins.print", fake_print)

    repo = SQLiteGardenRepository(":memory:")
    try:
        journal = GardenJournal(repo)
        journal.record_event(
            event_type=GardenEventType.memory_composted,
            object_type=GardenObjectType.compost_record,
            object_id="cp1",
            summary="堆肥事件",
        )
        assert printed == []
    finally:
        repo.close()
