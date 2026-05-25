"""Stage 4A：规则版 Memory Court。"""

from pathlib import Path

import pytest

from memory_garden.core.court.engine import MemoryCourtEngine
from memory_garden.core.models import (
    CourtCase,
    GardenEventType,
    Seed,
    SeedSignalType,
)
import memory_garden.core.court as court_pkg
from memory_garden.core.court.verdict import CourtVerdictType
from memory_garden.storage.sqlite import SQLiteGardenRepository


@pytest.fixture
def repo() -> SQLiteGardenRepository:
    r = SQLiteGardenRepository(":memory:")
    yield r
    r.close()


@pytest.fixture
def engine(repo: SQLiteGardenRepository) -> MemoryCourtEngine:
    return MemoryCourtEngine(repo)


def _save(repo: SQLiteGardenRepository, seed: Seed) -> Seed:
    return repo.save_seed(seed)


def test_long_term_preference_verdict_plant(engine: MemoryCourtEngine, repo: SQLiteGardenRepository) -> None:
    seed = _save(
        repo,
        Seed(
            content="我以后都喜欢用简洁中文回答，请从现在起保持这样",
            source_excerpt="我以后都喜欢",
            signal_type=SeedSignalType.preference,
        ),
    )
    case = engine.open_case(seed)
    assert case.judge_verdict.verdict == CourtVerdictType.plant
    assert "r12_long_term_preference" in case.matched_rules


def test_negative_self_talk_not_plant_and_identity_risk(
    engine: MemoryCourtEngine,
    repo: SQLiteGardenRepository,
) -> None:
    seed = _save(
        repo,
        Seed(
            content="我好废，我不行，什么都做不好",
            source_excerpt="我好废",
            signal_type=SeedSignalType.negative_self_talk,
        ),
    )
    case = engine.open_case(seed)
    assert case.judge_verdict.verdict != CourtVerdictType.plant
    assert case.judge_verdict.verdict == CourtVerdictType.compost
    assert "identity_freeze_risk" in case.risk_flags


def test_sensitive_verdict_greenhouse_or_hold(engine: MemoryCourtEngine, repo: SQLiteGardenRepository) -> None:
    seed = _save(
        repo,
        Seed(
            content="我的银行卡密码写在病历诊断旁边，请不要外传",
            source_excerpt="银行卡",
            signal_type=SeedSignalType.sensitive_info,
        ),
    )
    case = engine.open_case(seed)
    assert case.judge_verdict.verdict in (
        CourtVerdictType.greenhouse,
        CourtVerdictType.hold,
    )
    assert "r02_sensitive_personal_info" in case.matched_rules


def test_explicit_forget_verdict_forget_not_plant(engine: MemoryCourtEngine, repo: SQLiteGardenRepository) -> None:
    seed = _save(
        repo,
        Seed(
            content="请忘掉我刚才说的偏好，不要保存那条",
            source_excerpt="请忘掉",
            signal_type=SeedSignalType.preference,
        ),
    )
    case = engine.open_case(seed)
    assert case.judge_verdict.verdict == CourtVerdictType.forget
    assert case.judge_verdict.verdict != CourtVerdictType.plant
    assert "r01_explicit_forget_request" in case.matched_rules


def test_negates_prior_without_target_hold_or_missing_flag(
    engine: MemoryCourtEngine,
    repo: SQLiteGardenRepository,
) -> None:
    seed = _save(
        repo,
        Seed(
            content="之前那个方向不要了，我不再采用旧方案",
            source_excerpt="之前那个方向",
            signal_type=SeedSignalType.unknown,
        ),
    )
    case = engine.open_case(seed)
    assert case.judge_verdict.verdict == CourtVerdictType.hold
    assert "prune_target_missing" in case.risk_flags


def test_unknown_seed_hold(engine: MemoryCourtEngine, repo: SQLiteGardenRepository) -> None:
    seed = _save(
        repo,
        Seed(
            content="今天天气还行吧随便聊聊",
            source_excerpt="今天天气",
            signal_type=SeedSignalType.unknown,
        ),
    )
    case = engine.open_case(seed)
    # "今天天气" matches ephemeral markers → compost
    assert case.judge_verdict.verdict == CourtVerdictType.compost
    assert "r13_ephemeral_content" in case.matched_rules


def test_court_case_roundtrip(engine: MemoryCourtEngine, repo: SQLiteGardenRepository) -> None:
    seed = _save(
        repo,
        Seed(
            content="我希望界面按钮大一点",
            source_excerpt="我希望",
            signal_type=SeedSignalType.preference,
        ),
    )
    case = engine.open_case(seed)
    loaded = repo.get_court_case(case.id)
    assert isinstance(loaded, CourtCase)
    assert loaded.judge_verdict.verdict == case.judge_verdict.verdict


