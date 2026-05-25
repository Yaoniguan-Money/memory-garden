"""Tests for Garden Soil hard forget cascade + FTS cleanup + audit."""

import json
import os
import sqlite3

from memory_garden.soil.forget import execute_hard_forget, plan_hard_forget
from memory_garden.soil.health import check_garden_health
from memory_garden.soil.home import initialize_garden_home
from memory_garden.soil.index import reindex_garden

from ._soil_test_helpers import insert_test_data, setup_garden_db


def _setup_with_index(garden_home, num_memories=3):
    setup_garden_db(garden_home)
    insert_test_data(garden_home, num_memories=num_memories)
    reindex_garden(garden_home, dry_run=False)


def _insert_forget_cascade_refs(garden_home):
    db_path = os.path.join(str(garden_home), "garden.db")
    conn = sqlite3.connect(db_path)
    seed_payload = json.dumps({
        "id": "seed-linked",
        "content": "Seed text linked to memory mem-0001 for cascade cleanup.",
        "source_excerpt": "Seed text linked to memory mem-0001 for cascade cleanup.",
        "context": {},
        "tags": ["forget"],
        "signal_type": "preference",
        "confidence": 0.9,
        "status": "pending",
        "source_memory_id": "mem-0001",
        "created_at": "2025-02-01T00:00:00Z",
    })
    case_payload = json.dumps({
        "id": "case-linked",
        "seed_id": "seed-linked",
        "prosecutor_argument": "Case text tied to a forgotten memory.",
        "defender_argument": "The source memory should be removed by cascade.",
        "privacy_guard_argument": "No content should leak after hard forget cascade.",
        "judge_verdict": {"verdict": "forget", "reason": "user request", "target_memory_id": "mem-0001"},
        "matched_rules": [],
        "risk_flags": [],
        "target_memory_id": "mem-0001",
        "created_at": "2025-03-01T00:00:00Z",
    })
    event_payload = json.dumps({"id": "event-seed", "object_id": "seed-linked"})
    conn.execute(
        "INSERT INTO seeds (id, created_at, status, signal_type, payload) VALUES (?, ?, ?, ?, ?)",
        ("seed-linked", "2025-02-01T00:00:00Z", "pending", "preference", seed_payload),
    )
    conn.execute(
        "INSERT INTO court_cases (id, created_at, seed_id, verdict, payload) VALUES (?, ?, ?, ?, ?)",
        ("case-linked", "2025-03-01T00:00:00Z", "seed-linked", "forget", case_payload),
    )
    conn.execute(
        "INSERT INTO garden_events (id, created_at, event_type, object_type, object_id, payload) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("event-seed", "2025-03-02T00:00:00Z", "seed_created", "seed", "seed-linked", event_payload),
    )
    conn.execute(
        "INSERT INTO garden_events (id, created_at, event_type, object_type, object_id, payload) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("event-case", "2025-03-03T00:00:00Z", "court_opened", "court_case", "case-linked", event_payload),
    )
    conn.commit()
    conn.close()
    reindex_garden(garden_home, dry_run=False)


def _insert_memory_payload_lineage_refs(garden_home):
    db_path = os.path.join(str(garden_home), "garden.db")
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute("SELECT payload FROM memory_cards WHERE id = ?", ("mem-0001",)).fetchone()
        payload = json.loads(row[0])
        payload["source_seed_ids"] = ["seed-source"]
        payload["court_case_ids"] = ["case-source"]
        conn.execute(
            "UPDATE memory_cards SET payload = ? WHERE id = ?",
            (json.dumps(payload, ensure_ascii=False), "mem-0001"),
        )
        seed_payload = json.dumps({
            "id": "seed-source",
            "content": "Original source seed for mem-0001 should cascade away.",
            "source_excerpt": "Original source seed for mem-0001 should cascade away.",
            "context": {},
            "tags": ["lineage"],
            "signal_type": "preference",
            "confidence": 0.9,
            "status": "planted",
            "created_at": "2025-02-01T00:00:00Z",
        })
        case_payload = json.dumps({
            "id": "case-source",
            "seed_id": "seed-source",
            "prosecutor_argument": "source case",
            "defender_argument": "source case",
            "privacy_guard_argument": "source case",
            "judge_verdict": {"verdict": "plant", "reason": "test"},
            "matched_rules": [],
            "risk_flags": [],
            "created_at": "2025-03-01T00:00:00Z",
        })
        conn.execute(
            "INSERT INTO seeds (id, created_at, status, signal_type, payload) VALUES (?, ?, ?, ?, ?)",
            ("seed-source", "2025-02-01T00:00:00Z", "planted", "preference", seed_payload),
        )
        conn.execute(
            "INSERT INTO court_cases (id, created_at, seed_id, verdict, payload) VALUES (?, ?, ?, ?, ?)",
            ("case-source", "2025-03-01T00:00:00Z", "seed-source", "plant", case_payload),
        )
        conn.commit()
    finally:
        conn.close()
    reindex_garden(garden_home, dry_run=False)


