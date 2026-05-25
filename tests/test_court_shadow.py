"""Stage 3: Court Shadow Mode 测试。

覆盖：
- court_shadow_mode 默认关闭
- final_verdict 永远等于 rule_verdict
- agreement / disagreement 检测
- LLM 建议不执行 Plant / Forget / Merge
- 校验失败 fallback
- provider 异常 fallback
- 4 组固定样例
"""

import pytest

from memory_garden.cognition.models import (
    CourtAdvice,
    CourtSeedInput,
    CourtShadowComparison,
    CourtShadowMode,
)
from memory_garden.cognition.providers import CourtAdvisorProvider
from memory_garden.cognition.fake_providers import FakeCourtAdvisorProvider
from memory_garden.cognition.court_shadow import run_court_shadow
from memory_garden.cognition.validation import (
    resolve_disagreement_type,
    validate_court_advice,
)


def _make_seed(sid="s1", text="", tags=None, signal_type=None):
    return type("Seed", (), {
        "id": sid, "content": text, "source_excerpt": text[:50],
        "tags": tags or [], "signal_type": signal_type or "unknown",
    })()


# ── models ──────────────────────────────────────────────────────────


def test_court_shadow_mode_enum():
    assert CourtShadowMode.DISABLED == "disabled"
    assert CourtShadowMode.SHADOW == "shadow"


def test_court_advice_constructs():
    a = CourtAdvice(
        seed_id="s1", advised_verdict="hold", confidence=0.7, reason="uncertain",
        source_seed_ids=["s1"],
    )
    assert a.seed_id == "s1"
    assert a.advised_verdict == "hold"


def test_court_shadow_comparison_constructs():
    c = CourtShadowComparison(
        seed_id="s1", rule_verdict="plant",
        llm_advised_verdict="hold", final_verdict="plant",
        agreement=False, disagreement_type="rule_plant_llm_hold",
        final_decision_source="rule_court",
    )
    assert c.final_verdict == "plant"
    assert c.final_decision_source == "rule_court"
    assert c.agreement is False


# ── validation ──────────────────────────────────────────────────────


def test_validate_advice_valid_returns_empty():
    seed = CourtSeedInput(seed_id="s1", text="hi")
    advice = CourtAdvice(seed_id="s1", advised_verdict="hold", confidence=0.5,
                         reason="ok", source_seed_ids=["s1"])
    assert validate_court_advice(advice, seed) == []


def test_validate_advice_invalid_verdict():
    seed = CourtSeedInput(seed_id="s1", text="hi")
    advice = CourtAdvice(seed_id="s1", advised_verdict="not_a_verdict", confidence=0.5,
                         reason="ok", source_seed_ids=["s1"])
    assert len(validate_court_advice(advice, seed)) >= 1


def test_validate_advice_missing_seed_id():
    seed = CourtSeedInput(seed_id="s1", text="hi")
    advice = CourtAdvice(seed_id="s1", advised_verdict="hold", confidence=0.5,
                         reason="ok", source_seed_ids=["s_other"])
    assert len(validate_court_advice(advice, seed)) >= 1


def test_validate_advice_seed_id_mismatch():
    seed = CourtSeedInput(seed_id="s1", text="hi")
    advice = CourtAdvice(seed_id="other", advised_verdict="hold", confidence=0.5,
                         reason="ok", source_seed_ids=["s1"])
    assert len(validate_court_advice(advice, seed)) >= 1


def test_validate_advice_empty_reason():
    """Pydantic Field(min_length=1) catches empty reason at construction."""
    with pytest.raises(Exception):
        CourtAdvice(seed_id="s1", advised_verdict="hold", confidence=0.5,
                    reason="", source_seed_ids=["s1"])


def test_resolve_disagreement_same():
    assert resolve_disagreement_type("plant", "plant") == "same_verdict"


def test_resolve_disagreement_different():
    assert resolve_disagreement_type("plant", "hold") == "rule_plant_llm_hold"
    assert resolve_disagreement_type("hold", "plant") == "rule_hold_llm_plant"
    assert resolve_disagreement_type("forget", "plant") == "rule_forget_llm_plant"
    assert resolve_disagreement_type("compost", "merge") == "rule_compost_llm_merge"


def test_resolve_disagreement_llm_none():
    assert resolve_disagreement_type("plant", None) is None


# ── shadow pipeline ─────────────────────────────────────────────────


def test_disabled_mode_returns_empty_comparison():
    seed = _make_seed("s1", "I prefer dark mode")
    comp = run_court_shadow(seed, "plant", "valid rule reason",
                            mode=CourtShadowMode.DISABLED)
    assert comp.final_verdict == "plant"
    assert comp.llm_advised_verdict is None
    assert comp.fallback_used is False


