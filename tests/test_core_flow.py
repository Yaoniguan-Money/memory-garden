"""Stage 7A：MemoryGardenCore 门面编排与端到端委托。"""

from pathlib import Path

import pytest

from memory_garden.core import MemoryGardenCore
from memory_garden.core.court.verdict import CourtVerdict, CourtVerdictType
from memory_garden.core.models import CourtCase, GardenEventType, Seed, SeedSignalType, SeedStatus
from memory_garden.storage.sqlite import SQLiteGardenRepository


@pytest.fixture
def repo() -> SQLiteGardenRepository:
    r = SQLiteGardenRepository(":memory:")
    yield r
    r.close()


def test_core_defaults_to_memory_sqlite_no_extra_project_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    core = MemoryGardenCore()
    assert isinstance(core.repository, SQLiteGardenRepository)
    assert getattr(core.repository, "_database_path") == ":memory:"
    assert not (tmp_path / ".memory_garden").exists()


def test_observe_open_court_apply_verdict_plant_flow(repo: SQLiteGardenRepository) -> None:
    core = MemoryGardenCore(repository=repo)
    text = "我以后都喜欢用简洁中文回答，请从现在起保持这样"
    seeds = core.observe(text)
    assert len(seeds) == 1
    assert seeds[0].status == SeedStatus.pending
    assert core.list_memories() == []

    cases = core.open_court()
    assert len(cases) == 1
    assert cases[0].judge_verdict.verdict == CourtVerdictType.plant
    assert core.list_memories() == []

    card = core.apply_verdict(cases[0])
    assert card is not None
    assert len(core.list_memories()) == 1
    assert repo.get_seed(seeds[0].id).status == SeedStatus.planted


def test_observe_writes_seed_created_only_no_memory(repo: SQLiteGardenRepository) -> None:
    core = MemoryGardenCore(repository=repo)
    core.observe("我希望以后回复都用深色主题")
    types = [e.event_type for e in repo.list_garden_events()]
    assert GardenEventType.seed_created in types
    assert GardenEventType.memory_planted not in types
    assert core.list_memories() == []


def test_negative_compost_apply_verdict_no_memory_card(repo: SQLiteGardenRepository) -> None:
    core = MemoryGardenCore(repository=repo)
    seeds = core.observe("我好废，我不行")
    cases = core.open_court()
    assert cases[0].judge_verdict.verdict == CourtVerdictType.compost
    rec = core.apply_verdict(cases[0])
    assert rec is not None
    assert core.list_memories() == []
    assert repo.get_seed(seeds[0].id).status == SeedStatus.composted


def test_greenhouse_list_memories_default_excludes_greenhouse(repo: SQLiteGardenRepository) -> None:
    core = MemoryGardenCore(repository=repo)
    core.observe("我以后都喜欢用简洁中文回答，请从现在起保持这样")
    case = core.open_court()[0]
    core.apply_verdict(case)
    mid = core.list_memories()[0].id
    core.greenhouse(mid, reason="敏感线索隔离")
    assert core.list_memories(include_greenhouse=False) == []
    assert len(core.list_memories(include_greenhouse=True)) == 1


def test_recent_events_are_persistent_not_synthetic(repo: SQLiteGardenRepository) -> None:
    core = MemoryGardenCore(repository=repo)
    core.observe("我以后都喜欢深色模式，希望界面默认深色")
    core.open_court()
    events = core.recent_events(limit=50)
    types = {e.event_type for e in events}
    assert GardenEventType.seed_created in types
    assert GardenEventType.court_opened in types
    assert GardenEventType.verdict_made in types


def test_memory_planted_after_apply(repo: SQLiteGardenRepository) -> None:
    core = MemoryGardenCore(repository=repo)
    # SeedExtractor 需命中偏好/约束等信号；"我决定…" 未被 observe 分类时必须改写文案
    core.observe("我决定第一版先用 SQLite，希望以后默认本地存储")
    core.apply_verdict(core.open_court()[0])
    events = repo.list_garden_events(event_type=GardenEventType.memory_planted)
    assert len(events) >= 1


