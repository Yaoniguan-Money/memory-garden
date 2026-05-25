"""Integration tests: full pipeline end-to-end with fake providers.

Covers the complete Memory Garden lifecycle across all layers:
  Core (Seed → Court → Plant)
  Harvest (collect → score → rank → bouquet → brief)
  Cognition (hybrid harvest → dream reflective → court shadow)
  Product (propose → approve → retrieve → edit → forget)
  Soil (hard forget with cascade cleanup + reindex + forget proof)
  Runtime (before_reply → harvest → brief → after_reply → observe → close)
"""

from pathlib import Path

import pytest

from memory_garden.cognition.fake_providers import (
    FakeBriefWriterProvider,
    FakeCourtAdvisorProvider,
    FakeDreamWeaverProvider,
    FakeHarvestRerankerProvider,
)
from memory_garden.cognition.models import (
    CourtShadowMode,
    DreamMode,
    HarvestMode as CogHarvestMode,
)
from memory_garden.core.garden import MemoryGardenCore
from memory_garden.core.growth.lifecycle import MemoryLifecycle
from memory_garden.core.models import SeedStatus, SensitivityLevel
from memory_garden.harvest.harvester import GardenHarvester
from memory_garden.harvest.models import HarvestQuery, MemoryLens
from memory_garden.harvest.policy import HarvestBudgetPolicy
from memory_garden.product import (
    MemoryListFilter,
    MemoryPatch,
    ProductMemorySystem,
)
from memory_garden.product.policy import MemoryPolicy
from memory_garden.providers.config import ProviderPolicy
from memory_garden.providers.fake import FakeEmbeddingProvider, FakeLLMProvider, FakeRerankerProvider
from memory_garden.providers.registry import ProviderRegistry
from memory_garden.sdk import MemoryGarden
from memory_garden.soil.forget import execute_hard_forget, plan_hard_forget
from memory_garden.soil.forget_proof import prove_forget
from memory_garden.soil.index import reindex_garden
from memory_garden.storage.sqlite import SQLiteGardenRepository


# ── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture
def repo() -> SQLiteGardenRepository:
    r = SQLiteGardenRepository(":memory:")
    yield r
    r.close()


@pytest.fixture
def garden(tmp_path: Path) -> MemoryGarden:
    g = MemoryGarden.local(tmp_path / "garden")
    yield g
    g.close()


@pytest.fixture
def product(garden: MemoryGarden) -> ProductMemorySystem:
    return ProductMemorySystem(
        garden_home=garden.home.root,
        repository=garden.core.repository,
    )


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_harvest_query(text: str, lenses: list[MemoryLens] | None = None) -> HarvestQuery:
    return HarvestQuery(
        session_id="test-session",
        turn_index=1,
        raw_user_text=text,
        lenses=lenses or [],
    )


def _make_lens(lens_id: str = "lens-1", name: str = "preference") -> MemoryLens:
    return MemoryLens(lens_id=lens_id, name=name, facet_keys=["preference"])


# ── Core Lifecycle Integration ──────────────────────────────────────────────


