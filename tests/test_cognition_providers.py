"""第四层：Cognition 提供者与校验单元测试。"""

import pytest

from memory_garden.cognition.fake_providers import (
    FakeBriefWriterProvider,
    FakeHarvestRerankerProvider,
)
from memory_garden.providers import FakeEmbeddingProvider
from memory_garden.cognition.brief_llm import LLMBriefWriter
from memory_garden.cognition.models import HarvestCandidate
from memory_garden.cognition.providers import (
    BriefWriterProvider,
    EmbeddingProvider,
    HarvestRerankerProvider,
)
from memory_garden.cognition.validation import (
    generate_trace,
    validate_brief_traceability,
    validate_rerank_candidates,
)
from memory_garden.cognition.fallback import FallbackChecker, safe_call
from memory_garden.cognition.models import GardenBriefDraft, HarvestMode
from memory_garden.providers import TextCompletionResult
from memory_garden.providers.errors import ProviderPolicyError


# ── FakeEmbeddingProvider ──────────────────────────────────────────


class TestFakeEmbeddingProvider:
    def test_deterministic_output(self) -> None:
        p = FakeEmbeddingProvider(dimensions=64)
        a = p.embed_texts(["hello world"])
        b = p.embed_texts(["hello world"])
        assert len(a) == 1
        assert len(a[0]) == 64
        assert a[0] == b[0]

    def test_different_texts_produce_different_vectors(self) -> None:
        p = FakeEmbeddingProvider(dimensions=64)
        a = p.embed_texts(["hello"])[0]
        b = p.embed_texts(["world"])[0]
        assert a != b

    def test_empty_text_produces_zero_vector(self) -> None:
        p = FakeEmbeddingProvider(dimensions=32)
        v = p.embed_texts([""])[0]
        assert v == [0.0] * 32

    def test_satisfies_protocol(self) -> None:
        p = FakeEmbeddingProvider()
        assert isinstance(p, EmbeddingProvider)


# ── FakeHarvestRerankerProvider ────────────────────────────────────


class TestFakeHarvestRerankerProvider:
    def test_preserves_candidate_count(self) -> None:
        p = FakeHarvestRerankerProvider()
        candidates = [
            HarvestCandidate(memory_id="a", source_ids=["a"], text="first", rule_score=0.3, semantic_score=0.7),
            HarvestCandidate(memory_id="b", source_ids=["b"], text="second", rule_score=0.9, semantic_score=0.1),
        ]
        result = p.rerank("query", candidates)
        assert len(result.candidates) == 2

    def test_assigns_rerank_scores(self) -> None:
        p = FakeHarvestRerankerProvider()
        candidates = [
            HarvestCandidate(memory_id="a", source_ids=["a"], text="", rule_score=0.5, semantic_score=0.5),
        ]
        result = p.rerank("q", candidates)
        assert result.candidates[0].rerank_score is not None
        assert 0.0 <= result.candidates[0].rerank_score <= 1.0  # type: ignore[operator]

    def test_sorts_by_rerank_score_descending(self) -> None:
        p = FakeHarvestRerankerProvider()
        candidates = [
            HarvestCandidate(memory_id="low", source_ids=["low"], text="z", rule_score=0.1, semantic_score=0.1),
            HarvestCandidate(memory_id="high", source_ids=["high"], text="a", rule_score=0.9, semantic_score=0.9),
        ]
        result = p.rerank("query", candidates)
        assert result.candidates[0].memory_id == "high"
        assert result.candidates[1].memory_id == "low"

    def test_no_new_memory_ids(self) -> None:
        p = FakeHarvestRerankerProvider()
        candidates = [
            HarvestCandidate(memory_id="m1", source_ids=["m1"], text="x"),
            HarvestCandidate(memory_id="m2", source_ids=["m2"], text="y"),
        ]
        result = p.rerank("q", candidates)
        output_ids = {c.memory_id for c in result.candidates}
        assert output_ids == {"m1", "m2"}

    def test_empty_candidates(self) -> None:
        p = FakeHarvestRerankerProvider()
        result = p.rerank("q", [])
        assert result.candidates == []

    def test_satisfies_protocol(self) -> None:
        p = FakeHarvestRerankerProvider()
        assert isinstance(p, HarvestRerankerProvider)


# ── FakeBriefWriterProvider ───────────────────────────────────────


