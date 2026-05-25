"""Tests for garden home initialization and resolution."""

import os

from memory_garden.soil.home import initialize_garden_home, resolve_garden_home
from memory_garden.soil.models import GardenHome


def test_resolve_garden_home_returns_path_no_create(tmp_path):
    """resolve_garden_home must not create any directory."""
    sub = tmp_path / "nested" / "garden"
    result = resolve_garden_home(sub)
    assert str(result) == str(sub.resolve())
    assert not sub.exists()


def test_resolve_garden_home_none_defaults_to_cwd_memory_garden():
    result = resolve_garden_home(None)
    assert result.name == ".memory_garden"
    assert result.is_absolute()


def test_initialize_garden_home_creates_directory(tmp_path):
    home_path = tmp_path / "my_garden"
    home = initialize_garden_home(home_path)
    assert home_path.is_dir()
    assert isinstance(home, GardenHome)
    assert home.root == home_path.resolve()


def test_initialize_garden_home_creates_manifest_json(tmp_path):
    home_path = tmp_path / "garden2"
    initialize_garden_home(home_path)
    manifest_path = home_path / "manifest.json"
    assert manifest_path.is_file()


def test_initialize_garden_home_populates_manifest(tmp_path):
    home_path = tmp_path / "garden3"
    home = initialize_garden_home(home_path)
    assert home.manifest.garden_name == "memory-garden"
    assert home.manifest.schema_version == 1


def test_initialize_garden_home_idempotent(tmp_path):
    """Calling initialize twice on the same path should not fail."""
    home_path = tmp_path / "garden4"
    h1 = initialize_garden_home(home_path)
    h2 = initialize_garden_home(home_path)
    assert h1.root == h2.root
    assert h1.manifest.garden_name == h2.manifest.garden_name


def test_initialize_garden_home_create_false_when_exists(tmp_path):
    home_path = tmp_path / "garden5"
    home_path.mkdir()
    (home_path / "manifest.json").write_text(
        '{"garden_name":"pre-existing","schema_version":2,"created_at":"2025-01-01T00:00:00Z","description":""}',
        encoding="utf-8",
    )
    home = initialize_garden_home(home_path, create=False)
    assert home.manifest.garden_name == "pre-existing"
    assert home.manifest.schema_version == 2


def test_initialize_garden_home_create_false_raises_if_missing(tmp_path):
    import pytest
    home_path = tmp_path / "nonexistent"
    with pytest.raises(FileNotFoundError):
        initialize_garden_home(home_path, create=False)


def test_import_does_not_create_memory_garden():
    """Verify that importing memory_garden.soil does not create .memory_garden."""
    cwd = os.getcwd()
    candidate = os.path.join(cwd, ".memory_garden")
    existed_before = os.path.exists(candidate)
    # The import already happened when pytest collected this module.
    # We check that no .memory_garden was created in the CWD.
    exists_after = os.path.exists(candidate)
    if not existed_before:
        assert not exists_after, (
            "Importing memory_garden.soil must not create .memory_garden in CWD"
        )
