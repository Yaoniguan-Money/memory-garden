"""Stage 14: 内容级 hard forget proof 测试。"""

from __future__ import annotations

import json
import sqlite3

from memory_garden.core.models import MemoryCard, MemoryType, SensitivityLevel
from memory_garden.core.growth.lifecycle import MemoryLifecycle
from memory_garden.soil.content_probes import (
    build_content_probes_from_card,
    probe_safe_dump,
    proof_json_contains_probe_plaintext,
    redact_token,
)
from memory_garden.soil.forget import execute_hard_forget, plan_hard_forget
from memory_garden.soil.forget_proof import prove_forget
from memory_garden.soil.home import initialize_garden_home
from memory_garden.soil.index import reindex_garden
from memory_garden.soil.models import ForgetProofVerdict

from ._soil_test_helpers import insert_test_data, setup_garden_db

_SECRET = "UNIQUE_SECRET_TOKEN_XYZ"


def _card() -> MemoryCard:
    return MemoryCard(
        id="mem-secret-001",
        title=f"Secret title {_SECRET}",
        essence=f"Sensitive essence contains {_SECRET} for proof testing",
        memory_type=MemoryType.preference,
        lifecycle=MemoryLifecycle.bloom,
        tags=["secret", "proof"],
        fragrance="fragrance",
        thorns="none",
        sensitivity=SensitivityLevel.none,
    )


def test_build_content_probes_safe_dump_excludes_match_tokens():
    probes = build_content_probes_from_card(_card())
    safe = probe_safe_dump(probes)
    assert "match_tokens" not in safe
    assert probes.match_tokens
    assert _SECRET.casefold() not in json.dumps(safe, ensure_ascii=False).casefold()


def test_redact_token_masks_plaintext():
    assert "***" in redact_token("abcdef")


def test_proof_json_redaction_detects_plaintext_leaks():
    probes = build_content_probes_from_card(_card())
    payload = json.dumps({"detail": probes.match_tokens[0]}, ensure_ascii=False)
    assert proof_json_contains_probe_plaintext(payload, probes)


def test_content_proof_passes_after_hard_forget(tmp_path):
    home = initialize_garden_home(tmp_path / "garden")
    setup_garden_db(home.root)
    card = _card()
    db_path = home.root / "garden.db"
    conn = sqlite3.connect(db_path)
    payload = json.dumps(card.model_dump(mode="json"), ensure_ascii=False)
    conn.execute(
        "INSERT INTO memory_cards (id, created_at, lifecycle, memory_type, sensitivity, updated_at, payload) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (card.id, "2025-01-01T00:00:00Z", "bloom", "preference", "none", "2025-01-01T00:00:00Z", payload),
    )
    conn.commit()
    conn.close()
    reindex_garden(home.root, dry_run=False)

    probes = build_content_probes_from_card(card)
    execute_hard_forget(home.root, card.id, reason="test", dry_run=False, cascade=True)
    proof = prove_forget(home.root, card.id, content_probes=probes, cascade=True)
    assert proof.proof_level == "content"
    assert proof.proven is True
    assert proof.failed == 0
    assert proof.content_probe_fingerprint


def test_db_content_scan_fails_when_payload_leaks(tmp_path):
    home = initialize_garden_home(tmp_path / "garden")
    setup_garden_db(home.root)
    card = _card()
    probes = build_content_probes_from_card(card)
    db_path = home.root / "garden.db"
    conn = sqlite3.connect(db_path)
    payload = json.dumps(card.model_dump(mode="json"), ensure_ascii=False)
    conn.execute(
        "INSERT INTO memory_cards (id, created_at, lifecycle, memory_type, sensitivity, updated_at, payload) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (card.id, "2025-01-01T00:00:00Z", "bloom", "preference", "none", "2025-01-01T00:00:00Z", payload),
    )
    conn.commit()
    conn.close()

    proof = prove_forget(home.root, card.id, content_probes=probes, surfaces=["db_content_scan"])
    assert proof.proven is False
    assert proof.checks[0].verdict == ForgetProofVerdict.failed


def test_cascade_false_lineage_residual_is_skipped_not_failed(tmp_path):
    home = initialize_garden_home(tmp_path / "garden")
    setup_garden_db(home.root)
    card = _card()
    probes = build_content_probes_from_card(card)
    db_path = home.root / "garden.db"
    conn = sqlite3.connect(db_path)
    payload = json.dumps(card.model_dump(mode="json"), ensure_ascii=False)
    conn.execute(
        "INSERT INTO memory_cards (id, created_at, lifecycle, memory_type, sensitivity, updated_at, payload) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (card.id, "2025-01-01T00:00:00Z", "bloom", "preference", "none", "2025-01-01T00:00:00Z", payload),
    )
    seed_payload = json.dumps(
        {"id": "seed-x", "content": card.essence, "source_memory_id": card.id},
        ensure_ascii=False,
    )
    conn.execute(
        "INSERT INTO seeds (id, created_at, status, signal_type, payload) VALUES (?, ?, ?, ?, ?)",
        ("seed-x", "2025-02-01T00:00:00Z", "pending", "preference", seed_payload),
    )
    conn.commit()
    conn.close()

    execute_hard_forget(home.root, card.id, reason="test", cascade=False)
    proof = prove_forget(
        home.root,
        card.id,
        content_probes=probes,
        cascade=False,
        surfaces=["db_memory_card_row", "db_content_scan"],
    )
    db_check = next(c for c in proof.checks if c.surface == "db_content_scan")
    assert db_check.verdict == ForgetProofVerdict.skipped
    assert proof.proven is True


def test_plan_hard_forget_includes_content_probes(tmp_path):
    home = initialize_garden_home(tmp_path / "garden")
    setup_garden_db(home.root)
    insert_test_data(home.root, num_memories=1)
    plan = plan_hard_forget(home.root, "mem-0001")
    assert plan.content_probes is not None
    assert plan.content_probes.token_probe_count > 0


def test_execute_hard_forget_records_content_probe_fingerprint(tmp_path):
    home = initialize_garden_home(tmp_path / "garden")
    setup_garden_db(home.root)
    insert_test_data(home.root, num_memories=1)
    plan = plan_hard_forget(home.root, "mem-0001")
    assert plan.content_probes is not None

    result = execute_hard_forget(home.root, "mem-0001", reason="test", dry_run=False, cascade=True)
    assert result.content_probe_fingerprint
    assert len(result.content_probe_fingerprint) == 64
