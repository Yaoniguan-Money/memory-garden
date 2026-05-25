"""Stage 5A-1：温室 greenhouse_memory。"""

from datetime import datetime, timezone

import pytest

from memory_garden.core.growth.greenhouse import greenhouse_memory
from memory_garden.core.growth.lifecycle import MemoryLifecycle
from memory_garden.core.journal import GardenJournal
from memory_garden.core.models import (
    GardenEventType,
    GreenhouseAccessPolicy,
    MemoryCard,
    SensitivityLevel,
)
from memory_garden.storage.base import NotFoundError
from memory_garden.storage.sqlite import SQLiteGardenRepository


@pytest.fixture
def repo() -> SQLiteGardenRepository:
    r = SQLiteGardenRepository(":memory:")
    yield r
    r.close()


def test_greenhouse_sets_lifecycle_and_record(repo: SQLiteGardenRepository) -> None:
    journal = GardenJournal(repo)
    card = MemoryCard(title="t", essence="e", fragrance="f", thorns="th")
    repo.save_memory_card(card)
    gh_record = greenhouse_memory(
        card.id,
        reason="包含敏感线索需隔离",
        sensitivity_level=SensitivityLevel.high,
        access_policy=GreenhouseAccessPolicy.requires_explicit_include,
        repository=repo,
        journal=journal,
    )[1]
    loaded = repo.get_memory_card(card.id)
    assert loaded.lifecycle == MemoryLifecycle.greenhouse
    assert loaded.sensitivity == SensitivityLevel.high
    assert repo.get_greenhouse_record(gh_record.id).memory_id == card.id


def test_greenhouse_updates_updated_at(repo: SQLiteGardenRepository) -> None:
    journal = GardenJournal(repo)
    fixed = datetime(2020, 1, 1, tzinfo=timezone.utc)
    card = MemoryCard(
        title="t",
        essence="e",
        fragrance="f",
        thorns="th",
        updated_at=fixed,
    )
    repo.save_memory_card(card)
    greenhouse_memory(
        card.id,
        reason="隔离",
        sensitivity_level=SensitivityLevel.medium,
        access_policy=GreenhouseAccessPolicy.excluded_by_default,
        repository=repo,
        journal=journal,
    )
    assert repo.get_memory_card(card.id).updated_at > fixed


def test_greenhouse_writes_event(repo: SQLiteGardenRepository) -> None:
    journal = GardenJournal(repo)
    card = MemoryCard(title="t", essence="e", fragrance="f", thorns="th")
    repo.save_memory_card(card)
    before = len(repo.list_garden_events(event_type=GardenEventType.memory_greenhoused))
    greenhouse_memory(
        card.id,
        reason="原因",
        sensitivity_level=SensitivityLevel.low,
        access_policy=GreenhouseAccessPolicy.excluded_by_default,
        repository=repo,
        journal=journal,
    )
    after = repo.list_garden_events(event_type=GardenEventType.memory_greenhoused)
    assert len(after) == before + 1


def test_list_memory_cards_excludes_greenhouse_by_default(repo: SQLiteGardenRepository) -> None:
    journal = GardenJournal(repo)
    card = MemoryCard(title="t", essence="e", fragrance="f", thorns="th")
    repo.save_memory_card(card)
    greenhouse_memory(
        card.id,
        reason="隔离",
        sensitivity_level=SensitivityLevel.medium,
        access_policy=GreenhouseAccessPolicy.excluded_by_default,
        repository=repo,
        journal=journal,
    )
    assert repo.list_memory_cards(include_greenhouse=False) == []
    assert len(repo.list_memory_cards(include_greenhouse=True)) == 1


def test_greenhouse_missing_memory_raises(repo: SQLiteGardenRepository) -> None:
    journal = GardenJournal(repo)
    with pytest.raises(NotFoundError):
        greenhouse_memory(
            "missing-id",
            reason="x",
            sensitivity_level=SensitivityLevel.low,
            access_policy=GreenhouseAccessPolicy.excluded_by_default,
            repository=repo,
            journal=journal,
        )


def test_greenhouse_rejects_pruned(repo: SQLiteGardenRepository) -> None:
    journal = GardenJournal(repo)
    card = MemoryCard(
        title="t",
        essence="e",
        fragrance="f",
        thorns="th",
        lifecycle=MemoryLifecycle.pruned,
    )
    repo.save_memory_card(card)
    with pytest.raises(ValueError, match="修剪"):
        greenhouse_memory(
            card.id,
            reason="不应进入",
            sensitivity_level=SensitivityLevel.low,
            access_policy=GreenhouseAccessPolicy.excluded_by_default,
            repository=repo,
            journal=journal,
        )


def test_greenhouse_rejects_composted_lifecycle(repo: SQLiteGardenRepository) -> None:
    journal = GardenJournal(repo)
    card = MemoryCard(
        title="t",
        essence="e",
        fragrance="f",
        thorns="th",
        lifecycle=MemoryLifecycle.composted,
    )
    repo.save_memory_card(card)
    with pytest.raises(ValueError, match="堆肥"):
        greenhouse_memory(
            card.id,
            reason="不应进入",
            sensitivity_level=SensitivityLevel.low,
            access_policy=GreenhouseAccessPolicy.excluded_by_default,
            repository=repo,
            journal=journal,
        )


def test_greenhouse_empty_reason_raises(repo: SQLiteGardenRepository) -> None:
    journal = GardenJournal(repo)
    card = MemoryCard(title="t", essence="e", fragrance="f", thorns="th")
    repo.save_memory_card(card)
    with pytest.raises(ValueError, match="理由"):
        greenhouse_memory(
            card.id,
            reason="   ",
            sensitivity_level=SensitivityLevel.low,
            access_policy=GreenhouseAccessPolicy.excluded_by_default,
            repository=repo,
            journal=journal,
        )