def test_dream_delegates_empty_returns_none(repo: SQLiteGardenRepository) -> None:
    core = MemoryGardenCore(repository=repo)
    assert core.dream() is None


def test_dream_with_materials_may_return_record(repo: SQLiteGardenRepository) -> None:
    core = MemoryGardenCore(repository=repo)
    core.observe("希望以后界面默认深色模式以保护视力")
    core.observe("希望以后长期使用深色主题降低刺眼")
    dr = core.dream()
    assert dr is None or dr.id is not None


def test_hold_verdict_no_growth_and_seed_becomes_held(repo: SQLiteGardenRepository) -> None:
    core = MemoryGardenCore(repository=repo)
    seed = Seed(
        content="最近项目进展正常没什么特别的事",
        source_excerpt="项目进展正常",
        signal_type=SeedSignalType.unknown,
    )
    repo.save_seed(seed)
    case = core.open_court([seed.id])[0]
    assert case.judge_verdict.verdict == CourtVerdictType.hold
    assert repo.get_seed(seed.id).status == SeedStatus.in_court
    assert core.apply_verdict(case) is None
    assert repo.get_seed(seed.id).status == SeedStatus.held
    assert core.list_memories() == []


def test_open_court_default_twice_does_not_duplicate_pending_trial(repo: SQLiteGardenRepository) -> None:
    """默认仅 pending：首次开庭后种子变为 in_court，第二次默认开庭列表为空。"""
    core = MemoryGardenCore(repository=repo)
    core.observe("我以后都喜欢用简洁中文回答，请从现在起保持这样")
    first = core.open_court()
    assert len(first) == 1
    second = core.open_court()
    assert second == []
    assert len(repo.list_court_cases()) == 1


def test_open_court_explicit_seed_ids_can_target_non_pending(repo: SQLiteGardenRepository) -> None:
    """显式 id 不按状态过滤：可对已是 in_court 的种子再次开庭（由调用方承担重复语义）。"""
    core = MemoryGardenCore(repository=repo)
    seeds = core.observe("我以后都喜欢深色模式，希望界面默认深色")
    sid = seeds[0].id
    core.open_court()
    assert repo.get_seed(sid).status == SeedStatus.in_court
    explicit = core.open_court([sid])
    assert len(explicit) == 1
    assert len(repo.list_court_cases(seed_id=sid)) == 2


def test_apply_verdict_requires_target_for_prune_merge_forget_greenhouse(repo: SQLiteGardenRepository) -> None:
    core = MemoryGardenCore(repository=repo)
    s = repo.save_seed(
        Seed(
            content="占位种子",
            source_excerpt="占",
            signal_type=SeedSignalType.preference,
        )
    )
    v_base = dict(prosecutor_argument="p", defender_argument="d", privacy_guard_argument="g")

    for vtype, msg in (
        (CourtVerdictType.prune, "PRUNE"),
        (CourtVerdictType.merge, "MERGE"),
        (CourtVerdictType.forget, "FORGET"),
        (CourtVerdictType.greenhouse, "GREENHOUSE"),
    ):
        case = CourtCase(
            seed_id=s.id,
            judge_verdict=CourtVerdict(verdict=vtype, reason="测试", confidence=0.5, target_memory_id=None),
            **v_base,
        )
        with pytest.raises(ValueError, match="target_memory_id"):
            core.apply_verdict(case)


def test_facade_has_no_search_harvest_brief(repo: SQLiteGardenRepository) -> None:
    core = MemoryGardenCore(repository=repo)
    assert core is not None
    for forbidden in (
        "search",
        "retrieve",
        "embedding",
        "vector",
        "harvest",
        "brief",
        "rerank",
    ):
        assert not hasattr(MemoryGardenCore, forbidden)