def test_disabled_mode_no_provider_called():
    seed = _make_seed("s1", "test")
    comp = run_court_shadow(seed, "hold", "rule reason",
                            mode=CourtShadowMode.DISABLED,
                            advisor_provider=FakeCourtAdvisorProvider())
    # Provider is present but mode is disabled → should not call
    assert comp.llm_advised_verdict is None


def test_shadow_mode_with_provider():
    seed = _make_seed("s1", "I prefer dark mode")
    provider = FakeCourtAdvisorProvider()
    comp = run_court_shadow(seed, "plant", "rule reason",
                            mode=CourtShadowMode.SHADOW,
                            advisor_provider=provider)
    assert comp.final_verdict == "plant"
    assert comp.llm_advised_verdict is not None
    assert comp.final_decision_source == "rule_court"
    assert comp.fallback_used is False


def test_final_verdict_always_equals_rule_verdict():
    """无论 LLM 建议什么，final_verdict 始终等于 rule_verdict。"""
    seed = _make_seed("s1", "test content")
    # Force LLM to suggest "plant" when rule says "hold"
    provider = FakeCourtAdvisorProvider(force_verdict="plant")
    comp = run_court_shadow(seed, "hold", "rule hold reason",
                            mode=CourtShadowMode.SHADOW,
                            advisor_provider=provider)
    assert comp.final_verdict == "hold"
    assert comp.llm_advised_verdict == "plant"
    assert comp.agreement is False


def test_llm_suggest_plant_rule_hold():
    """LLM 建议 PLANT 但规则是 HOLD → final 仍是 HOLD。"""
    seed = _make_seed("s1", "something")
    provider = FakeCourtAdvisorProvider(force_verdict="plant")
    comp = run_court_shadow(seed, "hold", "hold reason",
                            mode=CourtShadowMode.SHADOW,
                            advisor_provider=provider)
    assert comp.final_verdict == "hold"
    assert comp.disagreement_type == "rule_hold_llm_plant"


def test_llm_suggest_hold_rule_plant():
    """LLM 建议 HOLD 但规则是 PLANT → final 仍是 PLANT。"""
    seed = _make_seed("s1", "I prefer dark mode")
    provider = FakeCourtAdvisorProvider(force_verdict="hold")
    comp = run_court_shadow(seed, "plant", "plant reason",
                            mode=CourtShadowMode.SHADOW,
                            advisor_provider=provider)
    assert comp.final_verdict == "plant"
    assert comp.disagreement_type == "rule_plant_llm_hold"


def test_llm_suggest_forget_not_executed():
    """LLM 建议 FORGET → 不会真正执行 Forget，只记录 comparison。"""
    seed = _make_seed("s1", "delete this")
    provider = FakeCourtAdvisorProvider(force_verdict="forget")
    comp = run_court_shadow(seed, "hold", "hold reason",
                            mode=CourtShadowMode.SHADOW,
                            advisor_provider=provider)
    # LLM 建议 forget，但 final 仍是 hold
    assert comp.final_verdict == "hold"
    assert comp.llm_advised_verdict == "forget"
    assert comp.agreement is False


def test_llm_suggest_merge_not_executed():
    """LLM 建议 MERGE → 不会真正执行 Merge。"""
    seed = _make_seed("s1", "similar content")
    provider = FakeCourtAdvisorProvider(force_verdict="merge")
    comp = run_court_shadow(seed, "compost", "compost reason",
                            mode=CourtShadowMode.SHADOW,
                            advisor_provider=provider)
    assert comp.final_verdict == "compost"


def test_forget_rule_verdict_skips_advisor():
    class _SpyAdvisor:
        def __init__(self):
            self.called = False

        def advise(self, seed, context=None, policy=None):
            self.called = True
            return CourtAdvice(seed_id=seed.seed_id, advised_verdict="plant",
                               confidence=0.5, reason="bad",
                               source_seed_ids=[seed.seed_id])

    provider = _SpyAdvisor()
    seed = _make_seed("s1", "forget this")
    comp = run_court_shadow(seed, "forget", "explicit forget request",
                            mode=CourtShadowMode.SHADOW,
                            advisor_provider=provider)
    assert provider.called is False
    assert comp.final_verdict == "forget"
    assert comp.llm_advised_verdict is None
    assert comp.final_decision_source == "rule_court"
    assert comp.fallback_used is False


