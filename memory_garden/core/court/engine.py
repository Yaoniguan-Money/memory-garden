"""规则版记忆法庭引擎：裁决 Seed，不写 MemoryCard、不做生长动作。"""

from __future__ import annotations

from memory_garden.core.court.case import RuleOutcome, build_court_case
from memory_garden.core.court.interfaces import MemoryCourtEngineProtocol
from memory_garden.core.court.roles import triangulate_arguments
from memory_garden.core.court.verdict import CourtVerdictType
from memory_garden.core.journal import GardenJournal
from memory_garden.core.models import (
    CourtCase,
    GardenEventType,
    GardenObjectType,
    Seed,
    SeedSignalType,
    SeedStatus,
)
from memory_garden.core.policies import (
    ADOPTION_MARKERS,
    BOUNDARY_MARKERS,
    CONSTRAINT_MARKERS,
    CORRECTION_MARKERS,
    EPHEMERAL_MARKERS,
    EXPLICIT_REMEMBER_MARKERS,
    FORGET_OR_PURGE_PHRASES,
    FUTURE_INTENT_MARKERS,
    HYPOTHETICAL_MARKERS,
    IDENTITY_MARKERS,
    NEGATIVE_SELF_TALK_MARKERS,
    PREFERENCE_MARKERS,
    PROCEDURAL_MARKERS,
    SENSITIVE_MARKERS,
    SOCIAL_PLEASANTRIES,
    THIRD_PARTY_MARKERS,
    UNCERTAINTY_MARKERS,
    text_matches_marker_set,
)
from memory_garden.storage.base import GardenRepository

# 法庭额外敏感词（与 policies 合并检测）
_EXTRA_SENSITIVE_MARKERS: tuple[str, ...] = (
    "邮箱",
    "密钥",
    "财务账户",
    "健康诊断",
)

# 否定旧方向 / 推翻既有结论
_NEGATES_PRIOR_MARKERS: tuple[str, ...] = (
    "不是之前那样",
    "之前那个方向不要了",
    "改掉",
    "不再采用",
    "推翻之前",
)

# 长期偏好扩展触发词（规则 4）
_LONG_TERM_EXTRA_MARKERS: tuple[str, ...] = (
    "我决定",
    "第一版",
    "请一直",
    "我不喜欢",
)


_EXTRA_FORGET_FRAGMENTS: tuple[str, ...] = (
    "别记",
    "不要保存",
    "do not remember",
)


def _explicit_forget_request(text: str) -> bool:
    """仅检测明确遗忘短语（不含花园控制口令）。"""
    lower = text.casefold()
    for phrase in FORGET_OR_PURGE_PHRASES:
        if phrase.casefold() in lower:
            return True
    for frag in _EXTRA_FORGET_FRAGMENTS:
        if frag.casefold() in lower:
            return True
    return False


def _all_sensitive_markers() -> tuple[str, ...]:
    return tuple(dict.fromkeys((*SENSITIVE_MARKERS, *_EXTRA_SENSITIVE_MARKERS)))


def _extract_prune_target(seed: Seed) -> str | None:
    ctx = seed.context if isinstance(seed.context, dict) else {}
    for key in ("target_memory_id", "prune_target_memory_id", "contradicts_memory_id"):
        raw = ctx.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return None


def _long_term_signal(seed: Seed, text: str) -> bool:
    if seed.signal_type in (
        SeedSignalType.preference,
        SeedSignalType.constraint,
        SeedSignalType.decision,
    ):
        return True
    markers = (*PREFERENCE_MARKERS, *CONSTRAINT_MARKERS, *_LONG_TERM_EXTRA_MARKERS)
    return text_matches_marker_set(text, markers)


