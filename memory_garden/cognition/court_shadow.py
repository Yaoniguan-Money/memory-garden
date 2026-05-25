"""Stag 3: Court Shadow Mode — LLM 旁听顾问，不替代规则判决。

流水线：
1. 若 court_shadow_mode=DISABLED，直接返回规则判决
2. 若 court_shadow_mode=SHADOW + provider 就绪，调用 advise()
3. 校验 CourtAdvice
4. 对比 rule_verdict 与 advised_verdict
5. 生成 CourtShadowComparison
6. final_verdict 永远等于 rule_verdict

RuleCourt 负责裁判。LLM 只负责旁听。
"""

from __future__ import annotations

from typing import Any

from memory_garden.cognition.models import (
    CourtSeedInput,
    CourtShadowComparison,
    CourtShadowMode,
)
from memory_garden.cognition.providers import CourtAdvisorProvider
from memory_garden.cognition.validation import (
    resolve_disagreement_type,
    validate_court_advice,
)


def _seed_to_court_input(seed: Any) -> CourtSeedInput:
    """将 Seed 转换为 CourtSeedInput。

    注意：text 优先取 content，source 取 source_excerpt 原文摘录，
    两者内容可能不同（content 是提取的核心，source_excerpt 是原文）。
    """
    return CourtSeedInput(
        seed_id=getattr(seed, "id", ""),
        text=getattr(seed, "content", "") or getattr(seed, "source_excerpt", ""),
        tags=list(getattr(seed, "tags", []) or []),
        signal_type=str(getattr(seed, "signal_type", "")) if getattr(seed, "signal_type", None) else None,
        source=getattr(seed, "source_excerpt", None),
    )


def _empty_comparison(
    seed_id: str,
    rule_verdict: str,
    *,
    rule_reason: str | None = None,
    fallback_used: bool = False,
    fallback_reason: str | None = None,
    warnings: list[str] | None = None,
) -> CourtShadowComparison:
    return CourtShadowComparison(
        seed_id=seed_id,
        rule_verdict=rule_verdict,
        llm_advised_verdict=None,
        final_verdict=rule_verdict,
        agreement=True,
        disagreement_type=None,
        rule_reason=rule_reason,
        final_decision_source="rule_court",
        fallback_used=fallback_used,
        fallback_reason=fallback_reason,
        warnings=list(warnings or []),
    )


def run_court_shadow(
    seed: Any,
    rule_verdict: str,
    rule_reason: str,
    *,
    mode: CourtShadowMode = CourtShadowMode.DISABLED,
    advisor_provider: CourtAdvisorProvider | None = None,
    context: dict[str, Any] | None = None,
) -> CourtShadowComparison:
    """运行法庭旁听周期。

    Args:
        seed: 种子对象（须有 id / content / tags 属性）
        rule_verdict: 规则法庭判决的 verdict 字符串
        rule_reason: 规则法庭判决的理由
        mode: DISABLED 或 SHADOW
        advisor_provider: 可选 CourtAdvisorProvider
        context: 附加上下文

    Returns:
        CourtShadowComparison — rule_verdict 始终是 final_verdict
    """
    sid = getattr(seed, "id", "")

    if mode == CourtShadowMode.DISABLED or advisor_provider is None:
        return _empty_comparison(
            sid, rule_verdict, rule_reason=rule_reason,
            fallback_used=(mode == CourtShadowMode.SHADOW and advisor_provider is None),
            fallback_reason="advisor_provider not configured" if advisor_provider is None else None,
        )

    if rule_verdict == "forget":
        reason = "advisor intentionally skipped: forget is a terminal verdict"
        return _empty_comparison(
            sid,
            rule_verdict,
            rule_reason=rule_reason,
            fallback_used=False,
            fallback_reason=reason,
            warnings=[reason],
        )

    seed_input = _seed_to_court_input(seed)

    # ── 调用 advisor ─────────────────────────────────────────────
    try:
        advice = advisor_provider.advise(seed_input, context)
    except Exception as exc:
        return _empty_comparison(
            sid, rule_verdict,
            rule_reason=rule_reason,
            fallback_used=True,
            fallback_reason=f"advisor_provider exception: {exc}",
        )

    # ── 校验 ────────────────────────────────────────────────────
    issues = validate_court_advice(advice, seed_input, context)

    if issues:
        return CourtShadowComparison(
            seed_id=sid,
            rule_verdict=rule_verdict,
            llm_advised_verdict=None,
            final_verdict=rule_verdict,
            agreement=False,
            disagreement_type=None,
            final_decision_source="rule_court",
            fallback_used=True,
            fallback_reason=f"advice validation failed: {'; '.join(issues)}",
            warnings=issues,
        )

    # ── 对比 ────────────────────────────────────────────────────
    advised = advice.advised_verdict
    agreement = (rule_verdict == advised)
    disagreement = resolve_disagreement_type(rule_verdict, advised)

    return CourtShadowComparison(
        seed_id=sid,
        rule_verdict=rule_verdict,
        llm_advised_verdict=advised,
        final_verdict=rule_verdict,  # 永远等于规则判决
        agreement=agreement,
        disagreement_type=disagreement,
        rule_reason=rule_reason,
        llm_reason=advice.reason,
        confidence=advice.confidence,
        risk_flags=list(advice.risk_flags),
        warnings=list(advice.warnings or []),
        final_decision_source="rule_court",
        provider_name=advice.provider_name,
        prompt_version=advice.prompt_version,
        fallback_used=False,
    )
