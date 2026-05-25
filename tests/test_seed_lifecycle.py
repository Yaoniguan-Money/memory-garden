"""Stage 3A：规则版 Seed 观察与持久化。"""

from pathlib import Path

import pytest

from memory_garden.core.journal import GardenJournal
from memory_garden.core.models import GardenEventType, SeedSignalType, SeedStatus
from memory_garden.core import seeds as seeds_module
from memory_garden.core.seeds import SeedExtractor, SeedObserver
from memory_garden.storage.sqlite import SQLiteGardenRepository


@pytest.fixture
def memory_repo() -> SQLiteGardenRepository:
    repo = SQLiteGardenRepository(":memory:")
    yield repo
    repo.close()


def test_long_term_preference_produces_pending_seed(memory_repo: SQLiteGardenRepository) -> None:
    journal = GardenJournal(memory_repo)
    observer = SeedObserver(memory_repo, journal)
    text = "我以后都喜欢用简洁中文回答，请以后回复不要太啰嗦"
    seeds = observer.observe(text)
    assert len(seeds) == 1
    s = seeds[0]
    assert s.status == SeedStatus.pending
    assert s.signal_type == SeedSignalType.preference
    assert isinstance(s.context, dict)
    assert isinstance(s.tags, list)


def test_seed_persisted_in_repository(memory_repo: SQLiteGardenRepository) -> None:
    observer = SeedObserver(memory_repo)
    text = "我更喜欢 local-first 的设计方案"
    seeds = observer.observe(text)
    assert len(seeds) == 1
    loaded = memory_repo.get_seed(seeds[0].id)
    assert loaded.content == text.strip()
    assert loaded.signal_type == SeedSignalType.preference


def test_observe_writes_seed_created_event(memory_repo: SQLiteGardenRepository) -> None:
    journal = GardenJournal(memory_repo)
    observer = SeedObserver(memory_repo, journal)
    observer.observe("从现在起我希望回复尽量简短")
    events = memory_repo.list_garden_events(event_type=GardenEventType.seed_created)
    assert len(events) == 1
    ev = events[0]
    assert ev.event_type == GardenEventType.seed_created
    assert ev.object_type.value == "seed"
    assert "signal_type" in ev.metadata
    assert "tags" in ev.metadata
    assert "confidence" in ev.metadata


def test_empty_input_no_seed(memory_repo: SQLiteGardenRepository) -> None:
    observer = SeedObserver(memory_repo)
    assert observer.observe("") == []
    assert observer.observe("   \n\t  ") == []
    assert memory_repo.list_seeds() == []


def test_forget_intent_no_preference_seed(memory_repo: SQLiteGardenRepository) -> None:
    observer = SeedObserver(memory_repo)
    blocked = [
        "请忘掉我刚才说的那句偏好",
        "不要记住这段对话",
        "别记住我的密码",
        "删除记忆里的旧地址",
        "forget this message",
    ]
    for t in blocked:
        assert observer.observe(t) == []
    assert memory_repo.list_seeds() == []


def test_negative_self_talk_seed(memory_repo: SQLiteGardenRepository) -> None:
    observer = SeedObserver(memory_repo)
    seeds = observer.observe("我不行，我好废，我什么都没做好")
    assert len(seeds) == 1
    assert seeds[0].signal_type == SeedSignalType.negative_self_talk
    assert seeds[0].status == SeedStatus.pending


def test_sensitive_info_seed(memory_repo: SQLiteGardenRepository) -> None:
    observer = SeedObserver(memory_repo)
    seeds = observer.observe("我的银行卡密码写在了病历诊断旁边")
    assert len(seeds) == 1
    assert seeds[0].signal_type == SeedSignalType.sensitive_info
    assert seeds[0].status == SeedStatus.pending


def test_observe_does_not_create_memory_card(memory_repo: SQLiteGardenRepository) -> None:
    observer = SeedObserver(memory_repo)
    observer.observe("以后回复用中文就好")
    observer.observe("我很差劲我不行")
    assert memory_repo.list_memory_cards(include_greenhouse=True) == []