def evaluate_rules(seed: Seed) -> RuleOutcome:
    """按优先级输出裁决，共 27 条规则。

    优先级链：
    forget > sensitive > negative_self > correction >
    explicit_remember > adoption > identity > boundary >
    procedural > future_intent > negates_prior >
    long_term_preference > ephemeral > third_party >
    hypothetical > uncertainty > social_pleasantry >
    default_hold
    """
    text = seed.content.strip()

    # R1: 明确遗忘请求
    if _explicit_forget_request(text):
        return RuleOutcome(
            verdict_type=CourtVerdictType.forget,
            reason="检测到用户明确要求遗忘或删除相关记忆的表述",
            confidence=0.91,
            matched_rules=("r01_explicit_forget_request",),
            risk_flags=("user_requested_forget",),
        )

    # R2: 敏感个人信息 → 温室
    combined_sensitive = _all_sensitive_markers()
    if text_matches_marker_set(text, combined_sensitive):
        return RuleOutcome(
            verdict_type=CourtVerdictType.greenhouse,
            reason="文本包含敏感个人信息线索，宜进入温室隔离审查后再决定采摘范围",
            confidence=0.83,
            matched_rules=("r02_sensitive_personal_info",),
            risk_flags=("greenhouse_candidate", "sensitive_personal_info"),
        )

    # R3: 负面自我评价 → 堆肥
    if seed.signal_type == SeedSignalType.negative_self_talk or text_matches_marker_set(
        text, NEGATIVE_SELF_TALK_MARKERS,
    ):
        return RuleOutcome(
            verdict_type=CourtVerdictType.compost,
            reason="存在强烈负面自我评价，不宜直接固化为长期身份记忆",
            confidence=0.76,
            matched_rules=("r03_negative_self_talk",),
            risk_flags=("identity_freeze_risk",),
        )

    # R4: 用户纠正 → 合并或暂存
    if text_matches_marker_set(text, CORRECTION_MARKERS):
        target = _extract_prune_target(seed)
        if target:
            return RuleOutcome(
                verdict_type=CourtVerdictType.merge,
                reason="用户纠正既有认知，应合并到已有记忆而非新建",
                confidence=0.79,
                matched_rules=("r04a_correction_with_target",),
                risk_flags=("correction",),
                target_memory_id=target,
            )
        return RuleOutcome(
            verdict_type=CourtVerdictType.hold,
            reason="用户纠正意图可见，但缺少明确的合并目标标识",
            confidence=0.65,
            matched_rules=("r04b_correction_no_target",),
            risk_flags=("correction", "merge_target_missing"),
        )

    # R5: 明确记忆指令 → 种植
    if text_matches_marker_set(text, EXPLICIT_REMEMBER_MARKERS):
        return RuleOutcome(
            verdict_type=CourtVerdictType.plant,
            reason="用户明确要求记住此内容",
            confidence=0.92,
            matched_rules=("r05_explicit_remember",),
            risk_flags=("user_requested_memorize",),
        )

    # R6: 采纳信号 → 种植（辅助角色内容升格）
    if text_matches_marker_set(text, ADOPTION_MARKERS):
        return RuleOutcome(
            verdict_type=CourtVerdictType.plant,
            reason="用户明确采纳或认可，可将相关建议升格为记忆",
            confidence=0.81,
            matched_rules=("r06_adoption_signal",),
            risk_flags=("user_adoption",),
        )

    # R7: 身份声明 → 种植
    if text_matches_marker_set(text, IDENTITY_MARKERS):
        return RuleOutcome(
            verdict_type=CourtVerdictType.plant,
            reason="用户描述自我身份或角色，具有长期参考价值",
            confidence=0.84,
            matched_rules=("r07_identity_claim",),
            risk_flags=("identity_memory",),
        )

    # R8: 边界设定 → 种植 + 温室标记
    if text_matches_marker_set(text, BOUNDARY_MARKERS):
        return RuleOutcome(
            verdict_type=CourtVerdictType.plant,
            reason="用户设定了明确边界，应作为高风险约束长期保留",
            confidence=0.88,
            matched_rules=("r08_boundary_setting",),
            risk_flags=("boundary", "high_importance"),
        )

    # R9: 流程/程序性 → 种植
    if text_matches_marker_set(text, PROCEDURAL_MARKERS):
        return RuleOutcome(
            verdict_type=CourtVerdictType.plant,
            reason="用户描述了工作方式或流程偏好",
            confidence=0.77,
            matched_rules=("r09_procedural_pattern",),
            risk_flags=("procedural_knowledge",),
        )

    # R10: 未来意图 → 种植
    if text_matches_marker_set(text, FUTURE_INTENT_MARKERS):
        return RuleOutcome(
            verdict_type=CourtVerdictType.plant,
            reason="用户表达了未来计划或目标",
            confidence=0.73,
            matched_rules=("r10_future_intent",),
            risk_flags=("future_plan", "may_change"),
        )

    # R11: 否定旧方向 → 修剪或暂存
    if text_matches_marker_set(text, _NEGATES_PRIOR_MARKERS):
        target = _extract_prune_target(seed)
        if target:
            return RuleOutcome(
                verdict_type=CourtVerdictType.prune,
                reason="用户否定既有方向且提供了可定位的旧记忆目标",
                confidence=0.78,
                matched_rules=("r11a_negates_prior_with_target",),
                risk_flags=("possible_contradiction",),
                target_memory_id=target,
            )
        return RuleOutcome(
            verdict_type=CourtVerdictType.hold,
            reason="否定旧方向的意图可见，但缺少明确的修剪目标标识",
            confidence=0.64,
            matched_rules=("r11b_negates_prior_no_target",),
            risk_flags=("possible_contradiction", "prune_target_missing"),
        )

    # R12: 长期偏好/约束/决策 → 种植
    if _long_term_signal(seed, text):
        return RuleOutcome(
            verdict_type=CourtVerdictType.plant,
            reason="表述呈现可持续的长期偏好、约束或决策倾向",
            confidence=0.85,
            matched_rules=("r12_long_term_preference",),
            risk_flags=("structured_intent",),
        )

    # R13: 临时/短暂内容 → 堆肥
    if text_matches_marker_set(text, EPHEMERAL_MARKERS):
        return RuleOutcome(
            verdict_type=CourtVerdictType.compost,
            reason="内容具有明显临时性，不应固化为长期记忆",
            confidence=0.71,
            matched_rules=("r13_ephemeral_content",),
            risk_flags=("ephemeral", "low_signal"),
        )

    # R14: 第三方声明 → 暂存（非本人信息，需额外验证）
    if text_matches_marker_set(text, THIRD_PARTY_MARKERS):
        return RuleOutcome(
            verdict_type=CourtVerdictType.hold,
            reason="内容涉及第三方信息，非用户直接表述，暂存观察",
            confidence=0.55,
            matched_rules=("r14_third_party_claim",),
            risk_flags=("third_party", "verification_needed"),
        )

    # R15: 假设/反事实 → 暂存
    if text_matches_marker_set(text, HYPOTHETICAL_MARKERS):
        return RuleOutcome(
            verdict_type=CourtVerdictType.hold,
            reason="内容为假设性或反事实表述，信号不稳定",
            confidence=0.52,
            matched_rules=("r15_hypothetical",),
            risk_flags=("hypothetical", "unstable_signal"),
        )

    # R16: 不确定性表述 → 暂存
    if text_matches_marker_set(text, UNCERTAINTY_MARKERS):
        return RuleOutcome(
            verdict_type=CourtVerdictType.hold,
            reason="用户表达不确定，信号不足以支撑立即种植",
            confidence=0.49,
            matched_rules=("r16_uncertainty",),
            risk_flags=("uncertain", "low_confidence"),
        )

    # R17: 社交礼仪 → 不形成记忆（跳过，不存 Seed 才是最佳，但已在 pipeline 中则堆肥）
    # 30 字符阈值：极短消息中偏好/约束信号弱，保守跳过；
    # 注意短消息如 "谢谢，我喜欢这个方案" 可能被误判，需权衡。
    if text_matches_marker_set(text, SOCIAL_PLEASANTRIES) and len(text) < 30:
        return RuleOutcome(
            verdict_type=CourtVerdictType.compost,
            reason="社交礼仪用语，不应固化为长期记忆",
            confidence=0.93,
            matched_rules=("r17_social_pleasantry",),
            risk_flags=("social_only", "discard"),
        )

    # R18: 默认暂存
    return RuleOutcome(
        verdict_type=CourtVerdictType.hold,
        reason="信号偏弱或语义不稳定，默认暂存观察而非种下",
        confidence=0.57,
        matched_rules=("r18_low_signal_default_hold",),
        risk_flags=("low_signal",),
    )