class TestFakeBriefWriterProvider:
    def test_includes_source_memory_ids(self) -> None:
        p = FakeBriefWriterProvider()
        candidates = [
            HarvestCandidate(memory_id="m1", source_ids=["m1"], text="a"),
            HarvestCandidate(memory_id="m2", source_ids=["m2"], text="b"),
        ]
        draft = p.write_brief("query", candidates)
        assert len(draft.source_memory_ids) == 2
        assert "m1" in draft.source_memory_ids
        assert "m2" in draft.source_memory_ids

    def test_all_fields_non_empty(self) -> None:
        p = FakeBriefWriterProvider()
        draft = p.write_brief("test query", [
            HarvestCandidate(memory_id="m1", source_ids=["m1"], text="content"),
        ])
        assert draft.intent
        assert draft.use
        assert draft.avoid
        assert draft.style
        assert draft.safety
        assert draft.nudge

    def test_handles_empty_candidates(self) -> None:
        p = FakeBriefWriterProvider()
        draft = p.write_brief("query", [])
        assert draft.source_memory_ids == []

    def test_satisfies_protocol(self) -> None:
        p = FakeBriefWriterProvider()
        assert isinstance(p, BriefWriterProvider)


# ── Validation ────────────────────────────────────────────────────


class _SummaryLLM:
    name = "summary-llm"
    is_remote = False

    def __init__(self) -> None:
        self.user_prompt = ""

    def complete_text(self, *, system, user, context):
        self.user_prompt = user
        return TextCompletionResult(
            text="用户偏好简短的中文回复，技术术语保留英文。",
            model=self.name,
        )


class _RemoteSummaryLLM(_SummaryLLM):
    is_remote = True


class TestLLMBriefWriter:
    def test_writes_natural_language_use_with_source_ids(self) -> None:
        llm = _SummaryLLM()
        writer = LLMBriefWriter(llm)
        candidates = [
            HarvestCandidate(
                memory_id="m1",
                source_ids=["m1"],
                text="回复偏好 - 用户偏好简短的中文回复，技术术语保留英文。",
            ),
        ]

        draft = writer.write_brief("如何回复用户？", candidates)

        assert draft.use == "用户偏好简短的中文回复，技术术语保留英文。"
        assert draft.source_memory_ids == ["m1"]
        assert "m1" in llm.user_prompt
        assert "UUID" not in draft.use

    def test_satisfies_protocol(self) -> None:
        assert isinstance(LLMBriefWriter(_SummaryLLM()), BriefWriterProvider)

    def test_llm_brief_writer_blocks_remote_provider_without_policy(self) -> None:
        writer = LLMBriefWriter(_RemoteSummaryLLM())
        candidates = [HarvestCandidate(memory_id="m1", source_ids=["m1"], text="content")]

        with pytest.raises(ProviderPolicyError):
            writer.write_brief("query", candidates)


class TestValidateRerankCandidates:
    def test_no_new_ids_passes(self) -> None:
        pool = [
            HarvestCandidate(memory_id="a", source_ids=["a"], text="x"),
            HarvestCandidate(memory_id="b", source_ids=["b"], text="y"),
        ]
        reranked = list(pool)
        issues = validate_rerank_candidates(reranked, pool)
        assert issues == []

    def test_extra_id_fails(self) -> None:
        pool = [HarvestCandidate(memory_id="a", source_ids=["a"], text="x")]
        reranked = [
            HarvestCandidate(memory_id="a", source_ids=["a"], text="x"),
            HarvestCandidate(memory_id="b", source_ids=["b"], text="y"),
        ]
        issues = validate_rerank_candidates(reranked, pool)
        assert len(issues) >= 1
        assert any("b" in i for i in issues)

    def test_more_output_than_input_fails(self) -> None:
        pool = [HarvestCandidate(memory_id="a", source_ids=["a"], text="x")]
        reranked = [
            HarvestCandidate(memory_id="a", source_ids=["a"], text="x"),
            HarvestCandidate(memory_id="a", source_ids=["a"], text="x"),
        ]
        issues = validate_rerank_candidates(reranked, pool)
        assert len(issues) >= 1


