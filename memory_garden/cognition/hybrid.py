"""认知层混合采摘流水线：规则 + 语义融合，带可追溯审计。

流水线步骤：
1. 规则召回 (collect → score → rank) → top-N 候选
2. 语义召回 (embed → cosine similarity) → top-N 候选
3. 合并去重，保留 rule_score / semantic_score / source_ids
4. 重排序（仅可在候选池内排序，不能新增 memory_id）
5. 选取 top-K
6. 简报撰写
7. 生成 HarvestTrace
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from memory_garden.harvest.ann_index import AnnVectorIndex

from memory_garden.core.models import MemoryCard
from memory_garden.harvest.models import (
    BriefMode,
    HarvestGardenBrief,
    HarvestQuery,
    HarvestScore,
    MemoryCandidate,
)
from memory_garden.harvest.policy import HarvestBudgetPolicy
from memory_garden.cognition.models import (
    GardenBriefDraft,
    HarvestCandidate,
    HarvestMode,
    HarvestTrace,
)
from memory_garden.cognition.validation import (
    generate_trace,
    validate_brief_traceability,
    validate_rerank_candidates,
)

# 规则分数与语义分数的默认融合权重，可通过 HarvestBudgetPolicy 覆盖
_RULE_WEIGHT = 0.5
_SEMANTIC_WEIGHT = 0.5


def _as_vectors(value: Any) -> list[list[float]]:
    vectors = getattr(value, "vectors", value)
    if isinstance(vectors, list):
        return vectors
    # 支持 numpy 数组等可迭代向量容器
    try:
        return [list(v) for v in vectors]
    except (TypeError, ValueError):
        return []


def _mc_to_hc(mc: MemoryCandidate, rule_score: float | None = None) -> HarvestCandidate:
    """将 MemoryCandidate 转换为 HarvestCandidate。"""
    sm = mc.metadata.get("source_memory")
    if isinstance(sm, dict):
        title = str(sm.get("title", "") or "").strip()
        essence = str(sm.get("essence", "") or "").strip()
        text = " - ".join(part for part in (title, essence) if part) or mc.excerpt
        tags = [t for t in (sm.get("tags") or []) if isinstance(t, str)]
    else:
        text = mc.excerpt
        tags = []
    return HarvestCandidate(
        memory_id=mc.memory_id,
        source_ids=[mc.candidate_id],
        text=text,
        tags=tags,
        rule_score=rule_score,
    )


def _memory_to_hc(memory: MemoryCard, semantic_score: float) -> HarvestCandidate:
    """将 MemoryCard 直接转换为 HarvestCandidate（语义召回路径）。"""
    text = " - ".join(part for part in (memory.title.strip(), memory.essence.strip()) if part)
    return HarvestCandidate(
        memory_id=memory.id,
        source_ids=[memory.id],
        text=text or memory.essence or memory.title,
        tags=list(memory.tags) if memory.tags else [],
        semantic_score=round(semantic_score, 6),
        reasons=[f"semantic_recall:cosine={semantic_score:.4f}"],
    )


def _merge_candidates(
    rule_list: list[HarvestCandidate],
    semantic_list: list[HarvestCandidate],
) -> list[HarvestCandidate]:
    """按 memory_id 合并去重，保留最高分和所有 source_ids。

    注意：为避免修改调用者持有的原始对象，合并时对候选进行浅拷贝。
    """
    merged: dict[str, HarvestCandidate] = {}
    for c in rule_list + semantic_list:
        if c.memory_id in merged:
            existing = merged[c.memory_id]
            if c.rule_score is not None:
                if existing.rule_score is None or c.rule_score > existing.rule_score:
                    existing.rule_score = c.rule_score
            if c.semantic_score is not None:
                if existing.semantic_score is None or c.semantic_score > existing.semantic_score:
                    existing.semantic_score = c.semantic_score
            for sid in c.source_ids:
                if sid not in existing.source_ids:
                    existing.source_ids.append(sid)
            for r in c.reasons:
                if r not in existing.reasons:
                    existing.reasons.append(r)
        else:
            merged[c.memory_id] = c
    return list(merged.values())


def _draft_to_harvest_brief(
    draft: GardenBriefDraft,
    mode: BriefMode = BriefMode.HYBRID,
) -> HarvestGardenBrief:
    """将 GardenBriefDraft 桥接为 HarvestGardenBrief。"""
    return HarvestGardenBrief(
        intent=draft.intent,
        use=draft.use,
        avoid=draft.avoid,
        style=draft.style,
        safety=draft.safety,
        nudge=draft.nudge,
        source_memory_ids=list(draft.source_memory_ids),
        token_estimate=draft.token_estimate,
        mode=mode,
    )


def _score_breakdown(candidates: list[HarvestCandidate]) -> dict[str, Any]:
    """构建评分分解 dict。"""
    return {
        "total_candidates": len(candidates),
        "scores": [
            {
                "memory_id": c.memory_id,
                "rule_score": c.rule_score,
                "semantic_score": c.semantic_score,
                "rerank_score": c.rerank_score,
            }
            for c in candidates
        ],
    }


def _score_sort(candidates: list[HarvestCandidate]) -> list[HarvestCandidate]:
    def _sort_key(c: HarvestCandidate) -> float:
        rule = c.rule_score or 0.0
        semantic = c.semantic_score or 0.0
        return _RULE_WEIGHT * rule + _SEMANTIC_WEIGHT * semantic

    return sorted(candidates, key=_sort_key, reverse=True)


@dataclass
class HybridHarvestRequest:
    """混合采摘流水线入参（分组以降低 ``run_hybrid_harvest`` 参数面）。"""

    query: HarvestQuery
    memories: list[MemoryCard]
    policy: HarvestBudgetPolicy | None = None
    mode: HarvestMode = HarvestMode.RULES_ONLY
    emb_provider: Any = None
    rank_provider: Any = None
    cog_brief_writer: Any = None
    collector: Any = None
    scorer: Any = None
    ranker: Any = None
    bouquet_builder: Any = None
    brief_writer: Any = None
    ann_index: AnnVectorIndex | None = None
    rule_weight: float = _RULE_WEIGHT
    semantic_weight: float = _SEMANTIC_WEIGHT
    warnings: list[str] = field(default_factory=list)


def run_hybrid_harvest(
    query: HarvestQuery,
    memories: list[MemoryCard],
    policy: HarvestBudgetPolicy | None = None,
    *,
    mode: HarvestMode = HarvestMode.RULES_ONLY,
    emb_provider: Any = None,
    rank_provider: Any = None,
    cog_brief_writer: Any = None,
    collector: Any = None,
    scorer: Any = None,
    ranker: Any = None,
    bouquet_builder: Any = None,
    brief_writer: Any = None,
    ann_index: AnnVectorIndex | None = None,
) -> tuple[HarvestGardenBrief, HarvestTrace]:
    """运行混合采摘流水线（兼容旧签名；内部委托 ``HybridHarvestRequest``）。"""
    request = HybridHarvestRequest(
        query=query,
        memories=memories,
        policy=policy,
        mode=mode,
        emb_provider=emb_provider,
        rank_provider=rank_provider,
        cog_brief_writer=cog_brief_writer,
        collector=collector,
        scorer=scorer,
        ranker=ranker,
        bouquet_builder=bouquet_builder,
        brief_writer=brief_writer,
        ann_index=ann_index,
    )
    return run_hybrid_harvest_request(request)


def run_hybrid_harvest_request(request: HybridHarvestRequest) -> tuple[HarvestGardenBrief, HarvestTrace]:
    """运行混合采摘流水线。"""
    from memory_garden.harvest.local_embedding import cosine_similarity

    query = request.query
    memories = request.memories
    policy = request.policy
    mode = request.mode
    emb_provider = request.emb_provider
    rank_provider = request.rank_provider
    cog_brief_writer = request.cog_brief_writer
    collector = request.collector
    scorer = request.scorer
    ranker = request.ranker
    bouquet_builder = request.bouquet_builder
    brief_writer = request.brief_writer
    ann_index = request.ann_index

    query_text = query.raw_user_text
    max_cap = policy.max_candidates if policy is not None else 16
    rule_candidates: list[HarvestCandidate] = []
    semantic_candidates: list[HarvestCandidate] = []
    warnings: list[str] = []
    fallback_used = False
    fallback_reason: str | None = None
    provider_name: str | None = None
    prompt_version: str | None = None
    raw_candidates: list[MemoryCandidate] = []
    raw_scores: list[HarvestScore] = []
    ranked: list[MemoryCandidate] = []
    rank_outcome = None

    # ---- Step 1: 规则召回 ----
    if mode in (HarvestMode.RULES_ONLY, HarvestMode.HYBRID):
        raw_candidates = collector.collect(query, memories) if collector else []
        raw_scores = scorer.score(query, raw_candidates) if scorer else []
        rank_outcome = ranker.rank(query, raw_candidates, raw_scores, policy) if ranker else None

        score_by_id: dict[str, HarvestScore] = {}
        for s in (raw_scores or []):
            score_by_id[s.candidate_id] = s

        ranked = rank_outcome.ranked_candidates if rank_outcome else raw_candidates
        for mc in ranked:
            sc = score_by_id.get(mc.candidate_id)
            rule_candidates.append(_mc_to_hc(mc, sc.relevance if sc else None))

    # ---- Step 2: 语义召回 ----
    if mode in (HarvestMode.SEMANTIC_ONLY, HarvestMode.HYBRID) and emb_provider is not None:
        try:
            mem_texts = [(m, m.essence or m.title) for m in memories]
            if mem_texts:
                memory_by_id = {m.id: m for m in memories}
                if ann_index is not None and ann_index.size > 0:
                    query_vectors = _as_vectors(emb_provider.embed_texts([query_text]))
                    if not query_vectors:
                        raise ValueError("embedding provider 未返回查询向量")
                    query_vec = query_vectors[0]
                    for mid, sim in ann_index.search(query_vec, k=max_cap):
                        if sim <= 0.0:
                            continue
                        memory = memory_by_id.get(mid)
                        if memory is not None:
                            semantic_candidates.append(_memory_to_hc(memory, sim))
                else:
                    texts_to_embed = [query_text] + [t for _, t in mem_texts]
                    vectors = _as_vectors(emb_provider.embed_texts(texts_to_embed))
                    if len(vectors) != len(texts_to_embed):
                        raise ValueError("embedding provider 返回的向量数量与输入文本数量不一致")
                    query_vec = vectors[0]
                    memory_vecs = vectors[1:]

                    scored: list[tuple[float, MemoryCard]] = []
                    for (memory, _), vec in zip(mem_texts, memory_vecs):
                        sim = cosine_similarity(query_vec, vec)
                        if sim > 0.0:
                            scored.append((sim, memory))

                    scored.sort(key=lambda x: -x[0])
                    for sim, memory in scored[:max_cap]:
                        semantic_candidates.append(_memory_to_hc(memory, sim))
        except Exception as exc:
            warnings.append(f"semantic_recall_failed: {exc}")

    # ---- Step 3: 合并去重 ----
    merged = _merge_candidates(rule_candidates, semantic_candidates)

    if not merged:
        # 无候选时回退到规则流水线输出
        fallback_used = True
        fallback_reason = fallback_reason or "no_candidates_after_merge"
        bouquet = bouquet_builder.build(query, rank_outcome, raw_scores, policy) if bouquet_builder and rank_outcome else None
        fallback_brief = brief_writer.write(query, bouquet, ranked, raw_scores, policy) if brief_writer and bouquet else _empty_brief()
        trace = generate_trace(
            query=query_text,
            mode=mode,
            candidate_pool=[],
            selected=[],
            score_breakdown={},
            fallback_used=fallback_used,
            fallback_reason=fallback_reason,
            warnings=warnings + ["no_candidates_found"],
        )
        return fallback_brief, trace

    # ---- Step 4: 重排序 ----
    original_candidate_pool = list(merged)
    candidate_pool = _score_sort(original_candidate_pool)
    if rank_provider is not None:
        try:
            rerank_result = rank_provider.rerank(query_text, original_candidate_pool, policy)
            rerank_issues = validate_rerank_candidates(
                rerank_result.candidates,
                original_candidate_pool,
            )
            if rerank_issues:
                warnings.extend(rerank_issues)
                fallback_used = True
                fallback_reason = "reranker output failed candidate-pool validation"
                candidate_pool = _score_sort(original_candidate_pool)
            else:
                candidate_pool = rerank_result.candidates
            provider_name = rerank_result.provider_name
            prompt_version = rerank_result.prompt_version
        except Exception as exc:
            warnings.append(f"rerank_failed: {exc}")
            fallback_used = True
            fallback_reason = f"reranker exception: {exc}"
            candidate_pool = _score_sort(original_candidate_pool)
    else:
        # 无重排序 Provider 时按已有分数排序
        candidate_pool = _score_sort(candidate_pool)
        if mode != HarvestMode.RULES_ONLY:
            fallback_used = True
            fallback_reason = "no_reranker_provider:using_score_fallback"
            warnings.append(fallback_reason)

    # ---- Step 5: 选取 top-K ----
    selected = candidate_pool[:max_cap]

    # ---- Step 6: 简报撰写 ----
    if cog_brief_writer is not None and mode != HarvestMode.RULES_ONLY:
        try:
            draft = cog_brief_writer.write_brief(query_text, selected, policy)
        except Exception as exc:
            warnings.append(f"brief_write_failed: {exc}")
            draft = _fallback_draft(query_text, selected)
            fallback_used = True
            fallback_reason = f"brief_writer exception: {exc}"
    else:
        draft = _fallback_draft(query_text, selected)

    brief_issues = validate_brief_traceability(draft, selected)
    if brief_issues:
        warnings.extend(brief_issues)
        fallback_used = True
        fallback_reason = "brief output failed source-memory validation"
        draft = _fallback_draft(query_text, selected)

    brief_mode = BriefMode.TEMPLATE if mode == HarvestMode.RULES_ONLY else BriefMode.HYBRID
    harvest_brief = _draft_to_harvest_brief(draft, mode=brief_mode)

    # ---- Step 7: 生成 Trace ----
    score_bd = _score_breakdown(candidate_pool)
    trace = generate_trace(
        query=query_text,
        mode=mode,
        candidate_pool=candidate_pool,
        selected=selected,
        score_breakdown=score_bd,
        provider_name=provider_name,
        prompt_version=prompt_version,
        fallback_used=fallback_used,
        fallback_reason=fallback_reason,
        warnings=warnings,
    )

    return harvest_brief, trace


def _empty_brief() -> HarvestGardenBrief:
    """返回安全的空简报。"""
    return HarvestGardenBrief(
        intent="空查询或无匹配记忆。",
        use="无相关记忆可参考。",
        avoid="无。",
        style="中性。",
        safety="保守。",
        nudge="跳过。",
        source_memory_ids=[],
        token_estimate=8,
        mode=BriefMode.TEMPLATE,
    )


def _fallback_draft(query: str, selected: list[HarvestCandidate]) -> GardenBriefDraft:
    """模板化后备简报草稿。"""
    q_clip = (query or "").strip()[:100] or "（空查询）"
    source_ids = [c.memory_id for c in selected[:16]]
    if source_ids:
        use_text = f"参考记忆：{'、'.join(source_ids[:48])}。请以标识为线索核对上下文。"
    else:
        use_text = "当前无可参考的候选记忆。"
    return GardenBriefDraft(
        intent=f"模板简报：用户表达围绕「{q_clip}」",
        use=use_text,
        avoid="不将候选记忆视为确定事实。",
        style="中性简短。",
        safety="保守，不断言。",
        nudge="请将简报仅作编排线索。",
        source_memory_ids=source_ids,
        token_estimate=max(8, len(use_text) // 4 + 20),
    )