def test_seed_module_has_no_llm_or_embedding_imports() -> None:
    """规则实现：不引入向量 / LLM 相关符号。"""
    src = Path(seeds_module.__file__).read_text(encoding="utf-8").casefold()
    for token in ("openai", "embedding", "vector", "sentence_transform", "tiktoken"):
        assert token not in src


def test_seed_context_dict_tags_list(memory_repo: SQLiteGardenRepository) -> None:
    observer = SeedObserver(memory_repo)
    seeds = observer.observe("希望以后界面简洁一点")
    assert len(seeds) == 1
    assert isinstance(seeds[0].context, dict)
    assert isinstance(seeds[0].tags, list)


def test_extractor_returns_models_without_side_effect(memory_repo: SQLiteGardenRepository) -> None:
    """SeedExtractor 纯抽取；不经 Observer 不会写入仓储。"""
    ex = SeedExtractor()
    seeds = ex.extract("我希望按钮大一点")
    assert len(seeds) == 1
    assert memory_repo.list_seeds() == []


def test_plant_preference_seed_full_flow(memory_repo: SQLiteGardenRepository) -> None:
    """长期偏好种子 -> 法庭 PLANT -> plant -> MemoryCard。"""
    from memory_garden.core.cards import plant
    from memory_garden.core.court.engine import MemoryCourtEngine
    from memory_garden.core.court.verdict import CourtVerdictType
    from memory_garden.core.models import MemoryLifecycle, SeedStatus

    journal = GardenJournal(memory_repo)
    observer = SeedObserver(memory_repo, journal)
    seed = observer.observe("我以后都喜欢用简洁中文回答")[0]
    engine = MemoryCourtEngine(memory_repo, journal)
    case = engine.open_case(seed)
    assert case.judge_verdict.verdict == CourtVerdictType.plant

    card = plant(seed, case, memory_repo, journal)

    assert card.lifecycle == MemoryLifecycle.sprout
    assert seed.id in card.source_seed_ids
    assert case.id in card.court_case_ids
    assert memory_repo.get_seed(seed.id).status == SeedStatus.planted


def test_plant_updates_seed_status_planted(memory_repo: SQLiteGardenRepository) -> None:
    from memory_garden.core.cards import plant
    from memory_garden.core.court.engine import MemoryCourtEngine
    from memory_garden.core.models import SeedStatus

    journal = GardenJournal(memory_repo)
    observer = SeedObserver(memory_repo, journal)
    seed = observer.observe("从现在起我希望界面简洁")[0]
    case = MemoryCourtEngine(memory_repo, journal).open_case(seed)
    plant(seed, case, memory_repo, journal)
    assert memory_repo.get_seed(seed.id).status == SeedStatus.planted


def test_plant_non_verdict_raises(memory_repo: SQLiteGardenRepository) -> None:
    from memory_garden.core.cards import plant
    from memory_garden.core.court.engine import MemoryCourtEngine

    journal = GardenJournal(memory_repo)
    observer = SeedObserver(memory_repo, journal)
    seed = observer.observe("我不行我好废")[0]
    case = MemoryCourtEngine(memory_repo, journal).open_case(seed)
    with pytest.raises(ValueError, match="PLANT"):
        plant(seed, case, memory_repo, journal)


def test_plant_writes_memory_planted_event(memory_repo: SQLiteGardenRepository) -> None:
    from memory_garden.core.cards import plant
    from memory_garden.core.court.engine import MemoryCourtEngine
    from memory_garden.core.models import GardenEventType

    journal = GardenJournal(memory_repo)
    observer = SeedObserver(memory_repo, journal)
    seed = observer.observe("\u4ee5\u540e\u56de\u590d\u8bf7\u7528\u4e2d\u6587")[0]
    case = MemoryCourtEngine(memory_repo, journal).open_case(seed)
    before = len(memory_repo.list_garden_events(event_type=GardenEventType.memory_planted))
    plant(seed, case, memory_repo, journal)
    assert (
        len(memory_repo.list_garden_events(event_type=GardenEventType.memory_planted))
        == before + 1
    )


