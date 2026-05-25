"""Stage 6A：规则版梦境周期 DreamCycleEngine。"""

import pytest

from memory_garden.core import DreamCycleEngine, GardenJournal, greenhouse_memory
from memory_garden.core.growth.lifecycle import MemoryLifecycle
from memory_garden.core.models import (
    DreamRecord,
    GardenEventType,
    GardenObjectType,
    GreenhouseAccessPolicy,
    MemoryCard,
    Seed,
    SeedSignalType,
    SeedStatus,
    SensitivityLevel,
)
from memory_garden.storage.sqlite import SQLiteGardenRepository


@pytest.fixture
def repo() -> SQLiteGardenRepository:
    r = SQLiteGardenRepository(":memory:")
    yield r
    r.close()


def test_dream_empty_repository_returns_none_no_event(repo: SQLiteGardenRepository) -> None:
    journal = GardenJournal(repo)
    engine = DreamCycleEngine(repo, journal)
    assert engine.dream() is None
    assert repo.list_garden_events(event_type=GardenEventType.dream_completed) == []


def test_dream_cluster_creates_one_memory_with_all_source_seed_ids(repo: SQLiteGardenRepository) -> None:
    journal = GardenJournal(repo)
    engine = DreamCycleEngine(repo, journal)
    s1 = Seed(
        content="希望以后界面默认深色模式以保护视力",
        source_excerpt="深色",
        tags=["ui_pref"],
        signal_type=SeedSignalType.preference,
    )
    s2 = Seed(
        content="希望以后长期使用深色主题降低刺眼",
        source_excerpt="深色",
        tags=["ui_pref"],
        signal_type=SeedSignalType.preference,
    )
    repo.save_seed(s1)
    repo.save_seed(s2)

    record = engine.dream()
    assert record is not None
    assert len(record.created_memory_ids) == 1
    assert set(record.input_seed_ids) == {s1.id, s2.id}
    assert len(record.composted_seed_ids) == 0

    card = repo.get_memory_card(record.created_memory_ids[0])
    assert {s1.id, s2.id} <= set(card.source_seed_ids)
    assert "夜间收敛" in card.essence
    assert s1.content not in card.essence
    assert s2.content not in card.essence
    # 稳定语义：字典序最小的种子执行 plant（PLANTED），其余并入后均为 MERGED
    first, second = sorted((s1, s2), key=lambda x: x.id)
    assert repo.get_seed(first.id).status == SeedStatus.planted
    assert repo.get_seed(second.id).status == SeedStatus.merged

    assert record.observation.strip()
    assert record.reflection.strip()
    assert record.transformation.strip()
    assert record.morning_garden.strip()
    assert record.id in record.transformation
    assert "新建记忆卡" in record.transformation
    assert "堆肥" in record.transformation


def test_dream_restores_seed_status_when_cluster_court_does_not_plant(repo: SQLiteGardenRepository) -> None:
    journal = GardenJournal(repo)
    engine = DreamCycleEngine(repo, journal)
    s1 = Seed(
        content="maybe maybe",
        source_excerpt="maybe",
        tags=["weak"],
        signal_type=SeedSignalType.unknown,
    )
    s2 = Seed(
        content="maybe maybe again",
        source_excerpt="maybe",
        tags=["weak"],
        signal_type=SeedSignalType.unknown,
    )
    repo.save_seed(s1)
    repo.save_seed(s2)

    record = engine.dream()

    assert record is not None
    assert record.created_memory_ids == []
    first = sorted((s1, s2), key=lambda x: x.id)[0]
    assert repo.get_seed(first.id).status == SeedStatus.pending


def test_dream_record_text_fields_non_empty(repo: SQLiteGardenRepository) -> None:
    journal = GardenJournal(repo)
    engine = DreamCycleEngine(repo, journal)
    s1 = Seed(
        content="希望以后回复简洁一点",
        source_excerpt="简洁",
        tags=["style"],
        signal_type=SeedSignalType.preference,
    )
    s2 = Seed(
        content="希望以后语气更简洁清楚",
        source_excerpt="简洁",
        tags=["style"],
        signal_type=SeedSignalType.preference,
    )
    repo.save_seed(s1)
    repo.save_seed(s2)
    record = engine.dream()
    assert record is not None
    dr = repo.get_dream_record(record.id)
    assert isinstance(dr, DreamRecord)
    for field in ("observation", "reflection", "transformation", "morning_garden"):
        assert len(getattr(dr, field).strip()) > 0


