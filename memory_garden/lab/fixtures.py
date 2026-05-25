"""第六层 Stage 6B：Lab 套件样例库（纯数据，不参与 Core/Runtime 执行）。

``metadata.lab_fixture_example_actual`` 中为与断言配套的 **手写快照**，
供 ``evaluate_case`` / ``evaluate_suite_cases`` 做确定性回放（本模块不调用评估函数）。
"""

from __future__ import annotations

from typing import Any

from memory_garden.lab.models import LabAssertion, LabAssertionType, LabCase, LabSuite, LabTarget

_META_ACTUAL_KEY = "lab_fixture_example_actual"

# -----------------------------------------------------------------------------
# Helpers（仅拼装 Pydantic 模型）
# -----------------------------------------------------------------------------


def _case(
    case_id: str,
    *,
    title: str,
    description: str,
    scenario_hint: str,
    primary_target: LabTarget,
    assertions: list[LabAssertion],
    example_actual: dict[str, Any],
    extra_meta: dict[str, Any] | None = None,
) -> LabCase:
    md: dict[str, Any] = {
        "primary_target": primary_target.value,
        "scenario_hint": scenario_hint,
        "input_snapshot_hint": scenario_hint,
        _META_ACTUAL_KEY: example_actual,
    }
    if extra_meta:
        md.update(extra_meta)
    return LabCase(
        case_id=case_id,
        name=title,
        description=description,
        assertions=assertions,
        metadata=md,
    )


def seed_extraction_fixture_suite() -> LabSuite:
    """偏好类表达与会话口令相关：期望 **偏好** 可被捕捉为待定信号，口令 **不重写** 偏好槽位。"""
    suite_id = "lab_suite_seed_extraction_6b_v1"
    return LabSuite(
        suite_id=suite_id,
        name="Lab·Seed 快照（语义期望）",
        metadata={"fixture_kind": "seed_extraction", "version": "6b"},
        cases=[
            _case(
                "lab.6b.seed.preference_pending.standard_v1",
                title="偏好句应生成 pending 语义信号（快照）",
                description="在用户表达稳定偏好且不命中控制口令时，期望存在至少一条 pending 偏好类信号占位。",
                scenario_hint='用户："我喜欢默认深色界面"',
                primary_target=LabTarget.seed,
                assertions=[
                    LabAssertion(
                        assertion_type=LabAssertionType.count_equals,
                        target=LabTarget.seed,
                        field_path="pending_preference_signals",
                        expected=1,
                    ),
                    LabAssertion(
                        assertion_type=LabAssertionType.field_absent,
                        target=LabTarget.seed,
                        field_path="control_command_echo_as_preference_seed",
                        expected=None,
                    ),
                ],
                example_actual={
                    "seed": {
                        "pending_preference_signals": ["pref_turn_001"],
                    }
                },
            ),
            _case(
                "lab.6b.seed.control_commands.no_preference_capture_v1",
                title="花花开/花花关 不应产生偏好型 seed 捕获（快照）",
                description="控制口令路径不得把口语令本身当作用户偏好 seed 纳入 pending 列表。",
                scenario_hint='用户整句仅为 "花花开" 或 "花花关"',
                primary_target=LabTarget.seed,
                assertions=[
                    LabAssertion(
                        assertion_type=LabAssertionType.count_equals,
                        target=LabTarget.seed,
                        field_path="pending_preference_signals",
                        expected=0,
                    ),
                    LabAssertion(
                        assertion_type=LabAssertionType.count_equals,
                        target=LabTarget.seed,
                        field_path="control_command_only_events",
                        expected=1,
                    ),
                ],
                example_actual={
                    "seed": {
                        "pending_preference_signals": [],
                        "control_command_only_events": ["cmd_open_or_close"],
                    }
                },
            ),
        ],
    )


