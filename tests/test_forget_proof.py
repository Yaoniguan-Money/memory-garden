"""Tests for Forget Proof: systematic verification of hard forget."""

import os

from memory_garden.soil.forget import execute_hard_forget
from memory_garden.soil.forget_proof import prove_forget
from memory_garden.soil.home import initialize_garden_home
from memory_garden.soil.index import reindex_garden
from memory_garden.soil.models import ForgetProofVerdict

from ._soil_test_helpers import insert_test_data, setup_garden_db


def _setup(garden_home, num_memories=3):
    setup_garden_db(garden_home)
    insert_test_data(garden_home, num_memories=num_memories)
    reindex_garden(garden_home, dry_run=False)


def test_prove_forget_all_surfaces_pass_after_hard_forget(tmp_path):
    home = initialize_garden_home(tmp_path / "garden")
    _setup(home.root, num_memories=3)
    execute_hard_forget(home.root, "mem-0001", reason="test", dry_run=False)

    proof = prove_forget(home.root, "mem-0001")
    assert proof.proven is True
    assert proof.failed == 0
    assert proof.passed >= 4  # db_row, fts, search, bundle checks
    for check in proof.checks:
        assert check.verdict != ForgetProofVerdict.failed, f"{check.surface}: {check.detail}"


def test_prove_forget_fails_when_memory_still_exists(tmp_path):
    home = initialize_garden_home(tmp_path / "garden")
    _setup(home.root, num_memories=3)
    # No forget executed

    proof = prove_forget(home.root, "mem-0001")
    assert proof.proven is False
    assert proof.failed >= 1
    db_check = [c for c in proof.checks if c.surface == "db_memory_card_row"]
    assert len(db_check) == 1
    assert db_check[0].verdict == ForgetProofVerdict.failed


def test_prove_forget_db_row_check(tmp_path):
    home = initialize_garden_home(tmp_path / "garden")
    _setup(home.root, num_memories=2)
    execute_hard_forget(home.root, "mem-0001", reason="test", dry_run=False)

    proof = prove_forget(home.root, "mem-0001", surfaces=["db_memory_card_row"])
    assert proof.proven is True
    assert proof.passed == 1


def test_prove_forget_fts_check(tmp_path):
    home = initialize_garden_home(tmp_path / "garden")
    _setup(home.root, num_memories=2)
    execute_hard_forget(home.root, "mem-0001", reason="test", dry_run=False)

    proof = prove_forget(home.root, "mem-0001", surfaces=["fts_index_entry"])
    assert proof.proven is True
    assert proof.passed == 1


def test_prove_forget_search_check(tmp_path):
    home = initialize_garden_home(tmp_path / "garden")
    _setup(home.root, num_memories=2)
    execute_hard_forget(home.root, "mem-0001", reason="test", dry_run=False)

    proof = prove_forget(home.root, "mem-0001", surfaces=["search_result"])
    assert proof.proven is True


def test_prove_forget_bundle_checks(tmp_path):
    home = initialize_garden_home(tmp_path / "garden")
    _setup(home.root, num_memories=2)
    execute_hard_forget(home.root, "mem-0001", reason="test", dry_run=False)

    proof = prove_forget(home.root, "mem-0001", surfaces=[
        "bundle_manifest", "bundle_garden_manifest", "bundle_snapshot",
    ])
    assert proof.proven is True
    assert proof.passed == 3


def test_prove_forget_no_db_skips_gracefully(tmp_path):
    home = initialize_garden_home(tmp_path / "garden")
    # No database — db/fts/search checks skip, bundle checks pass (id not in manifest)
    proof = prove_forget(home.root, "mem-0001")
    assert proof.proven is True  # bundle checks pass, no db means nothing to leak from
    assert proof.skipped >= 3  # db_row, fts, search all skipped
    assert proof.failed == 0


def test_prove_forget_does_not_create_memory_garden(tmp_path):
    home = initialize_garden_home(tmp_path / "garden")
    _setup(home.root, num_memories=1)

    cwd_mg = os.path.join(os.getcwd(), ".memory_garden")
    existed_before = os.path.exists(cwd_mg)

    prove_forget(home.root, "mem-0001")

    if not existed_before:
        assert not os.path.exists(cwd_mg)


def test_proof_models_json_roundtrip():
    from memory_garden.soil.models import ForgetProof, ForgetProofCheck, ForgetProofVerdict

    check = ForgetProofCheck(
        surface="db_memory_card_row",
        verdict=ForgetProofVerdict.passed,
        detail="ok",
        evidence={"key": "val"},
    )
    data = check.model_dump(mode="json")
    c2 = ForgetProofCheck(**data)
    assert c2.verdict == ForgetProofVerdict.passed

    proof = ForgetProof(
        memory_id="m1",
        garden_home="/tmp/x",
        checks=[check],
        passed=1,
        failed=0,
        skipped=0,
        proven=True,
    )
    data2 = proof.model_dump(mode="json")
    p2 = ForgetProof(**data2)
    assert p2.proven is True
