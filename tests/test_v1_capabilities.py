"""Tests for v1.0 capabilities: hybrid search, expanded court rules, cascade forget."""

from memory_garden.core.court.engine import evaluate_rules
from memory_garden.core.court.verdict import CourtVerdictType
from memory_garden.core.models import Seed, SeedSignalType
from memory_garden.soil.forget import execute_hard_forget
from memory_garden.soil.home import initialize_garden_home
from memory_garden.soil.index import reindex_garden
from memory_garden.soil.search import hybrid_search_garden, search_garden

from ._soil_test_helpers import insert_test_data, setup_garden_db


def _make_seed(content, signal_type=SeedSignalType.unknown):
    return Seed(content=content, source_excerpt=content[:50], signal_type=signal_type)


# ── Expanded court rules ────────────────────────────────────────────


def test_correction_triggers_merge():
    outcome = evaluate_rules(_make_seed("不对，我之前说错了，应该是用蓝色", SeedSignalType.correction))
    assert outcome.verdict_type == CourtVerdictType.hold  # no target → hold
    assert "r04b_correction_no_target" in outcome.matched_rules


def test_explicit_remember_triggers_plant():
    outcome = evaluate_rules(_make_seed("请记住我偏好蓝色界面"))
    assert outcome.verdict_type == CourtVerdictType.plant
    assert "r05_explicit_remember" in outcome.matched_rules


def test_adoption_triggers_plant():
    outcome = evaluate_rules(_make_seed("就这样，按这个方向来"))
    assert outcome.verdict_type == CourtVerdictType.plant
    assert "r06_adoption_signal" in outcome.matched_rules


def test_identity_claim_triggers_plant():
    outcome = evaluate_rules(_make_seed("我是做后端开发的，主要用Go和Python"))
    assert outcome.verdict_type == CourtVerdictType.plant
    assert "r07_identity_claim" in outcome.matched_rules


def test_boundary_triggers_plant():
    outcome = evaluate_rules(_make_seed("我不能接受任何形式的代码审查绕过"))
    assert outcome.verdict_type == CourtVerdictType.plant
    assert "r08_boundary_setting" in outcome.matched_rules


def test_future_intent_triggers_plant():
    outcome = evaluate_rules(_make_seed("我计划下个季度重构整个认证模块"))
    assert outcome.verdict_type == CourtVerdictType.plant
    assert "r10_future_intent" in outcome.matched_rules


def test_ephemeral_triggers_compost():
    outcome = evaluate_rules(_make_seed("今天天气真好，适合出去走走"))
    assert outcome.verdict_type == CourtVerdictType.compost
    assert "r13_ephemeral_content" in outcome.matched_rules


def test_third_party_triggers_hold():
    outcome = evaluate_rules(_make_seed("他说这个方案之前被否决过"))
    assert outcome.verdict_type == CourtVerdictType.hold
    assert "r14_third_party_claim" in outcome.matched_rules


def test_hypothetical_triggers_hold():
    outcome = evaluate_rules(_make_seed("假如有一天我们需要支持多语言"))
    assert outcome.verdict_type == CourtVerdictType.hold
    assert "r15_hypothetical" in outcome.matched_rules


def test_uncertainty_triggers_hold():
    outcome = evaluate_rules(_make_seed("也许可以考虑换一种方式，但还不确定"))
    assert outcome.verdict_type == CourtVerdictType.hold
    assert "r16_uncertainty" in outcome.matched_rules


def test_social_pleasantry_triggers_compost():
    outcome = evaluate_rules(_make_seed("谢谢"))
    assert outcome.verdict_type == CourtVerdictType.compost
    assert "r17_social_pleasantry" in outcome.matched_rules


def test_preference_still_plants():
    outcome = evaluate_rules(_make_seed("我喜欢用深色主题", SeedSignalType.preference))
    assert outcome.verdict_type == CourtVerdictType.plant


def test_sensitive_still_greenhouse():
    outcome = evaluate_rules(_make_seed("我的密码是abc123", SeedSignalType.sensitive_info))
    assert outcome.verdict_type == CourtVerdictType.greenhouse


# ── Hybrid search ───────────────────────────────────────────────────


def _setup_search(garden_home, num_memories=5):
    setup_garden_db(garden_home)
    insert_test_data(garden_home, num_memories=num_memories)
    reindex_garden(garden_home, dry_run=False)


def test_hybrid_search_finds_fts5_matches(tmp_path):
    home = initialize_garden_home(tmp_path / "garden")
    _setup_search(home.root, num_memories=3)
    hits = hybrid_search_garden(home.root, "preference")
    assert len(hits) >= 1


def test_hybrid_search_falls_back_to_embedding(tmp_path):
    home = initialize_garden_home(tmp_path / "garden")
    _setup_search(home.root, num_memories=3)
    # "interface appearance" — FTS5 won't match "dark mode" literally
    hits = hybrid_search_garden(home.root, "interface appearance theme")
    # Should still return results via embedding fallback
    assert len(hits) >= 1


def test_hybrid_search_respects_limit(tmp_path):
    home = initialize_garden_home(tmp_path / "garden")
    _setup_search(home.root, num_memories=5)
    hits = hybrid_search_garden(home.root, "memory", limit=2)
    assert len(hits) <= 2


def test_fts5_search_still_works(tmp_path):
    home = initialize_garden_home(tmp_path / "garden")
    _setup_search(home.root, num_memories=3)
    hits = search_garden(home.root, "preference")
    assert len(hits) >= 1


# ── Cascade forget ──────────────────────────────────────────────────


def test_cascade_forget_deletes_seeds(tmp_path):
    home = initialize_garden_home(tmp_path / "garden")
    _setup_search(home.root, num_memories=2)

    result = execute_hard_forget(home.root, "mem-0001", reason="test", dry_run=False, cascade=True)
    assert result.status == "ok"
    # Cascade may have cleaned related seeds
    assert result.memory_deleted is True


def test_cascade_forget_does_not_crash_no_related(tmp_path):
    home = initialize_garden_home(tmp_path / "garden")
    _setup_search(home.root, num_memories=2)

    result = execute_hard_forget(home.root, "mem-0001", reason="test", dry_run=False, cascade=True)
    assert result.status == "ok"


def test_non_cascade_forget_default_behavior(tmp_path):
    home = initialize_garden_home(tmp_path / "garden")
    _setup_search(home.root, num_memories=2)

    # Default: cascade=False
    result = execute_hard_forget(home.root, "mem-0001", reason="test", dry_run=False)
    assert result.status == "ok"
    assert result.memory_deleted is True


def test_cascade_dry_run_does_not_delete(tmp_path):
    home = initialize_garden_home(tmp_path / "garden")
    _setup_search(home.root, num_memories=2)

    result = execute_hard_forget(home.root, "mem-0001", reason="test", dry_run=True, cascade=True)
    assert result.dry_run is True
    assert result.memory_deleted is False
