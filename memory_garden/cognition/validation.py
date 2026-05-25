"""认知层 LLM 输出可追溯性校验。

确保所有经由 LLM 产出的内容满足：
1. 所有 memory_id 引用可追溯至输入候选池
2. 简报条目均绑定 memory_id
3. 不可凭空生成不在候选池中的 memory_id
4. 不可追溯内容须标记为 "inference" 或删除
"""

from __future__ import annotations

from memory_garden.cognition.models import (
    CourtAdvice,
    CourtSeedInput,
    DreamMemoryInput,
    DreamMode,
    DreamProposal,
    DreamProposalBatch,
    DreamTrace,
    GardenBriefDraft,
    HarvestCandidate,
    HarvestMode,
    HarvestTrace,
)


def validate_rerank_candidates(
    reranked: list[HarvestCandidate],
    candidate_pool: list[HarvestCandidate],
) -> list[str]:
    """校验重排序结果未引入新的 memory_id。

    Returns:
        问题列表，空列表表示通过。
    """
    issues: list[str] = []
    pool_ids = {c.memory_id for c in candidate_pool}
    output_ids = [c.memory_id for c in reranked]

    for c in reranked:
        if c.memory_id not in pool_ids:
            issues.append(
                f"Rerank candidate memory_id '{c.memory_id}' not in candidate pool"
            )

    input_count = len(candidate_pool)
    output_count = len(reranked)
    if output_count > input_count:
        issues.append(
            f"Rerank output candidate count ({output_count}) exceeds input ({input_count})"
        )
    if len(output_ids) != len(set(output_ids)):
        issues.append("Rerank output contains duplicate memory_id values")
    missing_ids = pool_ids - set(output_ids)
    if missing_ids:
        issues.append(
            f"Rerank output missing candidate memory_id values: {sorted(missing_ids)}"
        )

    return issues


def validate_brief_traceability(
    draft: GardenBriefDraft,
    candidate_pool: list[HarvestCandidate],
) -> list[str]:
    """校验简报所有 source_memory_ids 来自候选池。

    Returns:
        问题列表，空列表表示通过。
    """
    issues: list[str] = []
    pool_ids = {c.memory_id for c in candidate_pool}

    if not draft.source_memory_ids:
        issues.append("Brief has empty source_memory_ids")
        return issues

    for mid in draft.source_memory_ids:
        if mid not in pool_ids:
            issues.append(
                f"Brief source_memory_id '{mid}' not in candidate pool"
            )

    return issues


def flag_untraceable_content(
    draft: GardenBriefDraft,
    candidate_pool: list[HarvestCandidate],
) -> list[str]:
    """标记简报中不可追溯的内容。

    检查每项简报字段是否引用了不在候选池中的 memory_id。

    Returns:
        警告列表，空列表表示全部可追溯。
    """
    warnings: list[str] = validate_brief_traceability(draft, candidate_pool)
    return warnings


def generate_trace(
    query: str,
    mode: HarvestMode,
    candidate_pool: list[HarvestCandidate],
    selected: list[HarvestCandidate],
    score_breakdown: dict,
    *,
    provider_name: str | None = None,
    prompt_version: str | None = None,
    fallback_used: bool = False,
    fallback_reason: str | None = None,
    warnings: list[str] | None = None,
) -> HarvestTrace:
    """生成认知流水线的 HarvestTrace。

    Args:
        query: 查询文本
        mode: 采摘模式
        candidate_pool: 全部候选
        selected: 入选候选
        score_breakdown: 评分分解
        provider_name: 提供方名称
        prompt_version: 提示版本
        fallback_used: 是否使用了回退
        warnings: 警告列表

    Returns:
        填充完整的 HarvestTrace。
    """
    pool_ids = [c.memory_id for c in candidate_pool]
    selected_ids = [c.memory_id for c in selected]
    selected_set = set(selected_ids)
    rejected_ids = [mid for mid in pool_ids if mid not in selected_set]

    all_warnings: list[str] = list(warnings or [])
    pool_set = set(pool_ids)
    for selected_id in selected_ids:
        if selected_id not in pool_set:
            all_warnings.append(
                f"Selected memory_id '{selected_id}' not in candidate pool"
            )

    return HarvestTrace(
        query=query,
        mode=mode,
        candidate_memory_ids=pool_ids,
        selected_memory_ids=selected_ids,
        rejected_memory_ids=rejected_ids,
        score_breakdown=score_breakdown,
        provider_name=provider_name,
        prompt_version=prompt_version,
        fallback_used=fallback_used,
        fallback_reason=fallback_reason,
        warnings=all_warnings,
    )


# ── Stage 2: Dream Proposal 校验 ────────────────────────────────────


