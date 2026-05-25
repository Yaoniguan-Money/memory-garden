"""第四层：Harvest Cognitive 模式集成测试。

测试 GardenHarvester.harvest_cognitive() 融合路径：
- 自动回退到 rules_only（无提供者时）
- 词法+语义合并去重
- LLM 重排序不新增 memory_id
- 简报携带 source_memory_ids
- 可追溯性校验通过
"""

import pytest

from memory_garden.core.models import MemoryCard
from memory_garden.harvest.harvester import GardenHarvester
from memory_garden.harvest.models import (
    HarvestQuery,
    MemoryLens,
)
from memory_garden.harvest.policy import HarvestBudgetPolicy
from memory_garden.cognition.fake_providers import (
    FakeBriefWriterProvider,
    FakeHarvestRerankerProvider,
)
from memory_garden.providers import FakeEmbeddingProvider
from memory_garden.cognition.models import HarvestMode as CogHarvestMode, HarvestTrace
from memory_garden.cognition.models import (
    GardenBriefDraft,
    HarvestCandidate,
    HarvestRerankResult,
)
from memory_garden.cognition.hybrid import run_hybrid_harvest


def _make_memory(
    mid: str,
    title: str = "",
    essence: str = "",
    tags: list[str] | None = None,
    lifecycle: str = "sprout",
) -> MemoryCard:
    return MemoryCard(
        id=mid,
        title=title or mid,
        essence=essence or "记忆内容",
        fragrance="香",
        thorns="无",
        tags=tags or [],
        lifecycle=lifecycle,  # type: ignore[arg-type]
        importance=0.5,
        confidence=0.5,
        memory_type="preference",  # type: ignore[arg-type]
    )


def _make_lens(lens_id: str = "lens-1", name: str = "test") -> MemoryLens:
    return MemoryLens(lens_id=lens_id, name=name, facet_keys=["preference"])


class _BadReranker:
    def rerank(self, query, candidates, policy=None):
        invented = HarvestCandidate(
            memory_id="invented",
            source_ids=["invented"],
            text="provider invented this",
            rerank_score=1.0,
        )
        return HarvestRerankResult(
            candidates=[invented, *candidates],
            provider_name="bad_reranker",
            prompt_version="bad_v1",
        )


class _BadBriefWriter:
    def write_brief(self, query, selected_memories, policy=None):
        return GardenBriefDraft(
            intent="bad",
            use="bad",
            avoid="bad",
            style="bad",
            safety="bad",
            nudge="bad",
            source_memory_ids=["invented"],
        )


# ── Fallback tests ────────────────────────────────────────────────


class TestCognitiveFallback:
    def test_without_providers_falls_back_to_rules_only(self) -> None:
        harvester = GardenHarvester()
        query = HarvestQuery(
            raw_user_text="我喜欢深色模式",
            lenses=[_make_lens()],
        )
        memories = [
            _make_memory("m1", title="深色模式", essence="用户喜欢深色界面"),
            _make_memory("m2", title="无关", essence="其他内容"),
        ]
        brief, cog_trace = harvester.harvest_cognitive(query, memories)
        assert brief is not None
        assert cog_trace is not None
        assert isinstance(cog_trace, HarvestTrace)
        assert cog_trace.fallback_used is True
        assert cog_trace.mode == CogHarvestMode.RULES_ONLY

    def test_harvest_still_works_normally(self) -> None:
        """harvest() 纯规则模式不受影响。"""
        harvester = GardenHarvester()
        query = HarvestQuery(
            raw_user_text="深色模式",
            lenses=[_make_lens()],
        )
        memories = [
            _make_memory("m1", title="深色模式偏好", essence="用户喜欢深色主题"),
        ]
        trace = harvester.harvest(query, memories)
        assert trace.brief is not None
        assert len(trace.candidates) > 0


# ── Hybrid mode tests ─────────────────────────────────────────────


