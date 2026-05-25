"""Stage 8F: Covenant audit and status payloads."""

from __future__ import annotations

import json

from memory_garden.covenant import (
    CovenantAudit,
    CovenantStatus,
    PolicyEngine,
    build_covenant_status,
    covenant_hash,
    default_garden_covenant,
)


def test_covenant_hash_is_stable() -> None:
    first = covenant_hash(default_garden_covenant())
    second = covenant_hash(default_garden_covenant())
    assert first == second
    assert len(first) == 64


def test_covenant_hash_changes_when_policy_changes() -> None:
    covenant = default_garden_covenant()
    original = covenant_hash(covenant)
    covenant.harvest.brief_token_budget = 300
    assert covenant_hash(covenant) != original


def test_audit_records_decisions_and_trims() -> None:
    audit = CovenantAudit(max_recent_decisions=2)
    engine = PolicyEngine(default_garden_covenant())
    d1 = engine.is_open_command("hello")
    d2 = engine.is_open_command("花花开")
    d3 = engine.should_memorize_command("花花关")
    audit.record_decision(d1)
    audit.record_decision(d2)
    audit.record_decision(d3)
    recent = audit.list_recent_decisions()
    assert [d.id for d in recent] == [d2.id, d3.id]


def test_audit_inspect_is_json_safe_and_short() -> None:
    audit = CovenantAudit()
    covenant = default_garden_covenant()
    audit.record_decision(PolicyEngine(covenant).should_memorize_command("花花开"))
    payload = audit.inspect(covenant)
    json.dumps(payload)
    assert payload["blocked_decision_count"] == 1
    assert payload["critical_decision_count"] == 1
    assert payload["covenant_hash"] == covenant_hash(covenant)
    raw = json.dumps(payload, ensure_ascii=False)
    assert "花花开" not in raw


def test_status_payload_json_round_trip() -> None:
    status = build_covenant_status(default_garden_covenant())
    blob = status.model_dump(mode="json")
    json.dumps(blob)
    restored = CovenantStatus.model_validate(blob)
    assert restored.hard_baselines_status == "ok"
    assert restored.full_garden_context_allowed is False
    assert restored.greenhouse_raw_export_allowed is False


def test_status_contains_expected_fields() -> None:
    status = build_covenant_status(default_garden_covenant())
    assert status.covenant_version == 1
    assert status.feedback_mode == "closing_only"
    assert status.external_llm_allowed is True
    assert status.hard_baselines_status == "ok"
