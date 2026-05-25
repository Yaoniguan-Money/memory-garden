"""认知层确定性伪提供者 — 用于测试，不发起真实 LLM 调用。"""

from __future__ import annotations

import hashlib
import math
from typing import Any

from memory_garden.cognition.models import (
    CourtAdvice,
    CourtSeedInput,
    DreamMemoryInput,
    DreamProposal,
    DreamProposalBatch,
    DreamRelationType,
    DreamSuggestedAction,
    GardenBriefDraft,
    HarvestCandidate,
    HarvestRerankResult,
)
from memory_garden.providers.fake import FakeEmbeddingProvider as _CanonicalFakeEmbeddingProvider


def _embed_one(text: str, dimensions: int) -> list[float]:
    """单文本确定性向量（字符 n-gram hash + L2 归一化）。"""
    if not text or not text.strip():
        return [0.0] * dimensions

    padded = "  " + text.lower().strip() + "  "
    ngrams_3 = [padded[i : i + 3] for i in range(len(padded) - 2)]
    ngrams_4 = [padded[i : i + 4] for i in range(len(padded) - 3)]

    buckets = [0.0] * dimensions
    for ng in ngrams_3:
        h = int(hashlib.md5(ng.encode()).hexdigest(), 16)
        buckets[h % dimensions] += 0.6
    for ng in ngrams_4:
        h = int(hashlib.md5(ng.encode()).hexdigest(), 16)
        buckets[h % dimensions] += 0.4

    norm = math.sqrt(sum(v * v for v in buckets))
    if norm > 0:
        return [v / norm for v in buckets]
    return buckets


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """两个等长向量的余弦相似度。"""
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class FakeEmbeddingProvider(_CanonicalFakeEmbeddingProvider):
    """确定性字符 n-gram hash 向量提供者 —— 已废弃，请直接用 ``memory_garden.providers.FakeEmbeddingProvider``。

    .. deprecated::
        本类只是 ``memory_garden.providers.fake.FakeEmbeddingProvider`` 的无操作子类。
        新代码应直接从 ``memory_garden.providers`` 导入。
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        import warnings

        warnings.warn(
            "cognition.FakeEmbeddingProvider 已废弃，请改用 memory_garden.providers.FakeEmbeddingProvider",
            DeprecationWarning,
            stacklevel=2,
        )
        super().__init__(*args, **kwargs)


class FakeHarvestRerankerProvider:
    """确定性重排序：组合 rule_score 和 semantic_score 后排序。

    仅在给定候选池内操作，不新增 memory_id。
    """

    def rerank(
        self,
        query: str,
        candidates: list[HarvestCandidate],
        policy: Any | None = None,
    ) -> HarvestRerankResult:
        for c in candidates:
            rule = c.rule_score or 0.0
            semantic = c.semantic_score or 0.0
            # 若查询文本与候选文本有子串重叠，给予小幅加权
            q_lower = query.strip().casefold()
            t_lower = c.text.strip().casefold()
            text_boost = 0.1 if q_lower and t_lower and (q_lower in t_lower or t_lower in q_lower) else 0.0
            c.rerank_score = round(0.5 * rule + 0.5 * semantic + text_boost, 6)

        sorted_candidates = sorted(candidates, key=lambda c: c.rerank_score or 0.0, reverse=True)
        return HarvestRerankResult(
            candidates=sorted_candidates,
            provider_name="fake_harvest_reranker",
            prompt_version="deterministic_v1",
        )


class FakeBriefWriterProvider:
    """确定性简报撰写：基于入选候选拼装模板文本。

    始终携带 ``source_memory_ids``，所有引用均来自输入候选池。
    """

    def write_brief(
        self,
        query: str,
        selected_memories: list[HarvestCandidate],
        policy: Any | None = None,
    ) -> GardenBriefDraft:
        q_clip = (query or "").strip()[:100]
        if not q_clip:
            q_clip = "（空查询）"

        source_ids = [m.memory_id for m in selected_memories[:16]]
        total = len(selected_memories)

        if source_ids:
            use_text = f"共 {total} 条候选记忆可参考：{'、'.join(source_ids[:48])}。请以标识为线索核对上下文。"
        else:
            use_text = "当前无可参考的候选记忆；请勿强行套用外部记忆。"

        draft = GardenBriefDraft(
            intent=f"语义增强简报：用户表达围绕「{q_clip}」",
            use=use_text,
            avoid="不将候选记忆视为确定事实；温室/修剪状态条目不作为积极依据。",
            style="语气中性简短，以标识占位指代记忆卡。",
            safety="不断言用户偏好或事实确定性；未核验结论不向用户转嫁。",
            nudge="请将简报仅作编排线索；若与当前上下文无关请跳过。",
            source_memory_ids=source_ids,
        )
        blob = draft.intent + draft.use + draft.avoid + draft.style + draft.safety + draft.nudge
        draft.token_estimate = max(8, len(blob) // 4 + 20)
        return draft


class FakeDreamWeaverProvider:
    """确定性梦境反思提供者：按标签/文本重叠度生成聚类 proposal。

    仅在输入记忆集合内操作，不新增 memory_id。
    可被测试配置覆盖返回内容（用于模拟非法输出场景）。
    """

    def __init__(self, *, preset_proposals: list[DreamProposal] | None = None) -> None:
        self._preset = preset_proposals

    def propose_clusters(
        self,
        memories: list[DreamMemoryInput],
        policy: object | None = None,
    ) -> DreamProposalBatch:
        if self._preset is not None:
            return DreamProposalBatch(
                proposals=list(self._preset),
                provider_name="fake_dream_weaver",
                prompt_version="preset_v1",
            )

        if not memories:
            return DreamProposalBatch(
                proposals=[],
                provider_name="fake_dream_weaver",
                prompt_version="empty_v1",
            )

        proposals: list[DreamProposal] = []

        # Group by shared tags
        tag_groups: dict[str, list[DreamMemoryInput]] = {}
        for m in memories:
            for t in (m.tags or []):
                tag_groups.setdefault(t, []).append(m)

        seq = 0
        for tag, group in tag_groups.items():
            if len(group) < 2:
                continue
            seq += 1
            source_ids = [m.memory_id for m in group]
            proposals.append(DreamProposal(
                proposal_id=f"dream-prop-{seq:04d}",
                title=f"主题聚类：{tag}",
                summary=f"多条记忆围绕标签「{tag}」形成共同主题，共计 {len(group)} 条相关记忆可互为佐证。"
                        f"记忆标识：{'、'.join(source_ids[:8])}。",
                source_memory_ids=source_ids,
                relation_type=DreamRelationType.SAME_THEME,
                suggested_action=DreamSuggestedAction.RECORD_REFLECTION,
                confidence=0.75,
                reason=f"标签「{tag}」在 {len(group)} 条记忆中重复出现，形成可识别的主题聚类。",
            ))

        # Check for duplicate-like pairs by text overlap
        for i in range(len(memories)):
            for j in range(i + 1, len(memories)):
                a, b = memories[i], memories[j]
                overlap = _text_overlap(a.text, b.text)
                if overlap > 0.5:
                    seq += 1
                    proposals.append(DreamProposal(
                        proposal_id=f"dream-prop-{seq:04d}",
                        title=f"疑似重复：{a.memory_id} ≅ {b.memory_id}",
                        summary=f"记忆 {a.memory_id} 与 {b.memory_id} 内容高度相似（重叠度 {overlap:.2f}），"
                                f"建议人工核对是否需要合并。当前证据不足以自动合并。",
                        source_memory_ids=[a.memory_id, b.memory_id],
                        relation_type=DreamRelationType.DUPLICATE,
                        suggested_action=DreamSuggestedAction.SUGGEST_MERGE,
                        confidence=round(overlap, 4),
                        reason=f"文本内容重叠度 {overlap:.2f} 超过阈值 0.5，疑似重复但仅作建议。",
                    ))

        return DreamProposalBatch(
            proposals=proposals,
            provider_name="fake_dream_weaver",
            prompt_version="deterministic_v1",
        )


def _text_overlap(a: str, b: str) -> float:
    """简单文本重叠度：取两文本的字符 trigram Jaccard 相似度。"""
    if not a or not b:
        return 0.0

    def _trigrams(s: str) -> set[str]:
        s = "  " + s.strip().casefold() + "  "
        return {s[i:i + 3] for i in range(len(s) - 2)}

    ta = _trigrams(a)
    tb = _trigrams(b)
    return len(ta & tb) / max(len(ta | tb), 1)


class FakeCourtAdvisorProvider:
    """确定性法庭旁听顾问——按预设或默认逻辑返回 advice。

    不在测试环境中执行 Plant / Forget / Merge 等真实生长动作。
    """

    def __init__(self, *, preset_advice: CourtAdvice | None = None,
                 force_verdict: str | None = None) -> None:
        self._preset = preset_advice
        self._force_verdict = force_verdict

    def advise(
        self,
        seed: CourtSeedInput,
        context: dict[str, Any] | None = None,
        policy: object | None = None,
    ) -> CourtAdvice:
        if self._preset is not None:
            return self._preset
        if self._force_verdict:
            return CourtAdvice(
                seed_id=seed.seed_id,
                advised_verdict=self._force_verdict,
                confidence=0.8,
                reason=f"Fake advisor opinion: would suggest {self._force_verdict}.",
                source_seed_ids=[seed.seed_id],
            )
        # Default: always agree with something reasonable
        return CourtAdvice(
            seed_id=seed.seed_id,
            advised_verdict="plant" if "prefer" in seed.text.lower() or "喜欢" in seed.text else "hold",
            confidence=0.75,
            reason="Fake advisor default opinion based on seed text signals.",
            source_seed_ids=[seed.seed_id],
            related_memory_ids=[],
            risk_flags=[],
            provider_name="fake_court_advisor",
            prompt_version="deterministic_v1",
        )