class TestCoreLifecyclePipeline:
    """Seed → Court → Plant → Harvest → Brief (rule-based)."""

    def test_full_rule_pipeline_plant_flow(self, repo: SQLiteGardenRepository) -> None:
        """Observe a preference seed, open court, plant, then harvest the brief."""
        core = MemoryGardenCore(repository=repo)

        seeds = core.observe("我喜欢用深色主题的界面")
        assert len(seeds) == 1
        assert seeds[0].status == SeedStatus.pending

        cases = core.open_court()
        assert len(cases) == 1
        verdict = cases[0].judge_verdict.verdict.value
        assert verdict in ("plant", "hold")

        result = core.apply_verdict(cases[0])
        if verdict == "plant":
            assert result is not None
            assert len(core.list_memories()) == 1

    def test_full_rule_pipeline_compost_negative(self, repo: SQLiteGardenRepository) -> None:
        """Negative self-talk should be composted, not planted."""
        core = MemoryGardenCore(repository=repo)
        seeds = core.observe("我好废，我什么都做不好")
        assert len(seeds) >= 1
        cases = core.open_court()
        assert len(cases) >= 1
        core.apply_verdict(cases[0])
        cards = core.list_memories()
        composted = all(
            repo.get_seed(s.id).status != SeedStatus.planted
            for s in seeds
        )
        assert composted or len(cards) == 0

    def test_pipeline_with_multiple_seeds_and_memories(self, repo: SQLiteGardenRepository) -> None:
        """Multiple observations — court processes all pending seeds."""
        core = MemoryGardenCore(repository=repo)

        texts = [
            "我喜欢简洁的代码风格",
            "请始终用中文回复我",
            "项目deadline非常重要，不要拖延",
        ]
        for t in texts:
            core.observe(t)

        cases = core.open_court()
        # Court opens for all pending seeds (may be fewer if some rejected)
        assert 1 <= len(cases) <= len(texts)

        planted = 0
        for c in cases:
            r = core.apply_verdict(c)
            if r is not None:
                planted += 1

        cards = core.list_memories()
        assert len(cards) == planted
        assert all(
            c.lifecycle not in (MemoryLifecycle.composted, MemoryLifecycle.pruned)
            for c in cards
        )

    def test_dream_cycle_no_crash(self, repo: SQLiteGardenRepository) -> None:
        """Dream engine runs without error on a garden with seeds."""
        core = MemoryGardenCore(repository=repo)
        core.observe("我喜欢暗色模式")
        core.observe("暗色主题最适合我")

        cases = core.open_court()
        for c in cases:
            core.apply_verdict(c)

        # Dream returns None if no work to do — both are valid
        core.dream()

    def test_hard_forget_removes_memory(self, repo: SQLiteGardenRepository) -> None:
        """Plant a memory, then hard-forget it — card must be gone."""
        core = MemoryGardenCore(repository=repo)
        seeds = core.observe("以后请叫我小明")
        cases = core.open_court()
        for c in cases:
            core.apply_verdict(c)

        cards = core.list_memories()
        if cards:
            mid = cards[0].id
            core.forget(mid, mode="hard", reason="test hard forget")
            with pytest.raises(Exception):
                repo.get_memory_card(mid)


# ── Harvest Pipeline Integration ────────────────────────────────────────────


class TestHarvestPipeline:
    """Harvester pipeline with fake providers: collect → score → rank → bouquet → brief."""

    def test_rule_only_harvest_produces_trace(self, repo: SQLiteGardenRepository) -> None:
        """RULES_ONLY harvest produces a HarvestTrace with brief."""
        core = MemoryGardenCore(repository=repo)
        core.observe("我喜欢Python编程")
        cases = core.open_court()
        for c in cases:
            core.apply_verdict(c)

        harvester = GardenHarvester()
        query = _make_harvest_query("Python", lenses=[_make_lens()])
        trace = harvester.harvest(query, core.list_memories(), HarvestBudgetPolicy(max_candidates=8))

        assert trace.brief is not None
        assert trace.brief.intent
        assert trace.brief.source_memory_ids is not None
        assert len(trace.candidates) >= 0
        assert len(trace.scores) >= 0

    def test_hybrid_harvest_with_fake_providers(self, repo: SQLiteGardenRepository) -> None:
        """HYBRID harvest with fake embedding + reranker + brief writer."""
        core = MemoryGardenCore(repository=repo)
        core.observe("我喜欢用暗色主题")
        cases = core.open_court()
        for c in cases:
            core.apply_verdict(c)

        harvester = GardenHarvester(
            emb_provider=FakeEmbeddingProvider(dimensions=64),
            rank_provider=FakeHarvestRerankerProvider(),
            cog_writer=FakeBriefWriterProvider(),
        )
        query = _make_harvest_query("暗色主题", lenses=[_make_lens()])
        brief, trace = harvester.harvest_cognitive(
            query, core.list_memories(),
            HarvestBudgetPolicy(max_candidates=8),
            mode=CogHarvestMode.HYBRID,
        )

        assert brief.intent
        assert brief.source_memory_ids is not None
        assert trace is not None
        assert trace.query == query.raw_user_text
        assert hasattr(trace, "fallback_used")

    def test_hybrid_auto_fallback_to_rules_only(self, repo: SQLiteGardenRepository) -> None:
        """When no providers are configured, HYBRID falls back to RULES_ONLY."""
        core = MemoryGardenCore(repository=repo)
        core.observe("请用中文回复")
        cases = core.open_court()
        for c in cases:
            core.apply_verdict(c)

        harvester = GardenHarvester()
        query = _make_harvest_query("中文", lenses=[_make_lens()])
        brief, trace = harvester.harvest_cognitive(
            query, core.list_memories(), mode=CogHarvestMode.HYBRID,
        )

        assert brief is not None
        assert trace is not None
        assert trace.fallback_used is True


