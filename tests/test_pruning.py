"""Stage 5A-2：修剪、遗忘、记忆合并。"""

import pytest

from memory_garden.core.cards import merge_memory_into_memory
from memory_garden.core.growth.lifecycle import MemoryLifecycle
from memory_garden.core.growth.pruning import forget_memory, prune_memory
from memory_garden.core.journal import GardenJournal
from memory_garden.core.models import GardenEventType, MemoryCard, SensitivityLevel
from memory_garden.storage.base import NotFoundError
from memory_garden.storage.sqlite import SQLiteGardenRepository


@pytest.fixture
def repo() -> SQLiteGardenRepository:
    r = SQLiteGardenRepository(":memory:")
    yield r
    r.close()


@pytest.fixture
def journal(repo: SQLiteGardenRepository) -> GardenJournal:
    return GardenJournal(repo)


def _card(repo: SQLiteGardenRepository) -> MemoryCard:
    c = MemoryCard(title="标题", essence="摘要正文", fragrance="香", thorns="刺")
    repo.save_memory_card(c)
    return c


def test_prune_sets_pruned_and_record(repo: SQLiteGardenRepository, journal: GardenJournal) -> None:
    c = _card(repo)
    before = c.updated_at
    pr = prune_memory(c.id, "用户否定该结论", repo, journal)
    loaded = repo.get_memory_card(c.id)
    assert loaded.lifecycle == MemoryLifecycle.pruned
    assert loaded.updated_at >= before
    assert pr.old_lifecycle == MemoryLifecycle.sprout
    assert pr.new_lifecycle == MemoryLifecycle.pruned


def test_prune_writes_event(repo: SQLiteGardenRepository, journal: GardenJournal) -> None:
    c = _card(repo)
    n = len(repo.list_garden_events(event_type=GardenEventType.memory_pruned))
    prune_memory(c.id, "修剪", repo, journal)
    assert len(repo.list_garden_events(event_type=GardenEventType.memory_pruned)) == n + 1


def test_prune_does_not_delete_row(repo: SQLiteGardenRepository, journal: GardenJournal) -> None:
    c = _card(repo)
    prune_memory(c.id, "理由", repo, journal)
    assert repo.get_memory_card(c.id).id == c.id


def test_prune_missing_raises(repo: SQLiteGardenRepository, journal: GardenJournal) -> None:
    with pytest.raises(NotFoundError):
        prune_memory("no-such", "x", repo, journal)


def test_prune_blocked_if_already_pruned(repo: SQLiteGardenRepository, journal: GardenJournal) -> None:
    c = MemoryCard(
        title="t",
        essence="e",
        fragrance="f",
        thorns="t",
        lifecycle=MemoryLifecycle.pruned,
    )
    repo.save_memory_card(c)
    with pytest.raises(ValueError, match="修剪"):
        prune_memory(c.id, "再次", repo, journal)


def test_prune_blocked_if_composted(repo: SQLiteGardenRepository, journal: GardenJournal) -> None:
    c = MemoryCard(
        title="t",
        essence="e",
        fragrance="f",
        thorns="t",
        lifecycle=MemoryLifecycle.composted,
    )
    repo.save_memory_card(c)
    with pytest.raises(ValueError):
        prune_memory(c.id, "再次", repo, journal)


def test_soft_forget_pruned_and_event(repo: SQLiteGardenRepository, journal: GardenJournal) -> None:
    c = _card(repo)
    forget_memory(c.id, "soft", "用户不想看见该条", repo, journal)
    assert repo.get_memory_card(c.id).lifecycle == MemoryLifecycle.pruned
    evs = repo.list_garden_events(event_type=GardenEventType.memory_forgotten)
    assert any(e.metadata.get("mode") == "soft" for e in evs)


def test_hard_forget_deletes_and_notfound(repo: SQLiteGardenRepository, journal: GardenJournal) -> None:
    c = _card(repo)
    forget_memory(c.id, "hard", "彻底删除", repo, journal)
    with pytest.raises(NotFoundError):
        repo.get_memory_card(c.id)


def test_hard_forget_event_has_no_content_fields(
    repo: SQLiteGardenRepository,
    journal: GardenJournal,
) -> None:
    c = _card(repo)
    forget_memory(c.id, "hard", "硬删", repo, journal)
    ev = repo.list_garden_events(event_type=GardenEventType.memory_forgotten)[-1]
    banned = {"title", "essence", "tags", "roots", "branches", "fragrance", "thorns"}
    assert not (banned & ev.metadata.keys())


def test_merge_memory_preserves_ids_and_prunes_source(
    repo: SQLiteGardenRepository,
    journal: GardenJournal,
) -> None:
    t = MemoryCard(
        title="目标",
        essence="目标摘要",
        fragrance="fa",
        thorns="ta",
        source_seed_ids=["s1"],
        court_case_ids=["c1"],
        dream_record_ids=["d1"],
    )
    s = MemoryCard(
        title="源",
        essence="源摘要内容",
        fragrance="fb",
        thorns="tb",
        source_seed_ids=["s2"],
        court_case_ids=["c2"],
        dream_record_ids=["d2"],
        sensitivity=SensitivityLevel.low,
        importance=0.4,
    )
    repo.save_memory_card(t)
    repo.save_memory_card(s)

    out = merge_memory_into_memory(s.id, t.id, "合并重复叙事", repo, journal)

    assert out.essence == "目标摘要"
    assert set(out.source_seed_ids) == {"s1", "s2"}
    assert set(out.court_case_ids) == {"c1", "c2"}
    assert set(out.dream_record_ids) == {"d1", "d2"}
    src = repo.get_memory_card(s.id)
    assert src.lifecycle == MemoryLifecycle.pruned
    assert repo.list_pruning_records(memory_id=s.id)


def test_merge_memory_writes_event(repo: SQLiteGardenRepository, journal: GardenJournal) -> None:
    t = MemoryCard(title="t1", essence="e1", fragrance="f", thorns="t")
    s = MemoryCard(title="t2", essence="e2", fragrance="f", thorns="t")
    repo.save_memory_card(t)
    repo.save_memory_card(s)
    n = len(repo.list_garden_events(event_type=GardenEventType.memory_merged))
    merge_memory_into_memory(s.id, t.id, "合并", repo, journal)
    assert len(repo.list_garden_events(event_type=GardenEventType.memory_merged)) == n + 1