class TestHarvestCognitive:
    @pytest.fixture
    def harvester(self):
        return GardenHarvester(
            emb_provider=FakeEmbeddingProvider(dimensions=64),
            rank_provider=FakeHarvestRerankerProvider(),
            cog_writer=FakeBriefWriterProvider(),
        )

    @pytest.fixture
    def memories(self):
        return [
            _make_memory("m1", title="深色模式偏好", essence="用户更喜欢深色主题界面", tags=["preference"]),
            _make_memory("m2", title="字体大小", essence="用户需要大号字体便于阅读", tags=["preference"]),
            _make_memory("m3", title="Python 项目", essence="用户正在开发 Python Web 项目", tags=["project"]),
            _make_memory("m4", title="React 前端", essence="使用 React 和 TypeScript", tags=["project"]),
            _make_memory("m5", title="无关记忆", essence="完全不相关的其他内容", tags=["other"]),
        ]

    def test_cognitive_produces_brief_and_trace(self, harvester, memories) -> None:
        query = HarvestQuery(
            raw_user_text="我喜欢深色模式",
            lenses=[_make_lens("l1", "界面偏好")],
        )
        brief, cog_trace = harvester.harvest_cognitive(query, memories)
        assert brief is not None
        assert brief.intent
        assert brief.use
        assert isinstance(cog_trace, HarvestTrace)

    def test_cognitive_hybrid_mode(self, harvester, memories) -> None:
        query = HarvestQuery(
            raw_user_text="深色模式 Python 项目",
            lenses=[_make_lens()],
        )
        brief, cog_trace = harvester.harvest_cognitive(
            query, memories, mode=CogHarvestMode.HYBRID,
        )
        assert cog_trace.mode == CogHarvestMode.HYBRID
        assert len(cog_trace.candidate_memory_ids) >= 1

    def test_cognitive_brief_has_source_memory_ids(self, harvester, memories) -> None:
        query = HarvestQuery(
            raw_user_text="界面偏好",
            lenses=[_make_lens()],
        )
        brief, cog_trace = harvester.harvest_cognitive(query, memories)
        assert len(brief.source_memory_ids) > 0
        # 所有 source_memory_ids 必须在候选池中
        for mid in brief.source_memory_ids:
            assert mid in cog_trace.candidate_memory_ids, f"Brief source {mid} not in candidates"

    def test_cognitive_no_invented_memory_ids(self, harvester, memories) -> None:
        """LLM 不能凭空生成不在候选池中的 memory_id。"""
        query = HarvestQuery(
            raw_user_text="测试",
            lenses=[_make_lens()],
        )
        brief, cog_trace = harvester.harvest_cognitive(query, memories)
        valid_ids = {m.id for m in memories}
        for mid in brief.source_memory_ids:
            assert mid in valid_ids, f"Brief references {mid} not in input memories"
        for mid in cog_trace.selected_memory_ids:
            assert mid in valid_ids, f"Selected {mid} not in input memories"

    def test_cognitive_with_budget_policy(self, harvester, memories) -> None:
        policy = HarvestBudgetPolicy(
            max_candidates=2,
            default_lenses=[_make_lens("pl1", "策略透镜")],
        )
        query = HarvestQuery(
            raw_user_text="Python 项目",
            lenses=[_make_lens("ql1", "查询透镜")],
        )
        brief, cog_trace = harvester.harvest_cognitive(query, memories, policy=policy)
        assert brief is not None
        assert cog_trace is not None
        # max_candidates=2 应限制选中数量
        assert len(cog_trace.selected_memory_ids) <= 2

    def test_cognitive_rules_only_mode(self, harvester, memories) -> None:
        query = HarvestQuery(
            raw_user_text="深色模式",
            lenses=[_make_lens()],
        )
        brief, cog_trace = harvester.harvest_cognitive(
            query, memories, mode=CogHarvestMode.RULES_ONLY,
        )
        assert cog_trace.mode == CogHarvestMode.RULES_ONLY
        assert brief is not None

    def test_cognitive_trace_has_score_breakdown(self, harvester, memories) -> None:
        query = HarvestQuery(
            raw_user_text="界面偏好",
            lenses=[_make_lens()],
        )
        brief, cog_trace = harvester.harvest_cognitive(query, memories)
        assert cog_trace.score_breakdown is not None
        assert "total_candidates" in cog_trace.score_breakdown

    def test_cognitive_empty_memories(self, harvester) -> None:
        query = HarvestQuery(
            raw_user_text="任何查询",
            lenses=[_make_lens()],
        )
        brief, cog_trace = harvester.harvest_cognitive(query, [])
        assert brief is not None
        assert brief.source_memory_ids == []
        assert cog_trace.candidate_memory_ids == []

    def test_semantic_only_empty_recall_does_not_reference_rule_locals(self) -> None:
        query = HarvestQuery(raw_user_text="no semantic candidates", lenses=[_make_lens()])

        brief, cog_trace = run_hybrid_harvest(
            query,
            [],
            mode=CogHarvestMode.SEMANTIC_ONLY,
            emb_provider=FakeEmbeddingProvider(dimensions=64),
        )

        assert brief.source_memory_ids == []
        assert cog_trace.mode == CogHarvestMode.SEMANTIC_ONLY
        assert "no_candidates_found" in cog_trace.warnings

    def test_bad_reranker_output_falls_back_without_invented_ids(self, memories) -> None:
        harvester = GardenHarvester(
            emb_provider=FakeEmbeddingProvider(dimensions=64),
            rank_provider=_BadReranker(),
            cog_writer=FakeBriefWriterProvider(),
        )
        query = HarvestQuery(raw_user_text="深色模式", lenses=[_make_lens()])

        brief, cog_trace = harvester.harvest_cognitive(query, memories)

        assert "invented" not in brief.source_memory_ids
        assert "invented" not in cog_trace.selected_memory_ids
        assert cog_trace.fallback_used is True
        assert cog_trace.fallback_reason == "reranker output failed candidate-pool validation"

    def test_bad_brief_writer_output_falls_back_to_traceable_sources(self, memories) -> None:
        harvester = GardenHarvester(
            emb_provider=FakeEmbeddingProvider(dimensions=64),
            rank_provider=FakeHarvestRerankerProvider(),
            cog_writer=_BadBriefWriter(),
        )
        query = HarvestQuery(raw_user_text="深色模式", lenses=[_make_lens()])

        brief, cog_trace = harvester.harvest_cognitive(query, memories)

        assert "invented" not in brief.source_memory_ids
        assert set(brief.source_memory_ids).issubset(set(cog_trace.selected_memory_ids))
        assert cog_trace.fallback_used is True
        assert cog_trace.fallback_reason == "brief output failed source-memory validation"