def validate_dream_proposal(
    proposal: DreamProposal,
    input_memory_ids: set[str],
) -> list[str]:
    """校验单个 DreamProposal 的可追溯性和字段完整性。

    Returns:
        问题列表，空列表表示通过。
    """
    issues: list[str] = []

    # source_memory_ids 不能为空
    if not proposal.source_memory_ids:
        issues.append(f"DreamProposal {proposal.proposal_id}: empty source_memory_ids")

    # source_memory_ids 必须全部来自输入集合
    for mid in proposal.source_memory_ids:
        if mid not in input_memory_ids:
            issues.append(
                f"DreamProposal {proposal.proposal_id}: source_memory_id '{mid}' "
                f"not in input memories"
            )

    # 必填字段不能为空
    if not proposal.title.strip():
        issues.append(f"DreamProposal {proposal.proposal_id}: empty title")
    if not proposal.summary.strip():
        issues.append(f"DreamProposal {proposal.proposal_id}: empty summary")
    if not proposal.reason.strip():
        issues.append(f"DreamProposal {proposal.proposal_id}: empty reason")

    # confidence 范围校验
    if not (0.0 <= proposal.confidence <= 1.0):
        issues.append(
            f"DreamProposal {proposal.proposal_id}: confidence {proposal.confidence} "
            f"out of [0.0, 1.0]"
        )

    return issues


def validate_dream_batch(
    batch: DreamProposalBatch,
    input_memories: list[DreamMemoryInput],
) -> list[str]:
    """校验整批 DreamProposal。"""
    issues: list[str] = []
    input_ids = {m.memory_id for m in input_memories}

    for proposal in batch.proposals:
        issues.extend(validate_dream_proposal(proposal, input_ids))

    return issues


def generate_dream_trace(
    dream_run_id: str,
    mode: DreamMode,
    input_memory_ids: list[str],
    batch: DreamProposalBatch,
    *,
    fallback_used: bool = False,
    fallback_reason: str | None = None,
    warnings: list[str] | None = None,
) -> DreamTrace:
    """生成梦境反思的 DreamTrace。"""
    all_warnings: list[str] = list(warnings or [])

    return DreamTrace(
        dream_run_id=dream_run_id,
        mode=mode,
        input_memory_ids=list(input_memory_ids),
        proposal_ids=[p.proposal_id for p in batch.proposals],
        provider_name=batch.provider_name,
        prompt_version=batch.prompt_version,
        fallback_used=fallback_used,
        fallback_reason=fallback_reason,
        warnings=all_warnings,
    )


# ── Stage 3: Court Advice 校验 ──────────────────────────────────────

_VALID_VERDICTS = {
    "plant", "hold", "forget", "compost", "greenhouse", "prune", "merge",
}


def validate_court_advice(
    advice: CourtAdvice,
    seed: CourtSeedInput,
    context: dict | None = None,
) -> list[str]:
    """校验 CourtAdvice 的可追溯性与字段完整性。

    Returns:
        问题列表，空列表表示通过。
    """
    issues: list[str] = []

    if advice.seed_id != seed.seed_id:
        issues.append(
            f"CourtAdvice seed_id '{advice.seed_id}' does not match seed '{seed.seed_id}'"
        )

    # advised_verdict 必须是合法判决类型
    if advice.advised_verdict not in _VALID_VERDICTS:
        issues.append(
            f"CourtAdvice for {advice.seed_id}: invalid advised_verdict "
            f"'{advice.advised_verdict}'"
        )

    # seed_id 必须在 source_seed_ids 中
    if seed.seed_id not in advice.source_seed_ids:
        issues.append(
            f"CourtAdvice for {advice.seed_id}: seed_id missing from source_seed_ids"
        )

    # reason 不能为空
    if not advice.reason.strip():
        issues.append(f"CourtAdvice for {advice.seed_id}: empty reason")

    return issues


def resolve_disagreement_type(rule_verdict: str, llm_verdict: str | None) -> str | None:
    """区分规则判决与 LLM 建议之间的分歧类型。"""
    if llm_verdict is None:
        return None
    if rule_verdict == llm_verdict:
        return "same_verdict"

    pair = (rule_verdict, llm_verdict)
    mapping = {
        ("plant", "hold"): "rule_plant_llm_hold",
        ("hold", "plant"): "rule_hold_llm_plant",
        ("forget", "plant"): "rule_forget_llm_plant",
        ("compost", "merge"): "rule_compost_llm_merge",
        ("greenhouse", "plant"): "rule_protect_llm_other",
        ("greenhouse", "hold"): "rule_protect_llm_other",
    }
    return mapping.get(pair, "other")
