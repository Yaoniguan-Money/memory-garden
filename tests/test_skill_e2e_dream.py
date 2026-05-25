from memory_garden.core.models import MemoryCard
from memory_garden.cognition.dream_reflective import run_reflective_dream
from memory_garden.cognition.fake_providers import FakeDreamWeaverProvider
from memory_garden.cognition.models import (
    DreamMode,
    DreamProposal,
    DreamProposalBatch,
    DreamRelationType,
    DreamSuggestedAction,
)
from memory_garden.sdk import MemoryGarden


def test_skill_e2e_dream_proposal_keeps_sources_and_does_not_mutate(tmp_path) -> None:
    garden = MemoryGarden.local(tmp_path / "garden")
    try:
        m1 = MemoryCard(title="深色模式", essence="用户喜欢深色模式", fragrance="f", thorns="t", tags=["ui"])
        m2 = MemoryCard(title="字体偏好", essence="用户喜欢大字体", fragrance="f", thorns="t", tags=["ui"])
        garden.core.repository.save_memory_card(m1)
        garden.core.repository.save_memory_card(m2)

        before = garden.core.repository.get_memory_card(m1.id)
        batch, trace = run_reflective_dream(
            garden.core.list_memories(include_greenhouse=True),
            mode=DreamMode.REFLECTIVE,
            weaver_provider=FakeDreamWeaverProvider(),
        )
        after = garden.core.repository.get_memory_card(m1.id)

        assert trace.fallback_used is False
        assert batch.proposals
        assert all(p.source_memory_ids for p in batch.proposals)
        assert before.model_dump() == after.model_dump()
    finally:
        garden.close()


def test_skill_e2e_dream_bad_provider_falls_back(tmp_path) -> None:
    class _BadWeaver:
        def propose_clusters(self, memories, policy=None):
            return DreamProposalBatch(
                proposals=[
                    DreamProposal(
                        proposal_id="bad",
                        title="bad",
                        summary="bad",
                        source_memory_ids=["outside"],
                        relation_type=DreamRelationType.SAME_THEME,
                        suggested_action=DreamSuggestedAction.SUGGEST_MERGE,
                        confidence=0.9,
                        reason="bad",
                    )
                ],
                provider_name="bad",
            )

    garden = MemoryGarden.local(tmp_path / "garden")
    try:
        m1 = MemoryCard(title="A", essence="A", fragrance="f", thorns="t", tags=["shared"])
        m2 = MemoryCard(title="B", essence="B", fragrance="f", thorns="t", tags=["shared"])
        garden.core.repository.save_memory_card(m1)
        garden.core.repository.save_memory_card(m2)

        batch, trace = run_reflective_dream(
            garden.core.list_memories(include_greenhouse=True),
            mode=DreamMode.REFLECTIVE,
            weaver_provider=_BadWeaver(),
        )

        assert trace.fallback_used is True
        assert trace.mode == DreamMode.RULES_ONLY
        assert all("outside" not in p.source_memory_ids for p in batch.proposals)
    finally:
        garden.close()
