"""Tests for manifest save/load."""

import json

from memory_garden.soil.manifest import load_manifest, save_manifest
from memory_garden.soil.models import GardenManifest


def test_save_and_load_manifest(tmp_path):
    home = tmp_path / "garden"
    home.mkdir()
    m = GardenManifest(garden_name="test-save", schema_version=5, description="desc")
    save_manifest(home, m)

    loaded = load_manifest(home)
    assert loaded.garden_name == "test-save"
    assert loaded.schema_version == 5
    assert loaded.description == "desc"


def test_load_manifest_missing_raises(tmp_path):
    import pytest

    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(FileNotFoundError, match="manifest.json not found"):
        load_manifest(empty)


def test_save_manifest_stable_json_output(tmp_path):
    home = tmp_path / "garden"
    home.mkdir()
    m = GardenManifest(garden_name="stable", schema_version=1, description="")

    save_manifest(home, m)
    raw1 = (home / "manifest.json").read_text(encoding="utf-8")

    # Write again with identical data — output should be identical
    save_manifest(home, m)
    raw2 = (home / "manifest.json").read_text(encoding="utf-8")

    assert raw1 == raw2


def test_save_manifest_keys_are_sorted(tmp_path):
    home = tmp_path / "garden"
    home.mkdir()
    m = GardenManifest(garden_name="sorted")
    save_manifest(home, m)

    raw = (home / "manifest.json").read_text(encoding="utf-8")
    data = json.loads(raw)

    keys = list(data.keys())
    assert keys == sorted(keys), f"manifest keys are not sorted: {keys}"


def test_load_manifest_unknown_fields(tmp_path):
    """Extra fields in manifest.json should be ignored by Pydantic."""
    home = tmp_path / "garden"
    home.mkdir()
    (home / "manifest.json").write_text(
        json.dumps({
            "garden_name": "future",
            "schema_version": 1,
            "created_at": "2025-01-01T00:00:00Z",
            "description": "",
            "future_field_that_does_not_exist_yet": "some_value",
        }),
        encoding="utf-8",
    )
    loaded = load_manifest(home)
    assert loaded.garden_name == "future"
    assert loaded.schema_version == 1