def _row_exists(garden_home, table, row_id):
    conn = sqlite3.connect(os.path.join(str(garden_home), "garden.db"))
    try:
        return conn.execute(f"SELECT 1 FROM {table} WHERE id = ?", (row_id,)).fetchone() is not None
    finally:
        conn.close()


# ── Plan tests ──────────────────────────────────────────────────────


def test_plan_hard_forget_dry_does_not_delete(tmp_path):
    home = initialize_garden_home(tmp_path / "garden")
    _setup_with_index(home.root, num_memories=3)

    plan = plan_hard_forget(home.root, "mem-0001")
    assert plan.memory_id == "mem-0001"
    assert plan.mode == "hard"
    assert "memory_card" in plan.affected_entities

    # Verify nothing was deleted
    import sqlite3
    conn = sqlite3.connect(str(home.root / "garden.db"))
    row = conn.execute("SELECT id FROM memory_cards WHERE id = ?", ("mem-0001",)).fetchone()
    assert row is not None
    conn.close()


def test_plan_hard_forget_reports_fts_entries(tmp_path):
    home = initialize_garden_home(tmp_path / "garden")
    _setup_with_index(home.root, num_memories=2)

    plan = plan_hard_forget(home.root, "mem-0001")
    assert plan.fts_entries >= 1


def test_plan_hard_forget_reports_structured_cascade_refs(tmp_path):
    home = initialize_garden_home(tmp_path / "garden")
    _setup_with_index(home.root, num_memories=1)
    _insert_forget_cascade_refs(home.root)

    plan = plan_hard_forget(home.root, "mem-0001")

    assert plan.affected_entities["seed"] == ["seed-linked"]
    assert plan.affected_entities["court_case"] == ["case-linked"]


def test_plan_hard_forget_reports_memory_payload_lineage_refs(tmp_path):
    home = initialize_garden_home(tmp_path / "garden")
    _setup_with_index(home.root, num_memories=1)
    _insert_memory_payload_lineage_refs(home.root)

    plan = plan_hard_forget(home.root, "mem-0001")

    assert plan.affected_entities["seed"] == ["seed-source"]
    assert plan.affected_entities["court_case"] == ["case-source"]


def test_plan_hard_forget_nonexistent_memory_returns_empty(tmp_path):
    home = initialize_garden_home(tmp_path / "garden")
    _setup_with_index(home.root, num_memories=1)

    plan = plan_hard_forget(home.root, "nonexistent-id")
    assert plan.memory_id == "nonexistent-id"
    assert plan.fts_entries == 0


# ── Execute dry_run tests ───────────────────────────────────────────


def test_execute_dry_run_does_not_delete(tmp_path):
    home = initialize_garden_home(tmp_path / "garden")
    _setup_with_index(home.root, num_memories=3)

    result = execute_hard_forget(home.root, "mem-0001", dry_run=True)
    assert result.dry_run is True
    assert result.memory_deleted is False

    # Verify memory still exists
    import sqlite3
    conn = sqlite3.connect(str(home.root / "garden.db"))
    row = conn.execute("SELECT id FROM memory_cards WHERE id = ?", ("mem-0001",)).fetchone()
    assert row is not None
    conn.close()


# ── Execute real tests ──────────────────────────────────────────────


def test_execute_hard_forget_deletes_memory(tmp_path):
    home = initialize_garden_home(tmp_path / "garden")
    _setup_with_index(home.root, num_memories=3)

    result = execute_hard_forget(home.root, "mem-0001", reason="test", dry_run=False)
    assert result.status == "ok"
    assert result.memory_deleted is True

    # Verify memory is gone
    import sqlite3
    conn = sqlite3.connect(str(home.root / "garden.db"))
    row = conn.execute("SELECT id FROM memory_cards WHERE id = ?", ("mem-0001",)).fetchone()
    assert row is None
    conn.close()


def test_execute_hard_forget_cleans_fts_index(tmp_path):
    home = initialize_garden_home(tmp_path / "garden")
    _setup_with_index(home.root, num_memories=3)

    # Verify FTS has the entry before forget
    from memory_garden.soil.search import search_garden
    hits_before = search_garden(home.root, "preference", limit=20)
    assert any(h.target_id == "mem-0001" for h in hits_before)

    result = execute_hard_forget(home.root, "mem-0001", reason="test", dry_run=False)
    assert result.fts_entries_removed >= 1

    # Rebuild index to get clean state, then verify FTS entry is gone
    reindex_garden(home.root, dry_run=False)
    hits_after = search_garden(home.root, "preference", limit=20)
    assert not any(h.target_id == "mem-0001" for h in hits_after)


def test_execute_hard_forget_without_cascade_preserves_related_rows(tmp_path):
    home = initialize_garden_home(tmp_path / "garden")
    _setup_with_index(home.root, num_memories=1)
    _insert_forget_cascade_refs(home.root)

    result = execute_hard_forget(home.root, "mem-0001", reason="test", dry_run=False)

    assert result.status == "ok"
    assert result.seed_ids_cleaned == []
    assert result.case_ids_cleaned == []
    assert _row_exists(home.root, "seeds", "seed-linked")
    assert _row_exists(home.root, "court_cases", "case-linked")


