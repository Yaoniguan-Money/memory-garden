"""Stag 2: Dream Reflective Clustering — 规则分组 + 可选语义反思。

流水线步骤：
1. 将 MemoryCard 转换为 DreamMemoryInput
2. 若 provider 就绪且 mode=REFLECTIVE，调用 propose_clusters
3. 校验 proposal 的 source_memory_ids 可追溯性
4. 校验必填字段和 confidence 范围
5. 非法 proposal 跳过后 fallback
6. 生成 DreamTrace

DreamProposal 是派生记录，不修改原始 memory。
"""

from __future__ import annotations

import uuid

from memory_garden.core.models import MemoryCard
from memory_garden.cognition.models import (
    DreamMemoryInput,
    DreamMode,
    DreamProposal,
    DreamProposalBatch,
    DreamRelationType,
    DreamSuggestedAction,
    DreamTrace,
)
from memory_garden.cognition.providers import DreamWeaverProvider
from memory_garden.cognition.validation import generate_dream_trace, validate_dream_batch


def _memory_to_dream_input(memory: MemoryCard) -> DreamMemoryInput:
    """将 MemoryCard 转换为 DreamMemoryInput。"""
    return DreamMemoryInput(
        memory_id=memory.id,
        text=memory.essence or memory.title,
        tags=list(memory.tags) if memory.tags else [],
        source_seed_ids=list(getattr(memory, "source_seed_ids", []) or []),
        created_at=str(getattr(memory, "created_at", "")) or None,
    )


def _empty_batch() -> DreamProposalBatch:
    return DreamProposalBatch(proposals=[], provider_name="none", prompt_version=None)


def _default_proposals(memories: list[DreamMemoryInput]) -> list[DreamProposal]:
    """模板化后备：按标签分组生成基本聚类 proposal。"""
    tag_groups: dict[str, list[DreamMemoryInput]] = {}
    for m in memories:
        for t in (m.tags or []):
            tag_groups.setdefault(t, []).append(m)

    proposals: list[DreamProposal] = []
    seq = 0
    for tag, group in tag_groups.items():
        if len(group) < 2:
            continue
        seq += 1
        source_ids = [m.memory_id for m in group]
        proposals.append(DreamProposal(
            proposal_id=f"dream-prop-default-{seq:04d}",
            title=f"标签聚类：{tag}",
            summary=f"规则聚类发现 {len(group)} 条记忆共享标签「{tag}」：{'、'.join(source_ids[:8])}。",
            source_memory_ids=source_ids,
            relation_type=DreamRelationType.SAME_THEME,
            suggested_action=DreamSuggestedAction.RECORD_REFLECTION,
            confidence=0.65,
            reason=f"规则聚类：标签「{tag}」在 {len(group)} 条记忆中重复出现。",
        ))
    return proposals


def run_reflective_dream(
    memories: list[MemoryCard],
    *,
    mode: DreamMode = DreamMode.RULES_ONLY,
    weaver_provider: DreamWeaverProvider | None = None,
    dream_run_id: str | None = None,
) -> tuple[DreamProposalBatch, DreamTrace]:
    """运行反思梦境周期。

    Args:
        memories: 参与反思的记忆卡列表
        mode: RULES_ONLY 或 REFLECTIVE
        weaver_provider: 可选 DreamWeaverProvider
        dream_run_id: 梦境运行 ID，未提供则自动生成

    Returns:
        (DreamProposalBatch, DreamTrace) 元组
    """
    run_id = dream_run_id or str(uuid.uuid4())
    warnings: list[str] = []
    fallback_used = False
    fallback_reason: str | None = None

    inputs = [_memory_to_dream_input(m) for m in memories]

    if not inputs:
        batch = _empty_batch()
        trace = generate_dream_trace(
            dream_run_id=run_id,
            mode=mode,
            input_memory_ids=[],
            batch=batch,
            fallback_used=False,
        )
        return batch, trace

    # ── RULES_ONLY: 直接使用模板聚类 ───────────────────────────────
    if mode == DreamMode.RULES_ONLY or weaver_provider is None:
        if mode == DreamMode.REFLECTIVE and weaver_provider is None:
            fallback_used = True
            fallback_reason = "weaver_provider not configured, falling back to rules_only"

        proposals = _default_proposals(inputs)
        batch = DreamProposalBatch(
            proposals=proposals,
            provider_name="rules_only",
            prompt_version=None,
        )
        trace = generate_dream_trace(
            dream_run_id=run_id,
            mode=DreamMode.RULES_ONLY,
            input_memory_ids=[m.memory_id for m in inputs],
            batch=batch,
            fallback_used=fallback_used,
            fallback_reason=fallback_reason,
            warnings=warnings,
        )
        return batch, trace

    # ── REFLECTIVE: 调用 weaver provider ───────────────────────────
    try:
        batch = weaver_provider.propose_clusters(inputs)
    except Exception as exc:
        warnings.append(f"weaver_provider failed: {exc}")
        proposals = _default_proposals(inputs)
        batch = DreamProposalBatch(
            proposals=proposals,
            provider_name="rules_only",
            prompt_version=None,
            warnings=warnings,
        )
        trace = generate_dream_trace(
            dream_run_id=run_id,
            mode=DreamMode.RULES_ONLY,
            input_memory_ids=[m.memory_id for m in inputs],
            batch=batch,
            fallback_used=True,
            fallback_reason=f"weaver_provider exception: {exc}",
            warnings=warnings,
        )
        return batch, trace

    # ── 校验 ───────────────────────────────────────────────────────
    issues = validate_dream_batch(batch, inputs)
    if issues or not batch.proposals:
        if not batch.proposals:
            issues.append("DreamProposalBatch: empty provider output")
        warnings.extend(issues)
        proposals = _default_proposals(inputs)
        batch = DreamProposalBatch(
            proposals=proposals,
            provider_name="rules_only",
            prompt_version=None,
            warnings=warnings,
        )
        fallback_used = True
        fallback_reason = "weaver_provider output failed validation"
    else:
        batch.warnings = warnings

    trace = generate_dream_trace(
        dream_run_id=run_id,
        mode=DreamMode.RULES_ONLY if fallback_used else mode,
        input_memory_ids=[m.memory_id for m in inputs],
        batch=batch,
        fallback_used=fallback_used,
        fallback_reason=fallback_reason,
        warnings=warnings,
    )
    return batch, trace