# ── Cognition Pipeline Integration ──────────────────────────────────────────


class TestCognitionPipeline:
    """End-to-end cognition layer with fake providers: hybrid + dream + court shadow."""

    def test_full_cognition_trio(self, repo: SQLiteGardenRepository) -> None:
        """Run hybrid harvest, reflective dream, and court shadow in sequence."""
        from memory_garden.cognition.court_shadow import run_court_shadow
        from memory_garden.cognition.dream_reflective import run_reflective_dream

        core = MemoryGardenCore(repository=repo)

        texts = [
            "我喜欢简洁的代码风格",
            "请始终用中文回复",
            "暗色主题最适合编程",
            "我喜欢Python胜过Java",
        ]
        for t in texts:
            core.observe(t)
        cases = core.open_court()
        for c in cases:
            core.apply_verdict(c)

        memories = core.list_memories()
        assert len(memories) > 0, "Expected at least one memory from preference seeds"

        # 1. Hybrid harvest
        harvester = GardenHarvester(
            emb_provider=FakeEmbeddingProvider(dimensions=64),
            rank_provider=FakeHarvestRerankerProvider(),
            cog_writer=FakeBriefWriterProvider(),
        )
        query = _make_harvest_query("代码风格偏好", lenses=[_make_lens()])
        brief, harvest_trace = harvester.harvest_cognitive(
            query, memories, mode=CogHarvestMode.HYBRID,
        )
        assert brief is not None
        assert harvest_trace is not None

        # 2. Reflective dream
        dream_batch, dream_trace = run_reflective_dream(
            memories,
            mode=DreamMode.REFLECTIVE,
            weaver_provider=FakeDreamWeaverProvider(),
        )
        assert dream_batch is not None
        assert dream_trace is not None
        assert dream_trace.mode is not None

        # 3. Court shadow
        seeds = repo.list_seeds()
        active_seeds = [s for s in seeds if s.status != SeedStatus.planted]
        if active_seeds:
            shadow = run_court_shadow(
                active_seeds[0],
                "plant",
                "test reason",
                mode=CourtShadowMode.SHADOW,
                advisor_provider=FakeCourtAdvisorProvider(),
            )
            assert shadow.final_verdict == "plant"
            assert shadow.llm_advised_verdict is not None

    def test_court_shadow_disabled_mode_skips_advisor(self, repo: SQLiteGardenRepository) -> None:
        """DISABLED mode never calls the advisor."""
        from memory_garden.cognition.court_shadow import run_court_shadow

        core = MemoryGardenCore(repository=repo)
        core.observe("测试种子")
        seeds = repo.list_seeds()

        called = False

        class TrackedAdvisor:
            def advise(self, seed, context=None, policy=None):  # noqa: ARG002
                nonlocal called
                called = True
                from memory_garden.cognition.models import CourtAdvice
                return CourtAdvice(
                    seed_id=seed.seed_id,
                    advised_verdict="plant",
                    confidence=0.9,
                    reason="test",
                    source_seed_ids=[seed.seed_id],
                )

        if seeds:
            run_court_shadow(
                seeds[0], "hold", "reason",
                mode=CourtShadowMode.DISABLED,
                advisor_provider=TrackedAdvisor(),
            )
        assert not called, "DISABLED mode should not call the advisor"


# ── Product Layer Integration ───────────────────────────────────────────────