def runtime_command_fixture_suite() -> LabSuite:
    """Runtime 口令短路快照：handled 时不应再走 after/agent 钩子（由布尔占位表达）。"""
    return LabSuite(
        suite_id="lab_suite_runtime_commands_6b_v1",
        name="Lab·Runtime 命令短路快照",
        metadata={"fixture_kind": "runtime_command", "version": "6b"},
        cases=[
            _case(
                "lab.6b.runtime.short_circuit.no_after_reply_agent_v1",
                title="花花开命中：handled=True 且无 after/agent 占位调用",
                description="与控制口令语义一致：短路返回，不编排 before→agent→after 正常链。",
                scenario_hint='用户："花花开"（仅口令）',
                primary_target=LabTarget.runtime,
                assertions=[
                    LabAssertion(
                        assertion_type=LabAssertionType.is_true,
                        target=LabTarget.runtime,
                        field_path="command_short_circuited",
                        expected=None,
                    ),
                    LabAssertion(
                        assertion_type=LabAssertionType.is_false,
                        target=LabTarget.runtime,
                        field_path="after_reply_invoked",
                        expected=None,
                    ),
                    LabAssertion(
                        assertion_type=LabAssertionType.is_false,
                        target=LabTarget.runtime,
                        field_path="hosted_agent_generate_invoked",
                        expected=None,
                    ),
                ],
                example_actual={
                    "runtime": {
                        "command_short_circuited": True,
                        "after_reply_invoked": False,
                        "hosted_agent_generate_invoked": False,
                    }
                },
            ),
            _case(
                "lab.6b.runtime.open_chat.after_chain_expected_v1",
                title="普通 OPEN 会话句：短路未命中（快照）",
                description="控制口令之外的用户句，期望 command_short_circuited 为假（由 LabRunner 未来将真实字段映射）。",
                scenario_hint='已花花开 OPEN 后的普通闲聊："今天天气还行"',
                primary_target=LabTarget.runtime,
                assertions=[
                    LabAssertion(
                        assertion_type=LabAssertionType.is_false,
                        target=LabTarget.runtime,
                        field_path="command_short_circuited",
                        expected=None,
                    ),
                    LabAssertion(
                        assertion_type=LabAssertionType.equals,
                        target=LabTarget.runtime,
                        field_path="session_state_placeholder",
                        expected="open",
                    ),
                ],
                example_actual={
                    "runtime": {
                        "command_short_circuited": False,
                        "session_state_placeholder": "open",
                        "after_reply_invoked": True,
                    },
                },
            ),
        ],
    )


def court_verdict_fixture_suite() -> LabSuite:
    """法庭/生长约束：负面自评与敏感信息的路径期望（全部为示意字段）。"""
    return LabSuite(
        suite_id="lab_suite_court_verdict_6b_v1",
        name="Lab·Court / Growth 判决期望",
        metadata={"fixture_kind": "court_verdict", "version": "6b"},
        cases=[
            _case(
                "lab.6b.court.block_negative_identity_plant.v1",
                title="负面自评不应晋升为长期身份记忆（快照）",
                description="检测到负面自我叙事时，应阻止直接进入 identity 定植路径。",
                scenario_hint='用户："我真是一无是处"',
                primary_target=LabTarget.court,
                assertions=[
                    LabAssertion(
                        assertion_type=LabAssertionType.is_false,
                        target=LabTarget.court,
                        field_path="allow_plant_as_stable_identity_trait",
                        expected=None,
                    ),
                    LabAssertion(
                        assertion_type=LabAssertionType.contains,
                        target=LabTarget.court,
                        field_path="safety_escalations",
                        expected="defer_identity_planting",
                    ),
                ],
                example_actual={
                    "court": {
                        "allow_plant_as_stable_identity_trait": False,
                        "safety_escalations": ["defer_identity_planting"],
                    },
                },
            ),
            _case(
                "lab.6b.growth.sensitive_greenhouse_path.v1",
                title="敏感信息应走温室 / 加固路径（快照）",
                description="占位：期望敏感片段进入 greenhouse_policy 队列而非直通播种。",
                scenario_hint='用户披露疑似隐私凭证片段（示意）',
                primary_target=LabTarget.growth,
                assertions=[
                    LabAssertion(
                        assertion_type=LabAssertionType.is_true,
                        target=LabTarget.growth,
                        field_path="sensitive_routed_via_greenhouse_check",
                        expected=None,
                    ),
                    LabAssertion(
                        assertion_type=LabAssertionType.is_false,
                        target=LabTarget.growth,
                        field_path="auto_planted_from_raw_user_line",
                        expected=None,
                    ),
                ],
                example_actual={
                    "growth": {
                        "sensitive_routed_via_greenhouse_check": True,
                        "auto_planted_from_raw_user_line": False,
                    },
                },
            ),
        ],
    )


