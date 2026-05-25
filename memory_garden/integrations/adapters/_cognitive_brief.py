"""Shared cognitive brief helpers for framework adapters."""

from __future__ import annotations

from typing import Any


def resolve_provider_registry(garden: Any, providers: Any | None = None) -> Any | None:
    """Return an explicit or garden-level provider registry."""

    if providers is not None:
        return providers
    getter = getattr(garden, "_get_skill_product_providers", None)
    if callable(getter):
        registry = getter()
        if registry is not None:
            return registry
    return None


def build_cognitive_skill_context(
    *,
    garden: Any,
    skill: Any,
    providers: Any | None,
    user_message: str,
    metadata: dict[str, Any] | None = None,
    messages: list[dict[str, Any]] | None = None,
    max_candidates: int = 5,
) -> Any | None:
    """Build a SkillContext with an LLM-written harvest brief when possible."""

    llm = getattr(providers, "llm", None)
    if llm is None:
        return None
    try:
        from memory_garden.cognition.brief_llm import LLMBriefWriter
        from memory_garden.cognition.hybrid import run_hybrid_harvest
        from memory_garden.cognition.models import HarvestMode as CogHarvestMode
        from memory_garden.harvest.brief import HarvestGardenBriefWriter
        from memory_garden.harvest.bouquet import GardenBouquetBuilder
        from memory_garden.harvest.collector import LocalCandidateCollector
        from memory_garden.harvest.models import HarvestQuery
        from memory_garden.harvest.policy import HarvestBudgetPolicy
        from memory_garden.harvest.ranking import RuleBasedHarvestRanker
        from memory_garden.harvest.scoring import RuleBasedHarvestScorer
        from memory_garden.providers import cognition_from_product_registry
        from memory_garden.skill import SkillContext

        provider_kwargs = cognition_from_product_registry(
            providers,
            garden_home=str(garden.home.root),
        )
        query = HarvestQuery(
            raw_user_text=user_message,
            session_id=skill.session_id,
            metadata=dict(metadata or {}),
        )
        memories = garden.core.list_memories(include_greenhouse=False, limit=500)
        brief, trace = run_hybrid_harvest(
            query,
            memories,
            HarvestBudgetPolicy(max_candidates=max_candidates),
            mode=CogHarvestMode.HYBRID,
            emb_provider=provider_kwargs.get("emb_provider"),
            rank_provider=provider_kwargs.get("rank_provider"),
            cog_brief_writer=LLMBriefWriter(
                llm,
                policy=getattr(providers, "policy", None),
                garden_home=str(garden.home.root),
            ),
            collector=LocalCandidateCollector(),
            scorer=RuleBasedHarvestScorer(),
            ranker=RuleBasedHarvestRanker(),
            bouquet_builder=GardenBouquetBuilder(),
            brief_writer=HarvestGardenBriefWriter(),
        )
        brief_dict = brief.model_dump(mode="json")
        parts = []
        for slot in ("use", "avoid", "style", "safety", "nudge"):
            value = brief_dict.get(slot, "")
            if value and str(value).strip():
                parts.append(f"[{slot}] {value}")
        ctx = SkillContext(
            session_id=skill.session_id or "",
            brief_text="\n".join(parts),
            brief_dict=brief_dict,
            metadata={"cognitive_trace": trace.model_dump(mode="json")},
        )
        if messages is not None:
            ctx.messages = ctx.inject_into_messages(messages)
        return ctx
    except Exception:
        return None


__all__ = ["build_cognitive_skill_context", "resolve_provider_registry"]