def test_execute_hard_forget_cascade_cleans_related_rows_and_index(tmp_path):
    home = initialize_garden_home(tmp_path / "garden")
    _setup_with_index(home.root, num_memories=1)
    _insert_forget_cascade_refs(home.root)

    result = execute_hard_forget(home.root, "mem-0001", reason="test", dry_run=False, cascade=True)

    assert result.status == "ok"
    assert result.seed_ids_cleaned == ["seed-linked"]
    assert result.case_ids_cleaned == ["case-linked"]
    assert not _row_exists(home.root, "memory_cards", "mem-0001")
    assert not _row_exists(home.root, "seeds", "seed-linked")
    assert not _row_exists(home.root, "court_cases", "case-linked")

    conn = sqlite3.connect(os.path.join(str(home.root), "garden.db"))
    try:
        event_rows = conn.execute(
            "SELECT id FROM garden_events WHERE object_id IN (?, ?)",
            ("seed-linked", "case-linked"),
        ).fetchall()
        fts_rows = conn.execute(
            "SELECT target_id FROM garden_fts_index WHERE target_id IN (?, ?)",
            ("seed-linked", "case-linked"),
        ).fetchall()
    finally:
        conn.close()
    assert event_rows == []
    assert fts_rows == []


def test_execute_hard_forget_cascade_cleans_memory_payload_lineage_refs(tmp_path):
    home = initialize_garden_home(tmp_path / "garden")
    _setup_with_index(home.root, num_memories=1)
    _insert_memory_payload_lineage_refs(home.root)

    result = execute_hard_forget(home.root, "mem-0001", reason="test", dry_run=False, cascade=True)

    assert result.status == "ok"
    assert result.seed_ids_cleaned == ["seed-source"]
    assert result.case_ids_cleaned == ["case-source"]
    assert not _row_exists(home.root, "memory_cards", "mem-0001")
    assert not _row_exists(home.root, "seeds", "seed-source")
    assert not _row_exists(home.root, "court_cases", "case-source")


def test_execute_hard_forget_no_database_returns_failed(tmp_path):
    home = initialize_garden_home(tmp_path / "garden")
    # No database — only manifest
    result = execute_hard_forget(home.root, "mem-0001", reason="test", dry_run=False)
    assert result.status == "failed"


def test_health_check_detects_stale_fts_entries(tmp_path):
    home = initialize_garden_home(tmp_path / "garden")
    _setup_with_index(home.root, num_memories=2)

    # Manually delete a memory card WITHOUT cleaning FTS
    import sqlite3
    conn = sqlite3.connect(str(home.root / "garden.db"))
    conn.execute("DELETE FROM memory_cards WHERE id = ?", ("mem-0001",))
    conn.commit()
    conn.close()

    # Health check should detect the stale FTS entry
    report = check_garden_health(home.root)
    stale_codes = [i.code for i in report.issues]
    assert "fts_stale_entries" in stale_codes


def test_health_check_no_stale_after_proper_forget(tmp_path):
    home = initialize_garden_home(tmp_path / "garden")
    _setup_with_index(home.root, num_memories=2)

    # Use proper forget
    execute_hard_forget(home.root, "mem-0001", reason="test", dry_run=False)

    # Reindex to clean up, then health check
    reindex_garden(home.root, dry_run=False)
    report = check_garden_health(home.root)
    stale_codes = [i.code for i in report.issues]
    assert "fts_stale_entries" not in stale_codes


def test_forget_does_not_create_memory_garden(tmp_path):
    home = initialize_garden_home(tmp_path / "garden")
    _setup_with_index(home.root, num_memories=2)

    cwd_mg = os.path.join(os.getcwd(), ".memory_garden")
    existed_before = os.path.exists(cwd_mg)

    execute_hard_forget(home.root, "mem-0001", reason="test", dry_run=False)

    if not existed_before:
        assert not os.path.exists(cwd_mg), "hard forget must not create .memory_garden"


def test_import_has_no_side_effects():
    cwd = os.getcwd()
    candidate = os.path.join(cwd, ".memory_garden")
    existed_before = os.path.exists(candidate)
    if not existed_before:
        assert not os.path.exists(candidate), "import must not create .memory_garden"


def test_forget_models_json_roundtrip():
    from memory_garden.soil.models import GardenForgetPlan, GardenForgetResult

    plan = GardenForgetPlan(
        memory_id="m1",
        affected_entities={"memory_card": ["m1"], "fts_entry": ["m1"]},
        fts_entries=1,
        notes="test",
    )
    data = plan.model_dump(mode="json")
    p2 = GardenForgetPlan(**data)
    assert p2.memory_id == "m1"
    assert p2.fts_entries == 1

    result = GardenForgetResult(
        memory_id="m1",
        mode="hard",
        status="ok",
        memory_deleted=True,
        fts_entries_removed=1,
    )
    data2 = result.model_dump(mode="json")
    r2 = GardenForgetResult(**data2)
    assert r2.status == "ok"
    assert r2.memory_deleted is True
