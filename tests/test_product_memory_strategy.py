from datetime import timedelta

from memory_garden.product import (
    ApplicabilityContext,
    MemoryMaturityStage,
    ProductMemorySystem,
    utc_now,
)
from memory_garden.sdk import MemoryGarden


def _product(tmp_path):
    garden = MemoryGarden.local(tmp_path / "garden")
    return garden, ProductMemorySystem(garden_home=garden.home.root, repository=garden.core.repository)


def test_strategy_profile_layers_scope_and_filters(tmp_path):
    garden, product = _product(tmp_path)
    try:
        result = product.remember(
            "remember: for project atlas prefer detailed release notes",
            mode="trusted",
            metadata={"project_id": "atlas", "task_type": "writing"},
        )
        memory_id = result["approved_memory_ids"][0]

        profile = product.get_strategy_profile(memory_id)
        assert profile.layer.value == "preference"
        assert profile.scope.value == "project"
        assert profile.scope_id == "atlas"
        assert profile.maturity == MemoryMaturityStage.observed

        filtered = product.list_memories()
        assert filtered[0].layer == "preference"
        assert filtered[0].scope == "project"
        assert filtered[0].scope_id == "atlas"
    finally:
        garden.close()


def test_applicability_blocks_wrong_project_and_allows_matching_scope(tmp_path):
    garden, product = _product(tmp_path)
    try:
        memory_id = product.remember(
            "remember: for project atlas prefer detailed release notes",
            mode="trusted",
            metadata={"project_id": "atlas"},
        )["approved_memory_ids"][0]

        allowed = product.assess_applicability(
            memory_id,
            "release notes",
            context=ApplicabilityContext(project_id="atlas", task_type="writing"),
        )
        blocked = product.assess_applicability(
            memory_id,
            "release notes",
            context=ApplicabilityContext(project_id="zephyr", task_type="writing"),
        )

        assert allowed.allowed is True
        assert allowed.score > blocked.score
        assert blocked.allowed is False
        assert "scope_project_mismatch" in blocked.risk_flags
        assert product.retrieve("release notes", context={"project_id": "zephyr"}).hits == []
    finally:
        garden.close()


def test_retrieval_reinforces_and_promotes_memory_strategy(tmp_path):
    garden, product = _product(tmp_path)
    try:
        memory_id = product.remember("remember: prefer compact release notes", mode="trusted")["approved_memory_ids"][0]
        profile = product.get_strategy_profile(memory_id)
        product.store.save_strategy_profile(
            profile.model_copy(update={"evidence_count": 2, "mention_count": 2, "strength": 0.72})
        )

        result = product.retrieve("compact release notes")
        assert result.hits[0].memory.id == memory_id

        promoted = product.get_strategy_profile(memory_id)
        assert promoted.use_count == 1
        assert promoted.maturity in (MemoryMaturityStage.stable, MemoryMaturityStage.canonical)
        assert product.store.list_evolution_plans(memory_id)
    finally:
        garden.close()


def test_conflict_arbitration_prefers_explicit_correction(tmp_path):
    garden, product = _product(tmp_path)
    try:
        first = product.remember("remember: prefer concise and short updates", mode="trusted")["approved_memory_ids"][0]
        proposal = product.propose("correction: actually prefer detailed and long updates instead")[0]
        second = product.approve(proposal.id)

        arbitrations = product.store.list_conflict_arbitrations(first)
        assert arbitrations
        assert arbitrations[0].winner_memory_id == second.id
        assert arbitrations[0].resolution == "new_user_correction_supersedes_existing"
        assert product.get_strategy_profile(first).contradiction_count >= 1
    finally:
        garden.close()


def test_decay_and_abstraction_plans_are_auditable(tmp_path):
    garden, product = _product(tmp_path)
    try:
        memory_ids = [
            product.remember(f"remember: prefer release note style {idx}", mode="trusted")["approved_memory_ids"][0]
            for idx in range(3)
        ]
        for memory_id in memory_ids:
            profile = product.get_strategy_profile(memory_id)
            product.store.save_strategy_profile(
                profile.model_copy(
                    update={
                        "maturity": MemoryMaturityStage.stable,
                        "strength": 0.8,
                        "last_reinforced_at": utc_now() - timedelta(days=120),
                    }
                )
            )

        decay_plans = product.decay_memories()
        abstraction_plans = product.plan_abstractions()

        assert decay_plans
        assert all(plan.status == "executed" for plan in decay_plans)
        assert abstraction_plans
        assert abstraction_plans[0].action.value == "abstract"
        assert set(abstraction_plans[0].related_memory_ids) == set(memory_ids)
    finally:
        garden.close()
