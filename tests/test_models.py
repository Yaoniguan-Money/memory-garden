"""核心领域模型的单元测试（Stage 1A）。"""

import json
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from memory_garden.core.court.verdict import CourtVerdict, CourtVerdictType
from memory_garden.core.growth.lifecycle import MemoryLifecycle
from memory_garden.core.models import (
    CompostRecord,
    CourtCase,
    DreamRecord,
    GardenEvent,
    GardenEventType,
    GardenObjectType,
    GreenhouseAccessPolicy,
    GreenhouseRecord,
    MemoryCard,
    MemoryType,
    PruningRecord,
    Seed,
    SeedSignalType,
    SeedStatus,
    SensitivityLevel,
)


def test_seed_defaults_and_empty_content() -> None:
    s = Seed(content="  有效内容  ", source_excerpt="摘录")
    assert s.status == SeedStatus.pending
    assert s.signal_type == SeedSignalType.unknown
    assert 0.0 <= s.confidence <= 1.0
    assert s.content == "有效内容"
    assert len(s.id) == 36
    assert s.context == {}
    dumped_seed = s.model_dump(mode="json")
    assert dumped_seed["context"] == {}

    with pytest.raises(ValidationError):
        Seed(content="", source_excerpt="x")
    with pytest.raises(ValidationError):
        Seed(content="   ", source_excerpt="x")


def test_confidence_importance_bounds() -> None:
    with pytest.raises(ValidationError):
        Seed(content="a", source_excerpt="b", confidence=1.5)
    with pytest.raises(ValidationError):
        MemoryCard(
            title="t",
            essence="e",
            fragrance="f",
            thorns="t",
            importance=-0.1,
        )


def test_memory_card_defaults_lists_and_json_dump() -> None:
    m = MemoryCard(title="标题", essence="摘要", fragrance="香", thorns="刺")
    assert m.lifecycle == MemoryLifecycle.sprout
    assert m.tags == []
    assert m.roots == []
    assert m.branches == []
    assert m.source_seed_ids == []
    assert m.memory_type == MemoryType.unknown

    data = m.model_dump(mode="json")
    json.dumps(data)
    assert data["lifecycle"] == "sprout"


def test_court_verdict_reason_required() -> None:
    with pytest.raises(ValidationError):
        CourtVerdict(verdict=CourtVerdictType.plant, reason="")
    with pytest.raises(ValidationError):
        CourtVerdict(verdict=CourtVerdictType.plant, reason="   ")

    v = CourtVerdict(verdict=CourtVerdictType.hold, reason="保留观察")
    assert v.reason == "保留观察"


def test_court_case_structured_judge_verdict() -> None:
    verdict = CourtVerdict(
        verdict=CourtVerdictType.plant,
        reason="符合长期偏好",
        confidence=0.9,
    )
    case = CourtCase(
        seed_id="seed-1",
        prosecutor_argument="不应记",
        defender_argument="应该记",
        privacy_guard_argument="低风险",
        judge_verdict=verdict,
    )
    assert isinstance(case.judge_verdict, CourtVerdict)
    assert case.judge_verdict.verdict == CourtVerdictType.plant

    # 判决字段必须是结构化模型，不能是纯字符串
    with pytest.raises(ValidationError):
        CourtCase(
            seed_id="seed-1",
            prosecutor_argument="a",
            defender_argument="b",
            privacy_guard_argument="c",
            judge_verdict="plant",  # type: ignore[arg-type]
        )


def test_dream_record_four_text_fields_nonempty() -> None:
    with pytest.raises(ValidationError):
        DreamRecord(
            observation="",
            reflection="r",
            transformation="t",
            morning_garden="m",
        )

    d = DreamRecord(
        observation="白日见闻",
        reflection="夜里所想",
        transformation="转化",
        morning_garden="晨起花园",
    )
    assert d.observation == "白日见闻"


