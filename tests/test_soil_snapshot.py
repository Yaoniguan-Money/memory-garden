"""Tests for garden snapshot creation."""

from memory_garden.soil.home import initialize_garden_home
from memory_garden.soil.snapshot import create_garden_snapshot


def test_snapshot_includes_manifest_summary(tmp_path):
    home = initialize_garden_home(tmp_path / "garden")
    snap = create_garden_snapshot(home.root)
    assert snap.garden_home == str(home.root)
    assert snap.manifest_summary["garden_name"] == "memory-garden"
    assert snap.manifest_summary["schema_version"] == 1
    assert "created_at" in snap.manifest_summary


def test_snapshot_with_notes(tmp_path):
    home = initialize_garden_home(tmp_path / "garden")
    snap = create_garden_snapshot(home.root, notes="pre-migration snapshot")
    assert snap.notes == "pre-migration snapshot"


def test_snapshot_without_manifest(tmp_path):
    """Snapshot should handle missing manifest gracefully."""
    empty = tmp_path / "empty_garden"
    empty.mkdir()
    snap = create_garden_snapshot(empty, include_manifest=True)
    assert snap.garden_home == str(empty)
    assert snap.manifest_summary == {}


def test_snapshot_explicit_no_manifest(tmp_path):
    home = initialize_garden_home(tmp_path / "garden")
    snap = create_garden_snapshot(home.root, include_manifest=False)
    assert snap.garden_home == str(home.root)
    assert snap.manifest_summary == {}


def test_snapshot_json_serializable(tmp_path):
    home = initialize_garden_home(tmp_path / "garden")
    snap = create_garden_snapshot(home.root)
    data = snap.model_dump(mode="json")
    assert isinstance(data, dict)
    assert "garden_home" in data
    assert "manifest_summary" in data