def harvest_brief_fixture_suite() -> LabSuite:
    """Harvest：简报可追溯但不得夹带完整第一层卡片正文快照。"""
    return LabSuite(
        suite_id="lab_suite_harvest_brief_6b_v1",
        name="Lab·Harvest Brief 期望",
        metadata={"fixture_kind": "harvest_brief", "version": "6b"},
        cases=[
            _case(
                "lab.6b.harvest.no_full_card_dump_in_digest.v1",
                title="简报不得嵌完整 MemoryCard 正文",
                description="Harvest 简报仅允许摘录/长度占位，不得 dump 首张卡片全文字段。",
                scenario_hint='before_reply → brief 快照',
                primary_target=LabTarget.harvest,
                assertions=[
                    LabAssertion(
                        assertion_type=LabAssertionType.is_false,
                        target=LabTarget.harvest,
                        field_path="brief_embeds_complete_memory_card_plaintext",
                        expected=None,
                    ),
                    LabAssertion(
                        assertion_type=LabAssertionType.field_absent,
                        target=LabTarget.harvest,
                        field_path="serialised_full_cards_bodies_dump",
                        expected=None,
                    ),
                ],
                example_actual={
                    "harvest": {
                        "brief_embeds_complete_memory_card_plaintext": False,
                    },
                },
            ),
            _case(
                "lab.6b.harvest.digest_has_source_ids_short_form.v1",
                title="溯源以 id / 短语为主而非全文",
                description="简报侧应存在可追溯 id 列表，且单段摘录长度受占位上限约束。",
                scenario_hint='brief.source_memory_ids 只读标识',
                primary_target=LabTarget.harvest,
                assertions=[
                    LabAssertion(
                        assertion_type=LabAssertionType.count_at_most,
                        target=LabTarget.harvest,
                        field_path="source_memory_ids",
                        expected=32,
                    ),
                    LabAssertion(
                        assertion_type=LabAssertionType.equals,
                        target=LabTarget.harvest,
                        field_path="longest_plaintext_fragment_chars",
                        expected=120,
                    ),
                    LabAssertion(
                        assertion_type=LabAssertionType.is_true,
                        target=LabTarget.harvest,
                        field_path="truncation_policy_placeholder_enforced",
                        expected=None,
                    ),
                ],
                example_actual={
                    "harvest": {
                        "source_memory_ids": ["m1", "m2"],
                        "longest_plaintext_fragment_chars": 120,
                        "truncation_policy_placeholder_enforced": True,
                    },
                },
            ),
        ],
    )


def observatory_redaction_fixture_suite() -> LabSuite:
    """Observatory：PUBLIC 视图不暴露整条用户/助手轮次正文。"""
    return LabSuite(
        suite_id="lab_suite_observatory_redaction_6b_v1",
        name="Lab·Observatory 脱敏期望",
        metadata={"fixture_kind": "observatory_redaction", "version": "6b"},
        cases=[
            _case(
                "lab.6b.observatory.public.no_full_user_message.v1",
                title="PUBLIC 视图不出现完整 user_message（快照占位）",
                description="仅以布尔与长度占位断言，不存储真实长文。",
                scenario_hint='ObservationView redaction=PUBLIC',
                primary_target=LabTarget.observatory,
                assertions=[
                    LabAssertion(
                        assertion_type=LabAssertionType.is_false,
                        target=LabTarget.observatory,
                        field_path="public_sections_include_entire_user_message",
                        expected=None,
                    ),
                    LabAssertion(
                        assertion_type=LabAssertionType.field_absent,
                        target=LabTarget.observatory,
                        field_path="public_dump.user_message_plaintext_full",
                        expected=None,
                    ),
                ],
                example_actual={
                    "observatory": {
                        "public_sections_include_entire_user_message": False,
                        "redaction_level": "public",
                    },
                },
            ),
            _case(
                "lab.6b.observatory.public.no_full_assistant_reply.v1",
                title="PUBLIC 视图不出现完整 assistant_reply（快照占位）",
                description="同上，针对助手应答全文。",
                scenario_hint='ObservationView redaction=PUBLIC',
                primary_target=LabTarget.observatory,
                assertions=[
                    LabAssertion(
                        assertion_type=LabAssertionType.is_false,
                        target=LabTarget.observatory,
                        field_path="public_sections_include_entire_assistant_reply",
                        expected=None,
                    ),
                    LabAssertion(
                        assertion_type=LabAssertionType.is_true,
                        target=LabTarget.observatory,
                        field_path="uses_truncated_excerpt_only_placeholder",
                        expected=None,
                    ),
                ],
                example_actual={
                    "observatory": {
                        "public_sections_include_entire_assistant_reply": False,
                        "uses_truncated_excerpt_only_placeholder": True,
                        "redaction_level": "public",
                    },
                },
            ),
        ],
    )


def default_lab_suites() -> list[LabSuite]:
    """稳定排序的套件列表（供 Runner 占位与回归清单）。"""
    return [
        seed_extraction_fixture_suite(),
        runtime_command_fixture_suite(),
        court_verdict_fixture_suite(),
        harvest_brief_fixture_suite(),
        observatory_redaction_fixture_suite(),
    ]


def fixture_example_actual_from_case(lc: LabCase) -> dict[str, Any]:
    """读取用例附带的手写快照（若缺失则为空字典）。"""
    raw = lc.metadata.get(_META_ACTUAL_KEY)
    return dict(raw) if isinstance(raw, dict) else {}
