"""第四层：Cognition 模型单元测试。"""

import pytest
from pydantic import ValidationError

from memory_garden.cognition.models import (
    GardenBriefDraft,
    HarvestCandidate,
    HarvestMode,
    HarvestRerankResult,
    HarvestTrace,
)


class TestHarvestMode:
    def test_rules_only_is_default(self) -> None:
        assert HarvestMode.RULES_ONLY == "rules_only"

    def test_all_modes_exist(self) -> None:
        modes = {m.value for m in HarvestMode}
        assert modes == {"rules_only", "semantic_only", "hybrid"}


class TestHarvestCandidate:
    def test_minimal_construction(self) -> None:
        c = HarvestCandidate(
            memory_id="mem-1",
            source_ids=["mem-1"],
            text="some text",
        )
        assert c.memory_id == "mem-1"
        assert c.source_ids == ["mem-1"]
        assert c.text == "some text"
        assert c.tags == []
        assert c.rule_score is None
        assert c.semantic_score is None
        assert c.rerank_score is None

    def test_full_construction(self) -> None:
        c = HarvestCandidate(
            memory_id="mem-2",
            source_ids=["mem-2", "seed-1"],
            text="full text with details",
            tags=["tag-a", "tag-b"],
            rule_score=0.85,
            semantic_score=0.72,
            rerank_score=0.91,
            reasons=["lexical_hit", "semantic_match"],
        )
        assert c.memory_id == "mem-2"
        assert c.rule_score == 0.85
        assert c.semantic_score == 0.72
        assert c.rerank_score == 0.91
        assert len(c.reasons) == 2

    def test_memory_id_required(self) -> None:
        with pytest.raises(ValidationError):
            HarvestCandidate(source_ids=[], text="x")

    def test_source_ids_default_empty(self) -> None:
        c = HarvestCandidate(memory_id="m1", source_ids=[], text="x")
        assert c.source_ids == []


class TestHarvestRerankResult:
    def test_construction(self) -> None:
        c1 = HarvestCandidate(memory_id="m1", source_ids=["m1"], text="a")
        c2 = HarvestCandidate(memory_id="m2", source_ids=["m2"], text="b")
        result = HarvestRerankResult(
            candidates=[c1, c2],
            provider_name="fake",
            prompt_version="v1",
        )
        assert len(result.candidates) == 2
        assert result.provider_name == "fake"
        assert result.prompt_version == "v1"

    def test_default_metadata(self) -> None:
        result = HarvestRerankResult(
            candidates=[],
            provider_name="test",
        )
        assert result.metadata == {}
        assert result.prompt_version is None


class TestGardenBriefDraft:
    def test_full_construction(self) -> None:
        draft = GardenBriefDraft(
            intent="测试意图",
            use="可参考记忆标识",
            avoid="不视为确定事实",
            style="中性简短",
            safety="不断言偏好",
            nudge="编排线索",
            source_memory_ids=["mem-1", "mem-2"],
        )
        assert draft.intent == "测试意图"
        assert len(draft.source_memory_ids) == 2
        assert draft.token_estimate is None

    def test_required_fields(self) -> None:
        with pytest.raises(ValidationError):
            GardenBriefDraft(
                use="u", avoid="a", style="s", safety="sf", nudge="n",
                source_memory_ids=[],
            )


class TestHarvestTrace:
    def test_full_construction(self) -> None:
        trace = HarvestTrace(
            query="用户查询",
            mode=HarvestMode.HYBRID,
            candidate_memory_ids=["m1", "m2", "m3"],
            selected_memory_ids=["m1", "m2"],
            rejected_memory_ids=["m3"],
            score_breakdown={"lexical": 0.8, "semantic": 0.6},
            provider_name="fake",
            fallback_used=False,
        )
        assert trace.query == "用户查询"
        assert trace.mode == HarvestMode.HYBRID
        assert len(trace.selected_memory_ids) == 2
        assert len(trace.rejected_memory_ids) == 1
        assert trace.fallback_used is False
        assert trace.warnings == []

    def test_fallback_trace(self) -> None:
        trace = HarvestTrace(
            query="q",
            mode=HarvestMode.RULES_ONLY,
            candidate_memory_ids=["m1"],
            selected_memory_ids=["m1"],
            rejected_memory_ids=[],
            score_breakdown={},
            fallback_used=True,
            warnings=["missing embedding_provider"],
        )
        assert trace.fallback_used is True
        assert len(trace.warnings) == 1