def test_negative_short_seed_compost_no_memory_card(repo: SQLiteGardenRepository) -> None:
    journal = GardenJournal(repo)
    engine = DreamCycleEngine(repo, journal)
    seed = Seed(
        content="我好废",
        source_excerpt="我好废",
        signal_type=SeedSignalType.negative_self_talk,
    )
    repo.save_seed(seed)
    record = engine.dream()
    assert record is not None
    assert record.created_memory_ids == []
    assert seed.id in record.composted_seed_ids
    assert repo.list_memory_cards(include_greenhouse=True) == []
    assert repo.get_seed(seed.id).status == SeedStatus.composted
    nutrient_in_repo = repo.list_compost_records(source_seed_id=seed.id)[0].retained_nutrient
    assert "身份" in nutrient_in_repo or "固化为" in nutrient_in_repo


def test_dream_writes_dream_completed_event_with_metadata(repo: SQLiteGardenRepository) -> None:
    journal = GardenJournal(repo)
    engine = DreamCycleEngine(repo, journal)
    s1 = Seed(
        content="希望以后少用感叹号",
        source_excerpt="感叹号",
        tags=["tone"],
        signal_type=SeedSignalType.preference,
    )
    s2 = Seed(
        content="希望以后语气平静少用感叹号",
        source_excerpt="语气",
        tags=["tone"],
        signal_type=SeedSignalType.preference,
    )
    repo.save_seed(s1)
    repo.save_seed(s2)
    record = engine.dream()
    assert record is not None
    events = repo.list_garden_events(event_type=GardenEventType.dream_completed)
    assert len(events) == 1
    ev = events[0]
    assert ev.object_type == GardenObjectType.dream_record
    assert ev.object_id == record.id
    meta = ev.metadata
    assert meta.get("engine") == "rule_based"
    assert "created_memory_ids" in meta
    assert "merged_memory_ids" in meta
    assert "composted_seed_ids" in meta
    assert "pruned_memory_ids" in meta
    assert "input_seed_ids" in meta
    assert "input_memory_ids" in meta


def test_dream_excludes_greenhouse_memories_by_default(repo: SQLiteGardenRepository) -> None:
    journal = GardenJournal(repo)
    exposed = MemoryCard(title="可见", essence="朝露记忆", fragrance="f", thorns="t")
    hidden = MemoryCard(title="温室", essence="隔离记忆", fragrance="f", thorns="t")
    repo.save_memory_card(exposed)
    repo.save_memory_card(hidden)
    greenhouse_memory(
        hidden.id,
        reason="敏感线索隔离",
        sensitivity_level=SensitivityLevel.high,
        access_policy=GreenhouseAccessPolicy.excluded_by_default,
        repository=repo,
        journal=journal,
    )
    assert repo.get_memory_card(hidden.id).lifecycle == MemoryLifecycle.greenhouse

    seed = Seed(
        content="希望以后笔记本地化存储",
        source_excerpt="本地",
        tags=["store"],
        signal_type=SeedSignalType.preference,
    )
    repo.save_seed(seed)
    engine = DreamCycleEngine(repo, journal)
    record = engine.dream()
    assert record is not None
    assert hidden.id not in record.input_memory_ids
    assert exposed.id in record.input_memory_ids


def test_transformation_lists_actions_and_ids_not_plain_summary(repo: SQLiteGardenRepository) -> None:
    journal = GardenJournal(repo)
    engine = DreamCycleEngine(repo, journal)
    seed = Seed(
        content="我好废",
        source_excerpt="我好废",
        signal_type=SeedSignalType.negative_self_talk,
    )
    repo.save_seed(seed)
    record = engine.dream()
    assert record is not None
    assert "梦境操作" in record.transformation
    assert record.id in record.transformation
    assert "堆肥种子" in record.transformation and seed.id in record.transformation
