"""第三层 Stage 3D：规则版候选排序（稳定、可解释；不调外部模型）。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from memory_garden.harvest.models import (
    HarvestPolicyDecision,
    HarvestQuery,
    HarvestScore,
    MemoryCandidate,
)
from memory_garden.harvest.policy import HarvestBudgetPolicy

_MISSING_RELEVANCE = -1.0


class HarvestRankOutcome(BaseModel):
    """排序结果：候选新序 + 一条聚合策略说明（复用 ``HarvestPolicyDecision``）。"""

    model_config = ConfigDict(validate_assignment=True)

    ranked_candidates: list[MemoryCandidate] = Field(default_factory=list)
    policy_decision: HarvestPolicyDecision


class RuleBasedHarvestRanker:
    """按 ``HarvestScore.relevance`` 主序、``policy_boost`` 辅序做稳定降序排列。"""

    def rank(
        self,
        query: HarvestQuery,
        candidates: list[MemoryCandidate],
        scores: list[HarvestScore],
        policy: HarvestBudgetPolicy | None = None,
    ) -> HarvestRankOutcome:
        _ = query  # 预留与查询一致性校验，本规则版不使用 query 加权
        by_id: dict[str, HarvestScore] = {}
        dup_notes: list[str] = []
        for s in scores:
            cid = s.candidate_id
            if cid in by_id:
                dup_notes.append(f"duplicate_score_skipped:candidate_id={cid}")
                continue
            by_id[cid] = s

        indexed: list[tuple[int, MemoryCandidate, float, float, float, bool]] = []
        for i, c in enumerate(candidates):
            sc = by_id.get(c.candidate_id)
            if sc is None:
                indexed.append((i, c, _MISSING_RELEVANCE, 0.0, 0.0, True))
                continue
            indexed.append((i, c, float(sc.relevance), float(sc.recency), float(sc.policy_boost), False))

        # 稳定升序键：relevance 降序 → recency 降序 → policy_boost 降序 → 原序升序
        indexed.sort(key=lambda row: (-row[2], -row[3], -row[4], row[0]))

        cap: int | None = None
        if policy is not None:
            cap = int(policy.max_candidates)

        trimmed = indexed[:] if cap is None else indexed[:cap] if cap > 0 else []

        ranked = [row[1] for row in trimmed]
        ranked_ids = {c.candidate_id for c in ranked}

        allow_ids = [c.candidate_id for c in ranked]
        reject_ids: list[str] = []
        reasons: list[str] = list(dup_notes)

        for i, c, rel, _rec, _pb, missing in indexed:
            if c.candidate_id not in ranked_ids:
                reject_ids.append(c.candidate_id)
            if missing:
                reasons.append(f"missing_score:candidate_id={c.candidate_id}")

        if cap is not None and cap >= 0 and len(indexed) > len(ranked):
            reasons.append(f"ranking_cap_applied:max_candidates={cap}")
        if cap == 0:
            reasons.append("ranking_cap_zero_all_excluded")

        seen_reason: set[str] = set()
        ordered_reasons: list[str] = []
        for r in reasons:
            if r not in seen_reason:
                seen_reason.add(r)
                ordered_reasons.append(r)

        decision = HarvestPolicyDecision(
            allow_candidate_ids=allow_ids,
            reject_candidate_ids=reject_ids,
            capped_total=cap if policy is not None else None,
            reasons=ordered_reasons,
        )

        return HarvestRankOutcome(ranked_candidates=ranked, policy_decision=decision)
