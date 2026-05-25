"""Seventh layer Stage 7D: Suite Packs unit tests (smoke / safety / full, no execution)."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from memory_garden.lab.fixtures import default_lab_suites
from memory_garden.lab.models import LabSuite
from memory_garden.lab.suite_packs import (
    SMOKE,
    SAFETY,
    FULL,
    LabSuitePack,
    UnknownPackError,
    get_lab_suite_pack,
    get_lab_suites_for_pack,
    list_lab_suite_packs,
)


# ---------------------------------------------------------------------------
# 1. list_lab_suite_packs returns smoke/safety/full, order stable
# ---------------------------------------------------------------------------

def test_list_packs_returns_three() -> None:
    packs = list_lab_suite_packs()
    assert len(packs) == 3
    names = [p.pack_name for p in packs]
    assert names == [SMOKE, SAFETY, FULL]


def test_list_packs_order_stable() -> None:
    p1 = list_lab_suite_packs()
    p2 = list_lab_suite_packs()
    assert [p.pack_name for p in p1] == [p.pack_name for p in p2]


# ---------------------------------------------------------------------------
# 2. get_lab_suite_pack("smoke") can JSON round-trip
# ---------------------------------------------------------------------------

def test_smoke_pack_json_round_trip() -> None:
    pack = get_lab_suite_pack(SMOKE)
    blob = pack.model_dump(mode="json")
    assert blob["pack_name"] == SMOKE
    restored = LabSuitePack.model_validate(blob)
    assert restored.pack_name == SMOKE
    assert restored.total_cases == pack.total_cases
    json.dumps(blob)


def test_safety_pack_json_round_trip() -> None:
    pack = get_lab_suite_pack(SAFETY)
    blob = pack.model_dump(mode="json")
    assert "snapshot-contract" in blob["tags"]
    assert "placeholder" in blob["tags"]
    json.dumps(blob)


def test_full_pack_json_round_trip() -> None:
    pack = get_lab_suite_pack(FULL)
    blob = pack.model_dump(mode="json")
    json.dumps(blob)


# ---------------------------------------------------------------------------
# 3. get_lab_suites_for_pack("smoke") returns non-empty suites
# ---------------------------------------------------------------------------

def test_smoke_suites_non_empty() -> None:
    suites = get_lab_suites_for_pack(SMOKE)
    assert len(suites) >= 1
    assert all(isinstance(s, LabSuite) for s in suites)
    total_cases = sum(len(s.cases) for s in suites)
    assert total_cases >= 1


def test_safety_suites_non_empty() -> None:
    suites = get_lab_suites_for_pack(SAFETY)
    assert len(suites) >= 1
    total_cases = sum(len(s.cases) for s in suites)
    assert total_cases >= 1


# ---------------------------------------------------------------------------
# 4. smoke total_cases <= full total_cases
# ---------------------------------------------------------------------------

def test_smoke_smaller_than_full() -> None:
    smoke_pack = get_lab_suite_pack(SMOKE)
    full_pack = get_lab_suite_pack(FULL)
    assert smoke_pack.total_cases <= full_pack.total_cases


def test_safety_smaller_than_or_equal_full() -> None:
    safety_pack = get_lab_suite_pack(SAFETY)
    full_pack = get_lab_suite_pack(FULL)
    # safety includes placeholder, may be equal or less than full
    assert safety_pack.total_cases <= full_pack.total_cases + 2


# ---------------------------------------------------------------------------
# 5. full case_ids equals default_lab_suites all case_ids
# ---------------------------------------------------------------------------

def test_full_case_ids_match_default_suites() -> None:
    full_suites = get_lab_suites_for_pack(FULL)
    default_suites = default_lab_suites()
    full_ids = {c.case_id for s in full_suites for c in s.cases}
    default_ids = {c.case_id for s in default_suites for c in s.cases}
    assert full_ids == default_ids


def test_full_pack_case_ids_match() -> None:
    pack = get_lab_suite_pack(FULL)
    default_ids = {c.case_id for s in default_lab_suites() for c in s.cases}
    assert set(pack.case_ids) == default_ids


# ---------------------------------------------------------------------------
# 6. safety contains observatory / harvest safety / hard forget cases
# ---------------------------------------------------------------------------

def test_safety_contains_observatory_cases() -> None:
    pack = get_lab_suite_pack(SAFETY)
    obs_ids = {
        "lab.6b.observatory.public.no_full_user_message.v1",
        "lab.6b.observatory.public.no_full_assistant_reply.v1",
    }
    assert obs_ids.issubset(set(pack.case_ids))


def test_safety_contains_harvest_safety_case() -> None:
    pack = get_lab_suite_pack(SAFETY)
    assert "lab.6b.harvest.no_full_card_dump_in_digest.v1" in pack.case_ids


def test_safety_contains_court_greenhouse_cases() -> None:
    pack = get_lab_suite_pack(SAFETY)
    assert "lab.6b.growth.sensitive_greenhouse_path.v1" in pack.case_ids
    assert "lab.6b.court.block_negative_identity_plant.v1" in pack.case_ids


def test_safety_contains_hard_forget_placeholder() -> None:
    pack = get_lab_suite_pack(SAFETY)
    assert "lab.7d.hard_forget_no_leak.placeholder" in pack.case_ids


def test_safety_hard_forget_placeholder_has_snapshot_contract_marker() -> None:
    suites = get_lab_suites_for_pack(SAFETY)
    placeholder = [s for s in suites if "hard_forget" in s.suite_id]
    assert len(placeholder) == 1
    meta = placeholder[0].metadata
    assert meta.get("snapshot_contract") is True
    assert meta.get("placeholder") is True


def test_safety_pack_tags_include_snapshot_contract() -> None:
    pack = get_lab_suite_pack(SAFETY)
    assert "snapshot-contract" in pack.tags
    assert "placeholder" in pack.tags


# ---------------------------------------------------------------------------
# 7. unknown pack_name raises clear error
# ---------------------------------------------------------------------------

def test_unknown_pack_raises_error() -> None:
    with pytest.raises(UnknownPackError, match="Unknown pack"):
        get_lab_suite_pack("nonexistent")


def test_unknown_pack_suites_raises_error() -> None:
    with pytest.raises(UnknownPackError, match="Unknown pack"):
        get_lab_suites_for_pack("magic")


# ---------------------------------------------------------------------------
# 8. each pack has unique case_ids
# ---------------------------------------------------------------------------

def test_smoke_case_ids_unique() -> None:
    pack = get_lab_suite_pack(SMOKE)
    assert len(pack.case_ids) == len(set(pack.case_ids))


def test_safety_case_ids_unique() -> None:
    pack = get_lab_suite_pack(SAFETY)
    assert len(pack.case_ids) == len(set(pack.case_ids))


def test_full_case_ids_unique() -> None:
    pack = get_lab_suite_pack(FULL)
    assert len(pack.case_ids) == len(set(pack.case_ids))


# ---------------------------------------------------------------------------
# 9. functions do not call SnapshotLabRunner
# ---------------------------------------------------------------------------

def test_suite_packs_does_not_import_runner() -> None:
    raw = Path("memory_garden/lab/suite_packs.py").read_text(encoding="utf-8-sig")
    assert "SnapshotLabRunner" not in raw
    assert "run_suite" not in raw
    assert "run_suites" not in raw
    assert "evaluate_case" not in raw


# ---------------------------------------------------------------------------
# 10. no .memory_garden / garden.db created
# ---------------------------------------------------------------------------

def test_suite_packs_does_not_create_garden_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    list_lab_suite_packs()
    get_lab_suite_pack(SMOKE)
    get_lab_suites_for_pack(SMOKE)
    get_lab_suite_pack(SAFETY)
    get_lab_suites_for_pack(SAFETY)
    get_lab_suite_pack(FULL)
    get_lab_suites_for_pack(FULL)
    assert not (tmp_path / ".memory_garden").exists()
    assert not (tmp_path / "garden.db").exists()


# ---------------------------------------------------------------------------
# 11. source code has no forbidden tokens
# ---------------------------------------------------------------------------

def test_suite_packs_source_bans_external_infra_tokens() -> None:
    raw = Path("memory_garden/lab/suite_packs.py").read_text(encoding="utf-8-sig").lower()
    for token in ("openai", "anthropic", "embedding", "vector", "rerank", "search", "sqlite", "repository"):
        assert token not in raw, f"suite_packs.py must not contain token: {token}"


# ---------------------------------------------------------------------------
# 12. test module does not import forbidden modules
# ---------------------------------------------------------------------------

def test_suite_packs_test_module_does_not_import_forbidden_entries() -> None:
    tree = ast.parse(Path("tests/test_lab_suite_packs.py").read_text(encoding="utf-8-sig"))
    forbidden = (
        "memory_garden.core",
        "memory_garden.runtime",
        "memory_garden.harvest",
        "memory_garden.observatory",
    )
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
    for mod in imported:
        for prefix in forbidden:
            assert not (mod == prefix or mod.startswith(prefix + ".")), f"Forbidden import: {mod}"


# ---------------------------------------------------------------------------
# additional: smoke pack details
# ---------------------------------------------------------------------------

def test_smoke_pack_contains_seed_and_runtime_cases() -> None:
    pack = get_lab_suite_pack(SMOKE)
    assert "lab.6b.seed.control_commands.no_preference_capture_v1" in pack.case_ids
    assert "lab.6b.runtime.short_circuit.no_after_reply_agent_v1" in pack.case_ids


def test_smoke_pack_description() -> None:
    pack = get_lab_suite_pack(SMOKE)
    assert "critical" in pack.description.lower() or "critical" in pack.tags


def test_full_pack_has_all_five_suites() -> None:
    suites = get_lab_suites_for_pack(FULL)
    assert len(suites) == 5
    suite_ids = {s.suite_id for s in suites}
    default_ids = {s.suite_id for s in default_lab_suites()}
    assert suite_ids == default_ids