"""Tests for Covenant Enforcer — policy enforcement bridge."""

from memory_garden.covenant.enforcer import CovenantEnforcer, EnforcementResult


def _make_enforcer() -> CovenantEnforcer:
    from memory_garden.covenant.defaults import default_garden_covenant
    return CovenantEnforcer(default_garden_covenant())


def _make_memory(memory_id="m1", lifecycle="bloom", sensitivity="low", tags=None, **kwargs):
    return type("Memory", (), {
        "id": memory_id,
        "lifecycle": lifecycle,
        "sensitivity": sensitivity,
        "tags": tags or [],
        **kwargs,
    })()


# ── Harvest enforcement ─────────────────────────────────────────────


def test_before_harvest_allows_normal_memory():
    enforcer = _make_enforcer()
    mem = _make_memory(lifecycle="bloom")
    result = enforcer.before_harvest(mem, purpose="brief")
    assert result.allowed is True


def test_before_harvest_denies_greenhouse_for_ordinary_purpose():
    enforcer = _make_enforcer()
    mem = _make_memory(lifecycle="greenhouse")
    result = enforcer.before_harvest(mem, purpose="brief")
    assert result.allowed is False
    assert "greenhouse" in result.reason.lower()


def test_before_harvest_denies_pruned_for_ordinary_purpose():
    enforcer = _make_enforcer()
    mem = _make_memory(lifecycle="pruned")
    result = enforcer.before_harvest(mem, purpose="brief")
    assert result.allowed is False


def test_before_harvest_denies_composted_for_ordinary_purpose():
    enforcer = _make_enforcer()
    mem = _make_memory(lifecycle="composted")
    result = enforcer.before_harvest(mem, purpose="brief")
    assert result.allowed is False


def test_before_harvest_denies_hard_forgotten():
    enforcer = _make_enforcer()
    mem = _make_memory(hard_forgotten=True)
    result = enforcer.before_harvest(mem)
    assert result.allowed is False
    assert result.severity.value == "critical"


def test_before_harvest_batch_filters_correctly():
    enforcer = _make_enforcer()
    memories = [
        _make_memory("m1", lifecycle="bloom"),
        _make_memory("m2", lifecycle="greenhouse"),
        _make_memory("m3", lifecycle="bloom"),
        _make_memory("m4", lifecycle="pruned"),
    ]
    allowed, denied = enforcer.before_harvest_batch(memories, purpose="brief")
    assert len(allowed) == 2
    assert len(denied) == 2


# ── Model call enforcement ──────────────────────────────────────────


def test_before_model_call_denies_when_disabled():
    enforcer = _make_enforcer()
    result = enforcer.before_model_call({}, purpose="brief_writing")
    # Default covenant disables external model calls
    assert result.allowed is False


def test_before_model_call_denies_full_garden_context():
    enforcer = _make_enforcer()
    result = enforcer.before_model_call({"full_garden_context": True}, purpose="brief_writing")
    assert result.allowed is False


# ── Display enforcement ─────────────────────────────────────────────


def test_before_display_allows_normal_memory():
    enforcer = _make_enforcer()
    mem = _make_memory(lifecycle="bloom")
    result = enforcer.before_display(mem, surface="report")
    assert result.allowed is True


def test_before_display_hides_greenhouse_raw_text():
    enforcer = _make_enforcer()
    mem = _make_memory(lifecycle="greenhouse")
    result = enforcer.before_display(mem, surface="report")
    assert result.allowed is False


def test_before_display_hides_hard_forgotten():
    enforcer = _make_enforcer()
    mem = _make_memory(hard_forgotten=True)
    result = enforcer.before_display(mem, surface="report")
    assert result.allowed is False


# ── Export enforcement ──────────────────────────────────────────────


def test_before_export_denies_api_keys():
    enforcer = _make_enforcer()
    record = type("Record", (), {"id": "r1", "contains_api_key": True})()
    result = enforcer.before_export(record, export_mode="bundle")
    assert result.allowed is False


