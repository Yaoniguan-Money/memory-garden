"""法庭案件装配：规则匹配结果与 CourtCase 构造。"""

from __future__ import annotations

from dataclasses import dataclass

from memory_garden.core.court.verdict import CourtVerdict, CourtVerdictType
from memory_garden.core.models import CourtCase, Seed


@dataclass(frozen=True)
class RuleOutcome:
    """单次规则裁决的结构化结果（写入 CourtCase 与日志 metadata）。"""

    verdict_type: CourtVerdictType
    reason: str
    confidence: float
    matched_rules: tuple[str, ...]
    risk_flags: tuple[str, ...]
    target_memory_id: str | None = None


def build_court_case(
    seed: Seed,
    outcome: RuleOutcome,
    prosecutor_argument: str,
    defender_argument: str,
    privacy_guard_argument: str,
) -> CourtCase:
    """由三方陈述与 RuleOutcome 组装可持久化模型。"""
    verdict = CourtVerdict(
        verdict=outcome.verdict_type,
        reason=outcome.reason,
        confidence=outcome.confidence,
        target_memory_id=outcome.target_memory_id,
    )
    return CourtCase(
        seed_id=seed.id,
        prosecutor_argument=prosecutor_argument,
        defender_argument=defender_argument,
        privacy_guard_argument=privacy_guard_argument,
        judge_verdict=verdict,
        matched_rules=list(outcome.matched_rules),
        risk_flags=list(outcome.risk_flags),
    )