def test_plant_no_side_growth_records(memory_repo: SQLiteGardenRepository) -> None:
    from memory_garden.core.cards import plant
    from memory_garden.core.court.engine import MemoryCourtEngine

    journal = GardenJournal(memory_repo)
    seed = SeedObserver(memory_repo, journal).observe("我喜欢深色主题")[0]
    case = MemoryCourtEngine(memory_repo, journal).open_case(seed)
    plant(seed, case, memory_repo, journal)
    assert memory_repo.list_compost_records() == []
    assert memory_repo.list_greenhouse_records() == []
    assert memory_repo.list_pruning_records() == []


def test_merge_seed_into_memory_flow(memory_repo: SQLiteGardenRepository) -> None:
    from memory_garden.core.cards import merge_seed_into_memory, plant
    from memory_garden.core.court.engine import MemoryCourtEngine
    from memory_garden.core.models import SeedStatus

    journal = GardenJournal(memory_repo)
    s_target = SeedObserver(memory_repo, journal).observe(
        "\u6211\u4ee5\u540e\u90fd\u4e60\u60ef\u7528\u4e2d\u6587\u754c\u9762"
    )[0]
    case_t = MemoryCourtEngine(memory_repo, journal).open_case(s_target)
    target_card = plant(s_target, case_t, memory_repo, journal)

    s_merge = SeedObserver(memory_repo, journal).observe(
        "\u6211\u5e0c\u671b\u6309\u94ae\u66f4\u5927\u4e00\u4e9b"
    )[0]
    n_cards = len(memory_repo.list_memory_cards(include_greenhouse=True))
    merge_seed_into_memory(s_merge, target_card.id, "补充同一主题偏好", memory_repo, journal)

    assert len(memory_repo.list_memory_cards(include_greenhouse=True)) == n_cards
    assert memory_repo.get_seed(s_merge.id).status == SeedStatus.merged
    updated = memory_repo.get_memory_card(target_card.id)
    assert s_merge.id in updated.source_seed_ids


def test_merge_seed_with_court_case_id(memory_repo: SQLiteGardenRepository) -> None:
    from memory_garden.core.cards import merge_seed_into_memory, plant
    from memory_garden.core.court.engine import MemoryCourtEngine

    journal = GardenJournal(memory_repo)
    base = SeedObserver(memory_repo, journal).observe(
        "\u6211\u504f\u597d local-first \u67b6\u6784"
    )[0]
    c0 = MemoryCourtEngine(memory_repo, journal).open_case(base)
    target = plant(base, c0, memory_repo, journal)

    extra = SeedObserver(memory_repo, journal).observe(
        "\u6211\u5e0c\u671b\u7ee7\u7eed\u5f3a\u8c03\u79bb\u7ebf\u4f18\u5148"
    )[0]
    c1 = MemoryCourtEngine(memory_repo, journal).open_case(extra)
    merge_seed_into_memory(extra, target.id, "合并", memory_repo, journal, court_case=c1)
    t2 = memory_repo.get_memory_card(target.id)
    assert c1.id in t2.court_case_ids


def test_merge_seed_writes_merged_event(memory_repo: SQLiteGardenRepository) -> None:
    from memory_garden.core.cards import merge_seed_into_memory, plant
    from memory_garden.core.court.engine import MemoryCourtEngine
    from memory_garden.core.models import GardenEventType

    journal = GardenJournal(memory_repo)
    a = SeedObserver(memory_repo, journal).observe(
        "\u4ee5\u540e\u56de\u590d\u8bf7\u7528\u7b80\u6d01\u4e2d\u6587"
    )[0]
    ca = MemoryCourtEngine(memory_repo, journal).open_case(a)
    target = plant(a, ca, memory_repo, journal)
    b = SeedObserver(memory_repo, journal).observe(
        "\u6211\u5e0c\u671b\u5c11\u7528\u611f\u53f9\u53f7"
    )[0]
    before = len(memory_repo.list_garden_events(event_type=GardenEventType.memory_merged))
    merge_seed_into_memory(b, target.id, "合并", memory_repo, journal)
    assert (
        len(memory_repo.list_garden_events(event_type=GardenEventType.memory_merged))
        == before + 1
    )
