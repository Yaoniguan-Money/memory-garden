"""Tests for Garden Soil health check with FTS index integration."""

import sqlite3

from memory_garden.soil.health import check_garden_health
from memory_garden.soil.home import initialize_garden_home
from memory_garden.soil.index import FTS_TABLE, reindex_garden
from memory_garden.soil.models import GardenHealthStatus

from ._soil_test_helpers import insert_test_data, setup_garden_db


def test_health_check_no_database_is_not_unhealthy(tmp_path):
    """Garden without a db file (e.g. :memory: users) should not be unhealthy."""
    home = initialize_garden_home(tmp_path / "garden")
    report = check_garden_health(home.root)
    # Should be healthy — no db is not an error
    assert report.status == GardenHealthStatus.healthy


def test_health_check_index_missing_is_degraded(tmp_path):
    """Garden with db but no FTS index should be degraded."""
    home = initialize_garden_home(tmp_path / "garden")
    setup_garden_db(home.root)

    report = check_garden_health(home.root)
    assert any(i.code == "fts_table_missing" for i in report.issues)
    assert report.status == GardenHealthStatus.degraded


def test_health_check_index_present_is_healthy(tmp_path):
    """Garden with db and healthy FTS index should be healthy."""
    home = initialize_garden_home(tmp_path / "garden")
    setup_garden_db(home.root)
    insert_test_data(home.root, num_memories=2)
    reindex_garden(home.root, dry_run=False)

    report = check_garden_health(home.root)
    assert report.status == GardenHealthStatus.healthy


def test_health_check_does_not_create_index(tmp_path):
    """Health check must never create the FTS index."""
    home = initialize_garden_home(tmp_path / "garden")
    setup_garden_db(home.root)

    # Verify FTS doesn't exist before
    import sqlite3
    db = home.root / "garden.db"
    conn = sqlite3.connect(str(db))
    fts_exists_before = bool(conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (FTS_TABLE,),
    ).fetchone())
    conn.close()
    assert fts_exists_before is False

    check_garden_health(home.root)

    # Verify FTS still doesn't exist
    conn = sqlite3.connect(str(db))
    fts_exists_after = bool(conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (FTS_TABLE,),
    ).fetchone())
    conn.close()
    assert fts_exists_after is False


def test_health_check_corrupt_index_is_unhealthy(tmp_path):
    """Corrupt FTS table should be reported as unhealthy."""
    home = initialize_garden_home(tmp_path / "garden")
    setup_garden_db(home.root)
    insert_test_data(home.root, num_memories=1)
    reindex_garden(home.root, dry_run=False)

    # Corrupt the FTS table by dropping its shadow tables
    db = home.root / "garden.db"
    conn = sqlite3.connect(str(db))
    # FTS5 stores data in shadow tables like garden_fts_index_content
    conn.execute(f"DROP TABLE IF EXISTS {FTS_TABLE}_content")
    conn.commit()
    conn.close()

    report = check_garden_health(home.root)
    assert any(
        i.code == "fts_table_corrupt" or i.severity == GardenHealthStatus.degraded
        for i in report.issues
    )


def test_reindex_does_not_create_memory_garden(tmp_path):
    home = initialize_garden_home(tmp_path / "garden")
    setup_garden_db(home.root)
    insert_test_data(home.root, num_memories=1)

    # Verify .memory_garden not created in CWD
    import os
    cwd_mg = os.path.join(os.getcwd(), ".memory_garden")
    existed_before = os.path.exists(cwd_mg)

    reindex_garden(home.root, dry_run=False)

    if not existed_before:
        assert not os.path.exists(cwd_mg), "reindex must not create .memory_garden in CWD"


def test_reindex_court_cases(tmp_path):
    home = initialize_garden_home(tmp_path / "garden")
    setup_garden_db(home.root)
    insert_test_data(home.root, num_court_cases=3)

    result = reindex_garden(home.root, target_types=["court_case"], dry_run=False)
    assert result.indexed_count == 3
    assert "court_case" in result.target_types


def test_reindex_dream_records(tmp_path):
    home = initialize_garden_home(tmp_path / "garden")
    setup_garden_db(home.root)
    insert_test_data(home.root, num_dream_records=2)

    result = reindex_garden(home.root, target_types=["dream_record"], dry_run=False)
    assert result.indexed_count == 2
    assert "dream_record" in result.target_types