class TestValidateBriefTraceability:
    def test_all_ids_in_pool_passes(self) -> None:
        pool = [
            HarvestCandidate(memory_id="m1", source_ids=["m1"], text="a"),
            HarvestCandidate(memory_id="m2", source_ids=["m2"], text="b"),
        ]
        draft = GardenBriefDraft(
            intent="i", use="u", avoid="a", style="s", safety="sf", nudge="n",
            source_memory_ids=["m1", "m2"],
        )
        issues = validate_brief_traceability(draft, pool)
        assert issues == []

    def test_missing_id_fails(self) -> None:
        pool = [HarvestCandidate(memory_id="m1", source_ids=["m1"], text="a")]
        draft = GardenBriefDraft(
            intent="i", use="u", avoid="a", style="s", safety="sf", nudge="n",
            source_memory_ids=["m1", "m_unknown"],
        )
        issues = validate_brief_traceability(draft, pool)
        assert len(issues) >= 1
        assert any("m_unknown" in i for i in issues)

    def test_empty_source_ids_fails(self) -> None:
        pool = [HarvestCandidate(memory_id="m1", source_ids=["m1"], text="a")]
        draft = GardenBriefDraft(
            intent="i", use="u", avoid="a", style="s", safety="sf", nudge="n",
            source_memory_ids=[],
        )
        issues = validate_brief_traceability(draft, pool)
        assert len(issues) >= 1


class TestGenerateTrace:
    def test_produces_trace(self) -> None:
        pool = [
            HarvestCandidate(memory_id="a", source_ids=["a"], text="x"),
            HarvestCandidate(memory_id="b", source_ids=["b"], text="y"),
            HarvestCandidate(memory_id="c", source_ids=["c"], text="z"),
        ]
        selected = [pool[0], pool[1]]
        trace = generate_trace(
            query="test query",
            mode=HarvestMode.HYBRID,
            candidate_pool=pool,
            selected=selected,
            score_breakdown={"rule": 0.9},
            provider_name="fake",
            fallback_used=False,
        )
        assert trace.mode == HarvestMode.HYBRID
        assert trace.selected_memory_ids == ["a", "b"]
        assert trace.rejected_memory_ids == ["c"]
        assert trace.fallback_used is False

    def test_fallback_trace(self) -> None:
        trace = generate_trace(
            query="q",
            mode=HarvestMode.RULES_ONLY,
            candidate_pool=[],
            selected=[],
            score_breakdown={},
            fallback_used=True,
            warnings=["no providers configured"],
        )
        assert trace.fallback_used is True


# ── FallbackChecker ───────────────────────────────────────────────


class TestFallbackChecker:
    def test_all_providers_none_triggers_fallback(self) -> None:
        checker = FallbackChecker()
        mode, used, reason = checker.resolve_mode(HarvestMode.HYBRID)
        assert mode == HarvestMode.RULES_ONLY
        assert used is True
        assert "embedding_provider" in reason

    def test_all_providers_present_no_fallback(self) -> None:
        checker = FallbackChecker(
            embedding_provider=FakeEmbeddingProvider(),
            reranker_provider=FakeHarvestRerankerProvider(),
            brief_writer_provider=FakeBriefWriterProvider(),
        )
        mode, used, reason = checker.resolve_mode(HarvestMode.HYBRID)
        assert mode == HarvestMode.HYBRID
        assert used is False
        assert reason == ""

    def test_rules_only_never_falls_back(self) -> None:
        checker = FallbackChecker()
        mode, used, reason = checker.resolve_mode(HarvestMode.RULES_ONLY)
        assert mode == HarvestMode.RULES_ONLY
        assert used is False

    def test_can_run_semantic_missing_providers(self) -> None:
        checker = FallbackChecker(embedding_provider=FakeEmbeddingProvider())
        ok, reason = checker.can_run_semantic()
        assert ok is True
        assert reason == ""

    def test_can_run_semantic_all_present(self) -> None:
        checker = FallbackChecker(
            embedding_provider=FakeEmbeddingProvider(),
            reranker_provider=FakeHarvestRerankerProvider(),
            brief_writer_provider=FakeBriefWriterProvider(),
        )
        ok, reason = checker.can_run_semantic()
        assert ok is True


class TestSafeCall:
    def test_successful_call(self) -> None:
        result, ok, err = safe_call(lambda x: x * 2, 21)
        assert ok is True
        assert err == ""
        assert result == 42

    def test_failing_call(self) -> None:
        def raiser():
            raise ValueError("boom")
        result, ok, err = safe_call(raiser, default_result=None)
        assert ok is False
        assert "ValueError" in err
        assert result is None