def test_before_export_denies_hard_forgotten():
    enforcer = _make_enforcer()
    record = type("Record", (), {"id": "r1", "hard_forgotten_text": True})()
    result = enforcer.before_export(record, export_mode="bundle")
    assert result.allowed is False


def test_before_export_allows_normal_record():
    enforcer = _make_enforcer()
    record = type("Record", (), {"id": "r1"})()
    result = enforcer.before_export(record, export_mode="bundle")
    assert result.allowed is True


# ── Forget enforcement ──────────────────────────────────────────────


def test_before_hard_forget_allows_when_valid():
    enforcer = _make_enforcer()
    target = type("Target", (), {"id": "m1"})()
    result = enforcer.before_hard_forget(target)
    assert result.allowed is True


def test_before_hard_forget_denies_without_id():
    enforcer = _make_enforcer()
    target = type("Target", (), {"id": ""})()
    result = enforcer.before_hard_forget(target)
    assert result.allowed is False


# ── Seed admission enforcement ──────────────────────────────────────


def test_before_admit_seed_denies_control_commands():
    enforcer = _make_enforcer()
    seed = type("Seed", (), {"id": "s1", "content": "花花开", "signal_type": "unknown"})()
    result = enforcer.before_admit_seed(seed)
    assert result.allowed is False


def test_before_admit_seed_allows_normal_text():
    enforcer = _make_enforcer()
    seed = type("Seed", (), {"id": "s1", "content": "I prefer dark mode", "signal_type": "preference"})()
    result = enforcer.before_admit_seed(seed)
    assert result.allowed is True


def test_before_admit_seed_denies_assistant_role_without_adoption():
    enforcer = _make_enforcer()
    seed = type("Seed", (), {
        "id": "s1", "content": "You should use dark mode",
        "signal_type": "unknown", "source_role": "assistant",
    })()
    result = enforcer.before_admit_seed(seed)
    assert result.allowed is False


# ── Negative identity check ─────────────────────────────────────────


def test_check_negative_identity_with_custom_covenant():
    from memory_garden.covenant.models import GardenCovenant, EmotionalSafetyPolicy
    covenant = GardenCovenant(
        emotional_safety=EmotionalSafetyPolicy(
            forbidden_identity_phrases=["我好废", "我不行", "什么都做不好"],
        ),
        metadata={"source": "test"},
    )
    enforcer = CovenantEnforcer(covenant)
    r1 = enforcer.check_negative_identity("我好废什么都做不好")
    assert r1.allowed is False
    r2 = enforcer.check_negative_identity("我今天完成了所有任务")
    assert r2.allowed is True


def test_check_negative_identity_allows_normal_with_default():
    enforcer = _make_enforcer()
    result = enforcer.check_negative_identity("我今天完成了所有任务")
    assert result.allowed is True


# ── Command detection ───────────────────────────────────────────────


def test_is_control_command_detects_flower_open():
    enforcer = _make_enforcer()
    result = enforcer.is_control_command("花花开")
    assert result.allowed is True


def test_is_control_command_detects_flower_close():
    enforcer = _make_enforcer()
    result = enforcer.is_control_command("花花关")
    assert result.allowed is True


def test_is_control_command_rejects_normal_text():
    enforcer = _make_enforcer()
    result = enforcer.is_control_command("今天天气很好")
    # is_control_command returns allow() for non-commands ("it's fine, no command detected")
    assert result.allowed is True
    assert "Not a control command" in result.reason


def test_should_memorize_denies_control_commands():
    enforcer = _make_enforcer()
    result = enforcer.should_memorize("花花开")
    # should_memorize_command returns allowed=False for control commands
    # meaning "should NOT memorize"
    assert result.allowed is False


# ── EnforcementResult model ─────────────────────────────────────────


def test_enforcement_result_allow():
    r = EnforcementResult.allow()
    assert r.allowed is True


def test_enforcement_result_deny():
    r = EnforcementResult.deny("test reason", policy_name="test", action="block")
    assert r.allowed is False
    assert r.reason == "test reason"
    assert r.severity.value == "critical"
