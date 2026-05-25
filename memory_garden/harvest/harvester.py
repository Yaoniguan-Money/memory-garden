"""第三层 Stage 3G：纯内存串联式 GardenHarvester（无 Runtime / 仓库 / 外部模型）。

v1.5.0: 新增 harvest_cognitive() 方法，支持规则+语义融合模式，
通过 cognition.hybrid 委托语义召回与 LLM 增强逻辑。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from memory_garden.cognition.models import HarvestMode as CogHarvestMode, HarvestTrace as CogHarvestTrace

from memory_garden.core.models import MemoryCard
from memory_garden.harvest.brief import HarvestGardenBriefWriter
from memory_garden.harvest.bouquet import GardenBouquetBuilder
from memory_garden.harvest.collector import LocalCandidateCollector
from memory_garden.harvest.models import (
    HarvestGardenBrief,
    HarvestQuery,
    HarvestTrace,
    MemoryLens,
)
from memory_garden.harvest.policy import HarvestBudgetPolicy
from memory_garden.harvest.ranking import RuleBasedHarvestRanker
from memory_garden.harvest.retrieval_diagnostics import attach_retrieval_diagnostics, build_retrieval_diagnostics
from memory_garden.harvest.scoring import RuleBasedHarvestScorer
from memory_garden import runtime_config as _garden_config


def _merge_effective_lenses(
    query: HarvestQuery, policy: HarvestBudgetPolicy | None
) -> list[MemoryLens]:
    """query.lenses 与 policy.default_lenses 拼接，按 lens_id 去重（query 优先）。"""
    if policy is None:
        return list(query.lenses)
    seen: set[str] = set()
    merged: list[MemoryLens] = []
    for lz in [*query.lenses, *policy.default_lenses]:
        lid = lz.lens_id
        if lid in seen:
            continue
        seen.add(lid)
        merged.append(lz)
    return merged


def _resolve_effective_query(
    query: HarvestQuery, policy: HarvestBudgetPolicy | None
) -> tuple[HarvestQuery, dict[str, Any]]:
    """返回流水线实际使用的查询快照；不修改入参 ``query``。"""
    merged = _merge_effective_lenses(query, policy)
    if policy is None:
        return query, {}

    baseline_ids = [lz.lens_id for lz in query.lenses]
    merged_ids = [lz.lens_id for lz in merged]
    if merged_ids == baseline_ids:
        return query, {}

    effective = query.model_copy(update={"lenses": merged})
    meta = {
        "original_query_id": query.query_id,
        "original_lens_ids": list(baseline_ids),
    }
    return effective, meta


class GardenHarvester:
    """将 Stage 3B–3F 组件按固定顺序串为一次可序列化可追溯的采摘快照。

    v1.5.0: 可选注入认知增强组件（emb_provider / rank_provider / cog_writer），
    启用 ``harvest_cognitive()`` 语义+规则融合路径。
    """

    def __init__(
        self,
        collector: LocalCandidateCollector | None = None,
        scorer: RuleBasedHarvestScorer | None = None,
        ranker: RuleBasedHarvestRanker | None = None,
        bouquet_builder: GardenBouquetBuilder | None = None,
        brief_writer: HarvestGardenBriefWriter | None = None,
        *,
        emb_provider: object | None = None,
        rank_provider: object | None = None,
        cog_writer: object | None = None,
        ann_index: object | None = None,
        runtime_config: Any | None = None,
    ) -> None:
        cfg = runtime_config or _garden_config.default_garden_runtime_config()
        self._collector = collector or LocalCandidateCollector(cfg.harvest.collector)
        self._scorer = scorer or RuleBasedHarvestScorer()
        self._ranker = ranker or RuleBasedHarvestRanker()
        self._bouquet_builder = bouquet_builder or GardenBouquetBuilder(cfg.harvest.bouquet)
        self._brief_writer = brief_writer or HarvestGardenBriefWriter()
        self._emb_provider = emb_provider
        self._rank_provider = rank_provider
        self._cog_writer = cog_writer
        self._ann_index = ann_index

    def harvest(
        self,
        query: HarvestQuery,
        memories: list[MemoryCard],
        policy: HarvestBudgetPolicy | None = None,
    ) -> HarvestTrace:
        """纯规则采摘流水线（collect → score → rank → bouquet → brief）。"""
        effective_query, trace_meta_extra = _resolve_effective_query(query, policy)

        candidates = self._collector.collect(effective_query, memories)
        scanned_count = len(memories)
        total_meta = effective_query.metadata.get("total_available")
        total_available = int(total_meta) if total_meta is not None else scanned_count
        fallback_reason = str(effective_query.metadata.get("fallback_reason") or "")
        source = str(effective_query.metadata.get("retrieval_source") or "harvest_rules")
        retrieval_diagnostics = build_retrieval_diagnostics(
            total_available=total_available,
            scanned_count=scanned_count,
            candidate_count=len(candidates),
            source=source,
            fallback_reason=fallback_reason,
        )
        scores = self._scorer.score(effective_query, candidates)
        rank_outcome = self._ranker.rank(effective_query, candidates, scores, policy)
        bouquet = self._bouquet_builder.build(effective_query, rank_outcome, scores, policy)
        brief = self._brief_writer.write(
            effective_query,
            bouquet,
            rank_outcome.ranked_candidates,
            scores,
            policy,
        )
        lenses_trace = list(effective_query.lenses)
        return HarvestTrace(
            query=effective_query,
            lenses=lenses_trace,
            candidates=list(candidates),
            scores=list(scores),
            policy_decisions=[rank_outcome.policy_decision],
            bouquet=bouquet,
            brief=brief,
            model_calls=[],
            metadata=attach_retrieval_diagnostics(dict(trace_meta_extra), retrieval_diagnostics),
            finalized_at=datetime.now(timezone.utc),
        )

    def harvest_cognitive(
        self,
        query: HarvestQuery,
        memories: list[MemoryCard],
        policy: HarvestBudgetPolicy | None = None,
        *,
        mode: CogHarvestMode | None = None,
    ) -> tuple[HarvestGardenBrief, CogHarvestTrace]:
        """规则+语义融合采摘（委托 cognition.hybrid）。

        若语义提供者不完整，自动回退到 rules_only 模式。

        Args:
            query: 采摘查询
            memories: 待检索记忆列表
            policy: 预算策略
            mode: 认知采摘模式（cognition.HarvestMode），默认 HYBRID

        Returns:
            (HarvestGardenBrief, cognition.HarvestTrace) 元组
        """
        from memory_garden.cognition.fallback import resolve_cognitive_mode
        from memory_garden.cognition.hybrid import run_hybrid_harvest
        from memory_garden.cognition.models import HarvestMode as CogMode

        requested_mode = mode if isinstance(mode, CogMode) else CogMode.HYBRID

        effective_mode, fallback_used, fallback_reason = resolve_cognitive_mode(
            requested_mode,
            emb=self._emb_provider,
            rank=self._rank_provider,
            writer=self._cog_writer,
        )

        brief, trace = run_hybrid_harvest(
            query,
            memories,
            policy,
            mode=effective_mode,
            emb_provider=self._emb_provider,
            rank_provider=self._rank_provider,
            cog_brief_writer=self._cog_writer,
            collector=self._collector,
            scorer=self._scorer,
            ranker=self._ranker,
            bouquet_builder=self._bouquet_builder,
            brief_writer=self._brief_writer,
            ann_index=self._ann_index,
        )

        if fallback_used:
            trace.fallback_used = True
            if not trace.fallback_reason:
                trace.fallback_reason = fallback_reason
            trace.warnings.append(fallback_reason)

        return brief, trace