def test_triple_arguments_nonempty(engine: MemoryCourtEngine, repo: SQLiteGardenRepository) -> None:
    seed = _save(
        repo,
        Seed(
            content="我不喜欢太啰嗦的解释",
            source_excerpt="我不喜欢",
            signal_type=SeedSignalType.constraint,
        ),
    )
    case = engine.open_case(seed)
    assert len(case.prosecutor_argument.strip()) > 0
    assert len(case.defender_argument.strip()) > 0
    assert len(case.privacy_guard_argument.strip()) > 0


def test_verdict_reason_and_confidence_bounds(engine: MemoryCourtEngine, repo: SQLiteGardenRepository) -> None:
    seed = _save(
        repo,
        Seed(
            content="我决定第一版先用 SQLite",
            source_excerpt="我决定",
            signal_type=SeedSignalType.decision,
        ),
    )
    case = engine.open_case(seed)
    v = case.judge_verdict
    assert len(v.reason.strip()) > 0
    assert 0.0 <= v.confidence <= 1.0


def test_each_trial_writes_two_events(engine: MemoryCourtEngine, repo: SQLiteGardenRepository) -> None:
    seed = _save(
        repo,
        Seed(
            content="以后回复请保持简短",
            source_excerpt="以后回复",
            signal_type=SeedSignalType.preference,
        ),
    )
    before = len(repo.list_garden_events())
    case = engine.open_case(seed)
    events = repo.list_garden_events()
    assert len(events) == before + 2
    case_events = [e for e in events if e.object_id == case.id]
    assert len(case_events) == 2
    assert {e.event_type for e in case_events} == {
        GardenEventType.court_opened,
        GardenEventType.verdict_made,
    }


def test_verdict_made_metadata_contains_rules_and_flags(
    engine: MemoryCourtEngine,
    repo: SQLiteGardenRepository,
) -> None:
    seed = _save(
        repo,
        Seed(
            content="我不行，我好废",
            source_excerpt="我不行",
            signal_type=SeedSignalType.negative_self_talk,
        ),
    )
    case = engine.open_case(seed)
    verdict_ev = next(
        e
        for e in repo.list_garden_events()
        if e.object_id == case.id and e.event_type == GardenEventType.verdict_made
    )
    assert verdict_ev.metadata["verdict"] == case.judge_verdict.verdict.value
    assert verdict_ev.metadata["matched_rules"] == case.matched_rules
    assert verdict_ev.metadata["risk_flags"] == case.risk_flags


def test_court_does_not_create_side_records(engine: MemoryCourtEngine, repo: SQLiteGardenRepository) -> None:
    seed = _save(
        repo,
        Seed(
            content="以后都用中文回复我",
            source_excerpt="以后都",
            signal_type=SeedSignalType.preference,
        ),
    )
    engine.open_case(seed)
    assert repo.list_memory_cards(include_greenhouse=True) == []
    assert repo.list_compost_records() == []
    assert repo.list_greenhouse_records() == []
    assert repo.list_pruning_records() == []


def test_engine_source_has_no_llm_tokens() -> None:
    src = Path(court_pkg.engine.__file__).read_text(encoding="utf-8").casefold()
    for token in ("openai", "anthropic", "llm", "embedding", "tiktoken"):
        assert token not in src


def test_negates_prior_with_target_prune(engine: MemoryCourtEngine, repo: SQLiteGardenRepository) -> None:
    seed = _save(
        repo,
        Seed(
            content="之前那个方向不要了，我要改掉旧结论",
            source_excerpt="之前那个方向",
            signal_type=SeedSignalType.correction,
            context={"target_memory_id": "mem-target-1"},
        ),
    )
    case = engine.open_case(seed)
    assert case.judge_verdict.verdict == CourtVerdictType.prune
    assert case.judge_verdict.target_memory_id == "mem-target-1"


def test_open_cases_batch(engine: MemoryCourtEngine, repo: SQLiteGardenRepository) -> None:
    s1 = _save(
        repo,
        Seed(content="我喜欢深色主题", source_excerpt="我喜欢", signal_type=SeedSignalType.preference),
    )
    s2 = _save(
        repo,
        Seed(content="闲聊无结构内容测试", source_excerpt="闲聊", signal_type=SeedSignalType.unknown),
    )
    cases = engine.open_cases([s1, s2])
    assert len(cases) == 2
