"""Stage 5A-1：种子堆肥 compost_seed。"""

import pytest

from memory_garden.core.court.verdict import CourtVerdict, CourtVerdictType
from memory_garden.core.growth.compost import compost_memory_card, compost_seed
from memory_garden.core.journal import GardenJournal
from memory_garden.core.models import (
    CourtCase,
    GardenEventType,
    Seed,
    SeedSignalType,
    SeedStatus,
)
from memory_garden.core.court.engine import MemoryCourtEngine
from memory_garden.core.seeds import SeedObserver
from memory_garden.storage.sqlite import SQLiteGardenRepository


@pytest.fixture
def repo() -> SQLiteGardenRepository:
    r = SQLiteGardenRepository(":memory:")
    yield r
    r.close()


def _minimal_case(seed_id: str, verdict: CourtVerdictType) -> CourtCase:
    return CourtCase(
        seed_id=seed_id,
        prosecutor_argument="控方陈述占位",
        defender_argument="辩方陈述占位",
        privacy_guard_argument="隐私守卫占位",
        judge_verdict=CourtVerdict(
            verdict=verdict,
            reason="规则测试占位判决",
            confidence=0.75,
        ),
    )


def test_compost_with_compost_verdict_creates_record(repo: SQLiteGardenRepository) -> None:
    journal = GardenJournal(repo)
    observer = SeedObserver(repo, journal)
    seed = observer.observe("我好废，我不行")[0]
    engine = MemoryCourtEngine(repo, journal)
    case = engine.open_case(seed)
    assert case.judge_verdict.verdict == CourtVerdictType.compost

    rec = compost_seed(
        seed,
        case,
        reason="负面自评不宜身份化",
        nutrient="保留情境但不固化标签",
        repository=repo,
        journal=journal,
    )

    assert rec.discarded_surface == seed.content.strip()
    assert len(rec.retained_nutrient.strip()) > 0
    assert repo.get_seed(seed.id).status == SeedStatus.composted


def test_compost_does_not_create_memory_card(repo: SQLiteGardenRepository) -> None:
    journal = GardenJournal(repo)
    observer = SeedObserver(repo, journal)
    seed = observer.observe("我没用，什么都做不好")[0]
    case = MemoryCourtEngine(repo, journal).open_case(seed)
    compost_seed(seed, case, "堆肥", None, repo, journal)
    assert repo.list_memory_cards(include_greenhouse=True) == []


def test_compost_does_not_delete_seed_row(repo: SQLiteGardenRepository) -> None:
    journal = GardenJournal(repo)
    observer = SeedObserver(repo, journal)
    seed = observer.observe("我好废")[0]
    case = MemoryCourtEngine(repo, journal).open_case(seed)
    compost_seed(seed, case, "理由", "养分", repo, journal)
    assert repo.get_seed(seed.id).id == seed.id


def test_compost_writes_memory_composted_event(repo: SQLiteGardenRepository) -> None:
    journal = GardenJournal(repo)
    observer = SeedObserver(repo, journal)
    seed = observer.observe("我不行")[0]
    case = MemoryCourtEngine(repo, journal).open_case(seed)
    before = len(repo.list_garden_events(event_type=GardenEventType.memory_composted))
    compost_seed(seed, case, "测试堆肥", None, repo, journal)
    after = repo.list_garden_events(event_type=GardenEventType.memory_composted)
    assert len(after) == before + 1


def test_non_compost_verdict_raises(repo: SQLiteGardenRepository) -> None:
    journal = GardenJournal(repo)
    observer = SeedObserver(repo, journal)
    seed = observer.observe("我以后都喜欢深色模式")[0]
    case = MemoryCourtEngine(repo, journal).open_case(seed)
    assert case.judge_verdict.verdict == CourtVerdictType.plant
    with pytest.raises(ValueError, match="COMPOST"):
        compost_seed(seed, case, "错误调用", None, repo, journal)


def test_hard_forget_seed_cannot_compost_even_if_verdict_composite(repo: SQLiteGardenRepository) -> None:
    """显式遗忘语义不得走堆肥。"""
    journal = GardenJournal(repo)
    seed = Seed(
        content="请忘掉我刚才说的偏好，不要记住",
        source_excerpt="请忘掉",
        signal_type=SeedSignalType.preference,
    )
    repo.save_seed(seed)
    case = _minimal_case(seed.id, CourtVerdictType.compost)
    with pytest.raises(ValueError, match="遗忘"):
        compost_seed(seed, case, "试图堆肥", None, repo, journal)


def test_compost_requires_court_case(repo: SQLiteGardenRepository) -> None:
    journal = GardenJournal(repo)
    seed = Seed(content="我很差", source_excerpt="我很差", signal_type=SeedSignalType.negative_self_talk)
    repo.save_seed(seed)
    with pytest.raises(ValueError, match="CourtCase"):
        compost_seed(seed, None, "无案件", None, repo, journal)


def test_compost_memory_card_not_implemented(repo: SQLiteGardenRepository) -> None:
    with pytest.raises(NotImplementedError):
        compost_memory_card(memory_id="x")