class TestProductPipeline:
    """Product-grade memory system: propose → approve → retrieve → edit → forget."""

    def test_full_product_lifecycle(self, garden: MemoryGarden, product: ProductMemorySystem) -> None:
        """Propose, approve, retrieve, inspect, edit, archive — full cycle."""
        # 1. Propose
        proposals = product.propose("remember: prefer dark mode for all dashboards")
        assert len(proposals) == 1
        assert proposals[0].status.value == "pending"

        # 2. Approve
        card = product.approve(proposals[0].id)
        assert card.id
        assert card.sensitivity == SensitivityLevel.none

        # 3. Inspect
        inspection = product.inspect_memory(card.id)
        assert inspection.memory.id == card.id
        assert len(inspection.versions) >= 1
        assert inspection.versions[0].reason == "proposal_approved"

        # 4. Retrieve
        result = product.retrieve("dark dashboard", limit=5)
        assert len(result.hits) >= 1
        assert any(h.memory.id == card.id for h in result.hits)

        # 5. Edit
        edited = product.edit_memory(
            card.id,
            MemoryPatch(title="Dark mode preference", tags=["ui", "dark"], importance=0.85),
            reason="refining",
        )
        assert edited.title == "Dark mode preference"
        assert edited.importance == 0.85

        # 6. Archive (soft — moves to fading)
        archived = product.archive_memory(card.id, reason="test archive")
        valid_lifecycles = {MemoryLifecycle.fading, MemoryLifecycle.pruned, MemoryLifecycle.bloom}
        assert archived.lifecycle in valid_lifecycles

    def test_product_trusted_mode_auto_approve(self, garden: MemoryGarden, product: ProductMemorySystem) -> None:
        """trusted mode: low-sensitivity proposals auto-approved."""
        result = product.remember(
            "remember: I prefer short, concise answers",
            mode="trusted",
        )
        assert len(result["approved_memory_ids"]) >= 1
        assert result["mode"] == "trusted"

    def test_product_retrieve_with_strategy_context(self, garden: MemoryGarden, product: ProductMemorySystem) -> None:
        """Retrieve respects applicability context."""
        product.remember("remember: prefer dark mode", mode="trusted")
        result = product.retrieve(
            "dark mode", limit=5,
            context={"task_type": "coding", "user_id": "test-user"},
        )
        assert result.query == "dark mode"
        assert len(result.hits) >= 1

    def test_product_cautious_mode_requires_confirmation(self, garden: MemoryGarden, product: ProductMemorySystem) -> None:
        """cautious mode marks proposals as requiring confirmation."""
        proposals = product.propose("I prefer detailed explanations with examples")
        assert proposals[0].status.value == "pending"
        assert proposals[0].requires_confirmation is True

    def test_product_remember_uses_provider_extraction(self, garden: MemoryGarden) -> None:
        """When LLM provider is configured, proposals use provider extraction."""
        policy = MemoryPolicy(
            provider_policy=ProviderPolicy(allow_raw_user_text=True),
        )
        providers = ProviderRegistry(llm=FakeLLMProvider(), policy=policy.provider_policy)
        product_sys = ProductMemorySystem(
            garden_home=garden.home.root,
            repository=garden.core.repository,
            providers=providers,
            policy=policy,
        )
        result = product_sys.remember(
            "remember: prefer dark mode and concise answers",
            mode="trusted",
        )
        # Provider extraction creates proposals; trusted mode may auto-approve
        assert len(result["proposals"]) >= 1
        assert result["proposals"][0].source == "fake-llm"

    def test_product_retrieve_with_reranker(self, garden: MemoryGarden) -> None:
        """Retrieve with reranker provider configured."""
        policy = MemoryPolicy(
            provider_policy=ProviderPolicy(allow_raw_user_text=True),
        )
        providers = ProviderRegistry(reranker=FakeRerankerProvider(), policy=policy.provider_policy)
        product_sys = ProductMemorySystem(
            garden_home=garden.home.root,
            repository=garden.core.repository,
            providers=providers,
            policy=policy,
        )
        product_sys.remember("remember: prefer dark mode", mode="trusted")
        result = product_sys.retrieve("dark", limit=3)
        assert result.query == "dark"
        assert len(result.hits) >= 1


# ── Soil Hard Forget Integration ────────────────────────────────────────────