def test_provider_exception_falls_back():
    class _Failing:
        def advise(self, seed, context=None, policy=None):
            raise RuntimeError("provider crash")

    seed = _make_seed("s1", "test")
    comp = run_court_shadow(seed, "plant", "rule reason",
                            mode=CourtShadowMode.SHADOW,
                            advisor_provider=_Failing())
    assert comp.final_verdict == "plant"
    assert comp.fallback_used is True
    assert "provider crash" in (comp.fallback_reason or "")


def test_advice_invalid_verdict_falls_back():
    """Advice 带有非法 verdict → 校验失败，fallback。"""
    seed = _make_seed("s1", "test")
    bad_advice = CourtAdvice(
        seed_id="s1", advised_verdict="not_valid", confidence=0.5,
        reason="bad", source_seed_ids=["s1"],
    )
    provider = FakeCourtAdvisorProvider(preset_advice=bad_advice)
    comp = run_court_shadow(seed, "hold", "rule hold",
                            mode=CourtShadowMode.SHADOW,
                            advisor_provider=provider)
    assert comp.fallback_used is True


def test_advice_missing_seed_id_falls_back():
    """Advice 缺少当前 seed_id → 校验失败，fallback。"""
    seed = _make_seed("s1", "test")
    bad_advice = CourtAdvice(
        seed_id="s1", advised_verdict="hold", confidence=0.5,
        reason="ok", source_seed_ids=["other_seed"],
    )
    provider = FakeCourtAdvisorProvider(preset_advice=bad_advice)
    comp = run_court_shadow(seed, "plant", "rule plant",
                            mode=CourtShadowMode.SHADOW,
                            advisor_provider=provider)
    assert comp.fallback_used is True


def test_fake_provider_satisfies_protocol():
    assert isinstance(FakeCourtAdvisorProvider(), CourtAdvisorProvider)


# ── 4 组固定样例 ────────────────────────────────────────────────────


def test_fixture_rule_hold_llm_plant():
    """样例 1: 规则 HOLD，LLM 建议 PLANT → final HOLD。"""
    seed = _make_seed("s1", "some unclear signal")
    provider = FakeCourtAdvisorProvider(force_verdict="plant")
    comp = run_court_shadow(seed, "hold", "signal too weak",
                            mode=CourtShadowMode.SHADOW,
                            advisor_provider=provider)
    assert comp.final_verdict == "hold"
    assert comp.disagreement_type == "rule_hold_llm_plant"


def test_fixture_rule_plant_llm_hold():
    """样例 2: 规则 PLANT，LLM 建议 HOLD → final PLANT。"""
    seed = _make_seed("s1", "I prefer dark mode")
    provider = FakeCourtAdvisorProvider(force_verdict="hold")
    comp = run_court_shadow(seed, "plant", "strong preference signal",
                            mode=CourtShadowMode.SHADOW,
                            advisor_provider=provider)
    assert comp.final_verdict == "plant"
    assert comp.disagreement_type == "rule_plant_llm_hold"


def test_fixture_rule_forget_llm_plant():
    """样例 3: 规则 FORGET，LLM 建议 PLANT → final FORGET。"""
    seed = _make_seed("s1", "忘掉之前我说的偏好")
    provider = FakeCourtAdvisorProvider(force_verdict="plant")
    comp = run_court_shadow(seed, "forget", "explicit forget request",
                            mode=CourtShadowMode.SHADOW,
                            advisor_provider=provider)
    assert comp.final_verdict == "forget"
    # 用户显式遗忘命令不能进入 LLM 旁听链路。
    assert comp.llm_advised_verdict is None
    assert comp.fallback_reason == "advisor intentionally skipped: forget is a terminal verdict"


def test_fixture_rule_compost_llm_merge():
    """样例 4: 规则 COMPOST，LLM 建议 MERGE → final COMPOST。"""
    seed = _make_seed("s1", "temporary negative thought")
    provider = FakeCourtAdvisorProvider(force_verdict="merge")
    comp = run_court_shadow(seed, "compost", "ephemeral negative content",
                            mode=CourtShadowMode.SHADOW,
                            advisor_provider=provider)
    assert comp.final_verdict == "compost"
    assert comp.disagreement_type == "rule_compost_llm_merge"


# ── no side effects ─────────────────────────────────────────────────


def test_no_memory_garden_created(tmp_path):
    import os
    cwd = os.getcwd()
    existed = os.path.exists(os.path.join(cwd, ".memory_garden"))
    run_court_shadow(_make_seed("s1", "test"), "plant", "reason",
                     mode=CourtShadowMode.DISABLED)
    if not existed:
        assert not os.path.exists(os.path.join(cwd, ".memory_garden"))
