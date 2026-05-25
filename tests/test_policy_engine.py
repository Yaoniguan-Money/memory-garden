"""Stage 8C/8D: PolicyEngine decisions."""

from __future__ import annotations

import json

from memory_garden.covenant import (
    PolicyDecision,
    PolicyEngine,
    PolicySeverity,
    default_garden_covenant,
)


def _engine() -> PolicyEngine:
    return PolicyEngine(default_garden_covenant())


def test_policy_decision_json_round_trip() -> None:
    decision = _engine().is_open_command("花花开")
    blob = decision.model_dump(mode="json")
    json.dumps(blob)
    restored = PolicyDecision.model_validate(blob)
    assert restored.allowed is True
    assert restored.reason


def test_open_and_close_commands_recognized() -> None:
    engine = _engine()
    assert engine.is_open_command("花花开").allowed is True
    assert engine.is_open_command("/GARDEN ON").allowed is True
    assert engine.is_close_command("花花关").allowed is True
    assert engine.is_close_command("/garden off").allowed is True
    assert engine.is_open_command("请帮我花花开一下").allowed is False


def test_commands_are_not_memorized() -> None:
    decision = _engine().should_memorize_command("花花开")
    assert decision.allowed is False
    assert decision.action == "ignore_command"
    assert decision.severity == PolicySeverity.critical
    assert "hard_baselines.commands_never_memorized" in decision.matched_rules


def test_can_admit_normal_seed() -> None:
    seed = {"id": "s1", "content": "I prefer concise answers.", "signal_type": "preference"}
    decision = _engine().can_admit_seed(seed)
    assert decision.allowed is True
    assert decision.object_id == "s1"


def test_command_seed_is_blocked() -> None:
    seed = {"id": "s_cmd", "content": "花花关", "signal_type": "unknown"}
    decision = _engine().can_admit_seed(seed)
    assert decision.allowed is False
    assert decision.severity == PolicySeverity.critical


def test_assistant_memory_requires_user_adoption() -> None:
    seed = {"id": "s_ai", "content": "Use this architecture.", "signal_type": "decision"}
    decision = _engine().can_admit_seed(seed, {"source_role": "assistant"})
    assert decision.allowed is False
    assert "ai_self_memory_requires_user_adoption" in decision.matched_rules[0]


def test_assistant_memory_can_be_candidate_when_adopted() -> None:
    seed = {"id": "s_ai", "content": "Use this architecture.", "signal_type": "decision"}
    decision = _engine().can_admit_seed(seed, {"source_role": "assistant", "user_adopted": True})
    assert decision.allowed is True


def test_negative_self_talk_seed_is_blocked() -> None:
    seed = {"id": "s_bad", "content": "我真是一无是处", "signal_type": "negative_self_talk"}
    decision = _engine().can_admit_seed(seed)
    assert decision.allowed is False
    assert "emotional_safety.prevent_negative_identity_lock" in decision.matched_rules


def test_negative_identity_lock_policy_blocks_phrase() -> None:
    decision = _engine().should_prevent_negative_identity_lock("我真是一无是处")
    assert decision.allowed is False
    assert decision.action == "prevent_negative_identity_lock"
    assert decision.severity == PolicySeverity.critical


def test_sensitive_memory_routes_to_greenhouse() -> None:
    decision = _engine().route_sensitive_memory({"id": "m1", "sensitivity": "high"})
    assert decision.allowed is True
    assert decision.metadata["route"] == "greenhouse"


def test_can_harvest_normal_memory() -> None:
    decision = _engine().can_harvest_memory({"id": "m1", "lifecycle": "bloom"})
    assert decision.allowed is True
    assert decision.action == "allow_harvest"


def test_greenhouse_memory_not_in_ordinary_harvest() -> None:
    decision = _engine().can_harvest_memory({"id": "m_g", "lifecycle": "greenhouse"})
    assert decision.allowed is False
    assert decision.action == "exclude_from_harvest"


def test_pruned_memory_only_avoid_slot() -> None:
    engine = _engine()
    assert engine.can_harvest_memory({"id": "m_p", "lifecycle": "pruned"}, purpose="brief").allowed is False
    assert engine.can_harvest_memory({"id": "m_p", "lifecycle": "pruned"}, purpose="avoid").allowed is True
    slots = engine.allowed_brief_slots({"id": "m_p", "lifecycle": "pruned"})
    assert slots.metadata["allowed_slots"] == ["avoid"]


def test_compost_memory_only_safety_or_nudge() -> None:
    engine = _engine()
    assert engine.can_harvest_memory({"id": "m_c", "lifecycle": "composted"}, purpose="brief").allowed is False
    assert engine.can_harvest_memory({"id": "m_c", "lifecycle": "composted"}, purpose="safety").allowed is True
    assert engine.can_harvest_memory({"id": "m_c", "lifecycle": "composted"}, purpose="nudge").allowed is True


def test_brief_preference_requires_source_ids() -> None:
    decision = _engine().can_write_brief_instruction("User prefers terse answers.", [])
    assert decision.allowed is False
    assert decision.severity == PolicySeverity.critical


def test_brief_instruction_with_sources_allowed() -> None:
    decision = _engine().can_write_brief_instruction("User prefers terse answers.", ["m1"])
    assert decision.allowed is True


def test_model_call_blocks_full_garden_context() -> None:
    decision = _engine().can_send_to_model({"full_garden_context": True}, "brief_writer", "example")
    assert decision.allowed is False
    assert decision.severity == PolicySeverity.critical


def test_model_call_blocks_greenhouse_raw_text() -> None:
    decision = _engine().can_send_to_model({"greenhouse_raw_text": True}, "llm_judge")
    assert decision.allowed is False


def test_model_call_blocks_hard_forgotten_text() -> None:
    decision = _engine().can_send_to_model({"hard_forgotten_text": True}, "llm_judge")
    assert decision.allowed is False


def test_model_call_allows_selected_context() -> None:
    decision = _engine().can_send_to_model({"selected_context": ["m1"]}, "brief_writer", "example")
    assert decision.allowed is True
    assert decision.action == "allow_model_call"


def test_display_blocks_redacted_and_hard_forgotten() -> None:
    engine = _engine()
    assert engine.can_display_memory({"id": "m_r", "redacted_text": True}, "report").allowed is False
    hard = engine.can_display_memory({"id": "m_h", "hard_forgotten": True}, "report", debug=True)
    assert hard.allowed is False
    assert hard.severity == PolicySeverity.critical


def test_export_blocks_api_key_and_hard_forgotten() -> None:
    engine = _engine()
    assert engine.can_export_record({"id": "r1", "api_key": True}, "bundle").allowed is False
    hard = engine.can_export_record({"id": "r2", "hard_forgotten": True}, "bundle")
    assert hard.allowed is False
    assert hard.severity == PolicySeverity.critical


def test_hard_forget_requires_target_id() -> None:
    engine = _engine()
    assert engine.can_hard_forget({}).allowed is False
    assert engine.can_hard_forget({"id": "m1"}).allowed is True