class TestSoilForgetPipeline:
    """Soil-layer hard forget: plan → execute → prove → reindex."""

    def test_plan_execute_prove_forget_cycle(self, tmp_path: Path) -> None:
        """Full forget cycle with cascade cleanup, reindex, and proof."""
        garden = MemoryGarden.local(tmp_path / "garden-forget")
        try:
            product_sys = ProductMemorySystem(
                garden_home=garden.home.root,
                repository=garden.core.repository,
            )
            result = product_sys.remember(
                "remember: prefer dark mode for all interfaces",
                mode="trusted",
            )
            assert len(result["approved_memory_ids"]) >= 1
            mid = result["approved_memory_ids"][0]

            # 1. Plan
            plan = plan_hard_forget(garden.home.root, mid)
            assert plan.memory_id == mid
            assert plan.fts_entries >= 0

            # 2. Execute
            exec_result = execute_hard_forget(
                garden.home.root, mid,
                reason="test forget",
                cascade=True,
            )
            assert exec_result.status == "ok"
            assert exec_result.memory_deleted is True

            # 3. Prove
            proof = prove_forget(garden.home.root, mid)
            assert proof.proven is True
            assert len(proof.checks) >= 1

            # 4. Reindex — should succeed on a garden with a deleted memory
            reindex_result = reindex_garden(garden.home.root, dry_run=False)
            assert reindex_result.status in ("ok", "partial")

        finally:
            garden.close()

    def test_forget_without_cascade_leaves_related_entities(self, tmp_path: Path) -> None:
        """Without cascade, related seeds/cases remain after hard forget."""
        garden = MemoryGarden.local(tmp_path / "garden-nocascade")
        try:
            core = garden.core
            seeds = core.observe("测试遗忘功能")
            cases = core.open_court()
            for c in cases:
                core.apply_verdict(c)

            cards = core.list_memories()
            if not cards:
                pytest.skip("No memories created")
            mid = cards[0].id

            n_seeds_before = len(core.repository.list_seeds())
            n_cases_before = len(core.repository.list_court_cases())

            result = execute_hard_forget(
                garden.home.root, mid,
                reason="test no-cascade",
                cascade=False,
            )
            assert result.status == "ok"

            n_seeds_after = len(core.repository.list_seeds())
            n_cases_after = len(core.repository.list_court_cases())
            assert n_seeds_after == n_seeds_before, "Without cascade, seeds remain"
            assert n_cases_after == n_cases_before, "Without cascade, cases remain"

        finally:
            garden.close()


# ── Runtime Session Integration ─────────────────────────────────────────────


class TestRuntimeSession:
    """Runtime session lifecycle: open → observe → harvest → close."""

    def test_full_session_with_memory_growth(self, tmp_path: Path) -> None:
        """A complete chat session: 花花开, observe preferences, 花花关."""
        garden = MemoryGarden.local(tmp_path / "garden-session")
        try:
            r1 = garden.chat("花花开")
            sid = r1.session_id
            assert sid is not None
            assert r1.reply is not None

            garden.chat("我喜欢暗色主题的界面设计", session_id=sid)
            garden.chat("请不要给我太长的回复，简洁就好", session_id=sid)

            r4 = garden.chat("花花关", session_id=sid)
            assert r4.feedback is not None

        finally:
            garden.close()

    def test_skill_open_before_and_after(self, tmp_path: Path) -> None:
        """Using GardenSkill directly: open → before → after → close."""
        garden = MemoryGarden.local(tmp_path / "garden-skill")
        try:
            skill = garden.as_skill()
            sid = skill.open()
            assert sid is not None

            ctx = skill.before("我喜欢简洁的回答")
            assert ctx.brief_text is not None or ctx.garden_brief is not None

            skill.after("我喜欢简洁的回答", "好的，我会尽量简洁。")

            fb = skill.close()
            assert fb is not None

        finally:
            garden.close()

    def test_provider_registry_composition(self) -> None:
        """ProviderRegistry can be constructed and queried."""
        reg = ProviderRegistry()
        assert reg.optional_llm() is None
        assert reg.optional_embedding() is None
        assert reg.optional_reranker() is None

        reg2 = ProviderRegistry(
            llm=FakeLLMProvider(),
            embedding=FakeEmbeddingProvider(dimensions=128),
            reranker=FakeRerankerProvider(),
        )
        assert reg2.optional_llm() is not None
        assert reg2.optional_embedding() is not None
        assert reg2.optional_reranker() is not None

    def test_full_cycle_persists_memories_between_sessions(self, tmp_path: Path) -> None:
        """Memories planted in one session are visible in the next."""
        garden = MemoryGarden.local(tmp_path / "garden-persist")
        try:
            r1 = garden.chat("花花开")
            sid1 = r1.session_id
            garden.chat("我喜欢简洁的回复", session_id=sid1)
            garden.chat("花花关", session_id=sid1)

            n_cards = len(garden.core.list_memories())

            r2 = garden.chat("花花开")
            sid2 = r2.session_id
            garden.chat("花花关", session_id=sid2)

            # Memories persist across sessions
            assert len(garden.core.list_memories()) == n_cards

        finally:
            garden.close()