class MemoryCourtEngine(MemoryCourtEngineProtocol):
    """规则版法庭：持久化 CourtCase、更新种子状态为 in_court、写入两条领域事件。"""

    def __init__(
        self,
        repository: GardenRepository,
        journal: GardenJournal | None = None,
    ) -> None:
        self._repository = repository
        self._journal = journal if journal is not None else GardenJournal(repository)

    def open_case(self, seed: Seed) -> CourtCase:
        seed_status_before = seed.status
        outcome = evaluate_rules(seed)
        p_arg, d_arg, pg_arg = triangulate_arguments(seed, outcome)
        case = build_court_case(seed, outcome, p_arg, d_arg, pg_arg)
        verdict = case.judge_verdict

        self._repository.save_court_case(case)

        updated_seed = seed.model_copy(update={"status": SeedStatus.in_court})
        self._repository.update_seed(updated_seed)

        self._journal.record_event(
            event_type=GardenEventType.court_opened,
            object_type=GardenObjectType.court_case,
            object_id=case.id,
            summary=f"规则法庭开庭（案件 {case.id}）",
            metadata={
                "seed_id": seed.id,
                "seed_status_before": seed_status_before.value,
                "engine": "rule_based",
            },
        )
        self._journal.record_event(
            event_type=GardenEventType.verdict_made,
            object_type=GardenObjectType.court_case,
            object_id=case.id,
            summary=f"法庭判决：{verdict.verdict.value}",
            metadata={
                "seed_id": seed.id,
                "verdict": verdict.verdict.value,
                "reason": verdict.reason,
                "confidence": verdict.confidence,
                "target_memory_id": verdict.target_memory_id,
                "matched_rules": list(case.matched_rules),
                "risk_flags": list(case.risk_flags),
            },
        )
        return case

    def open_cases(self, seeds: list[Seed]) -> list[CourtCase]:
        return [self.open_case(s) for s in seeds]