def test_compost_at_least_one_source_id() -> None:
    with pytest.raises(ValidationError):
        CompostRecord(
            discarded_surface="表层",
            reason="理由",
        )

    with pytest.raises(ValidationError):
        CompostRecord(
            source_seed_id="",
            source_memory_id=None,
            discarded_surface="表层",
            reason="理由",
        )

    with pytest.raises(ValidationError):
        CompostRecord(
            source_seed_id="   ",
            source_memory_id=None,
            discarded_surface="表层",
            reason="理由",
        )

    with pytest.raises(ValidationError):
        CompostRecord(
            source_seed_id="",
            source_memory_id="",
            discarded_surface="表层",
            reason="理由",
        )

    c = CompostRecord(
        source_seed_id="sid",
        discarded_surface="表层",
        reason="理由",
    )
    assert c.source_memory_id is None


def test_greenhouse_sensitivity_and_access_policy() -> None:
    g = GreenhouseRecord(memory_id="m1", reason="敏感")
    assert g.sensitivity_level == SensitivityLevel.medium
    assert g.access_policy == GreenhouseAccessPolicy.excluded_by_default

    g2 = GreenhouseRecord(
        memory_id="m2",
        reason="原因",
        sensitivity_level=SensitivityLevel.high,
        access_policy=GreenhouseAccessPolicy.requires_explicit_include,
    )
    assert g2.sensitivity_level == SensitivityLevel.high


def test_pruning_lifecycle_enum() -> None:
    p = PruningRecord(
        memory_id="mid",
        reason="用户否定旧结论",
        old_lifecycle=MemoryLifecycle.rooted,
        new_lifecycle=MemoryLifecycle.pruned,
    )
    assert p.old_lifecycle == MemoryLifecycle.rooted
    assert p.new_lifecycle == MemoryLifecycle.pruned


def test_garden_event_enum_and_metadata_default() -> None:
    e = GardenEvent(
        event_type=GardenEventType.verdict_made,
        object_type=GardenObjectType.court_case,
        object_id="cid",
        summary="作出判决",
    )
    assert e.metadata == {}
    assert e.event_type.value == "verdict_made"


@pytest.mark.parametrize(
    "model_cls,kwargs",
    [
        (
            Seed,
            {"content": "c", "source_excerpt": "s"},
        ),
        (
            MemoryCard,
            {"title": "t", "essence": "e", "fragrance": "f", "thorns": "th"},
        ),
        (
            CourtCase,
            {
                "seed_id": "s",
                "prosecutor_argument": "p",
                "defender_argument": "d",
                "privacy_guard_argument": "pg",
                "judge_verdict": CourtVerdict(
                    verdict=CourtVerdictType.plant,
                    reason="r",
                ),
            },
        ),
        (
            DreamRecord,
            {
                "observation": "o",
                "reflection": "r",
                "transformation": "t",
                "morning_garden": "m",
            },
        ),
        (
            CompostRecord,
            {
                "source_memory_id": "mid",
                "discarded_surface": "ds",
                "reason": "why",
            },
        ),
        (
            GreenhouseRecord,
            {"memory_id": "x", "reason": "y"},
        ),
        (
            PruningRecord,
            {
                "memory_id": "m",
                "reason": "r",
                "old_lifecycle": MemoryLifecycle.bloom,
                "new_lifecycle": MemoryLifecycle.fading,
            },
        ),
        (
            GardenEvent,
            {
                "event_type": GardenEventType.seed_created,
                "object_type": GardenObjectType.seed,
                "object_id": "id",
                "summary": "摘要",
            },
        ),
    ],
)
def test_all_core_models_json_dump(model_cls, kwargs) -> None:
    obj = model_cls(**kwargs)
    data = obj.model_dump(mode="json")
    json.dumps(data)


def test_datetime_utc_serialization() -> None:
    fixed = datetime(2024, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    s = Seed(content="c", source_excerpt="s", created_at=fixed)
    dumped = s.model_dump(mode="json")
    assert "2024" in dumped["created_at"]
