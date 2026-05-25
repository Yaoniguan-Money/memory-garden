"""Tests for Garden Soil FTS5 index: reindex and index check."""

import os

from memory_garden.soil.index import check_garden_index, reindex_garden
from memory_garden.soil.home import initialize_garden_home

from ._soil_test_helpers import insert_test_data, setup_garden_db


def test_import_has_no_side_effects():
    """Importing soil must not create .memory_garden or index files."""
    cwd = os.getcwd()
    candidate = os.path.join(cwd, ".memory_garden")
    existed_before = os.path.exists(candidate)
    if not existed_before:
        assert not os.path.exists(candidate), "import must not create .memory_garden"


def test_check_index_missing_when_no_database(tmp_path):
    home = initialize_garden_home(tmp_path / "garden")
    status = check_garden_index(home.root)
    assert status.exists is False
    assert status.healthy is False
    assert any(i.code == "database_missing" for i in status.issues)


def test_check_index_missing_when_no_fts(tmp_path):
    home = initialize_garden_home(tmp_path / "garden")
    setup_garden_db(home.root)
    status = check_garden_index(home.root)
    assert status.exists is False
    assert status.healthy is False
    assert any(i.code == "fts_table_missing" for i in status.issues)


def test_reindex_dry_run_does_not_create_fts(tmp_path):
    home = initialize_garden_home(tmp_path / "garden")
    setup_garden_db(home.root)
    insert_test_data(home.root, num_memories=3)

    result = reindex_garden(home.root, dry_run=True)
    assert result.dry_run is True
    assert result.indexed_count == 3

    # FTS table must NOT exist
    status = check_garden_index(home.root)
    assert status.exists is False


def test_reindex_creates_fts_table(tmp_path):
    home = initialize_garden_home(tmp_path / "garden")
    setup_garden_db(home.root)
    insert_test_data(home.root, num_memories=3)

    result = reindex_garden(home.root, dry_run=False)
    assert result.dry_run is False
    assert result.status == "ok"
    assert result.indexed_count >= 3
    assert "memory_card" in result.target_types

    # FTS table must now exist
    status = check_garden_index(home.root)
    assert status.exists is True
    assert status.healthy is True
    assert status.indexed_count >= 3


def test_reindex_indexes_seeds(tmp_path):
    home = initialize_garden_home(tmp_path / "garden")
    setup_garden_db(home.root)
    insert_test_data(home.root, num_seeds=5)

    result = reindex_garden(home.root, target_types=["seed"], dry_run=False)
    assert result.dry_run is False
    assert result.indexed_count == 5
    assert "seed" in result.target_types


def test_reindex_target_type_filter(tmp_path):
    home = initialize_garden_home(tmp_path / "garden")
    setup_garden_db(home.root)
    insert_test_data(home.root, num_memories=3, num_seeds=2)

    result = reindex_garden(home.root, target_types=["memory_card"], dry_run=False)
    assert result.indexed_count == 3
    assert result.target_types == ["memory_card"]


def test_reindex_rebuilds_existing_index(tmp_path):
    home = initialize_garden_home(tmp_path / "garden")
    setup_garden_db(home.root)
    insert_test_data(home.root, num_memories=2)

    reindex_garden(home.root, dry_run=False)
    insert_test_data(home.root, num_memories=1, start_id_offset=10)

    result = reindex_garden(home.root, dry_run=False)
    assert result.indexed_count == 3


def test_reindex_no_database(tmp_path):
    home = initialize_garden_home(tmp_path / "garden")
    # No database created
    result = reindex_garden(home.root)
    assert result.status == "failed"
    assert any(i.code == "database_missing" for i in result.issues)


def test_reindex_models_json_roundtrip():
    from memory_garden.soil.models import (
        GardenIndexIssue,
        GardenIndexStatus,
        GardenReindexResult,
    )

    issue = GardenIndexIssue(code="TEST", message="msg")
    data = issue.model_dump(mode="json")
    i2 = GardenIndexIssue(**data)
    assert i2.code == "TEST"

    status = GardenIndexStatus(exists=True, healthy=True, indexed_count=42, target_types=["a"])
    data2 = status.model_dump(mode="json")
    s2 = GardenIndexStatus(**data2)
    assert s2.indexed_count == 42

    result = GardenReindexResult(status="ok", indexed_count=10)
    data3 = result.model_dump(mode="json")
    r2 = GardenReindexResult(**data3)
    assert r2.indexed_count == 10
