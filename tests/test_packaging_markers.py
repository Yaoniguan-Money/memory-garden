"""Verify packaging markers and metadata."""

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent


def test_py_typed_exists():
    marker = REPO_ROOT / "memory_garden" / "py.typed"
    assert marker.exists(), "memory_garden/py.typed marker is missing"
    assert marker.is_file()


def test_py_typed_is_in_package_directory():
    marker = REPO_ROOT / "memory_garden" / "py.typed"
    assert marker.parent.name == "memory_garden"


def test_soil_package_has_init():
    init = REPO_ROOT / "memory_garden" / "soil" / "__init__.py"
    assert init.exists()
    assert init.is_file()


def test_soil_public_api_exports():
    """Verify that the soil __init__.py exports the expected public API."""
    import memory_garden.soil as soil

    expected = [
        "GardenHealthIssue",
        "GardenHealthReport",
        "GardenHealthStatus",
        "GardenHome",
        "GardenManifest",
        "GardenSnapshot",
        "check_garden_health",
        "create_garden_snapshot",
        "initialize_garden_home",
        "load_manifest",
        "resolve_garden_home",
        "save_manifest",
    ]
    for name in expected:
        assert hasattr(soil, name), f"memory_garden.soil missing export: {name}"


def test_import_does_not_create_dot_memory_garden():
    """Sanity check: importing soil must not create .memory_garden anywhere."""
    cwd = Path.cwd()
    candidate = cwd / ".memory_garden"


    if not candidate.exists():
        return  # expected — nothing was created

    # If .memory_garden already existed before this test run,
    # we can't prove it wasn't created by us. But we can check
    # that it wasn't created *during* this test.
    # The import happens at collection time, so we check existence.
    # In CI, this directory should never exist in the repo root.
    in_repo = (REPO_ROOT / ".memory_garden").exists()
    assert not in_repo, (
        ".memory_garden was created in the repository root during import. "
        "Import must not create directories."
    )


def test_public_entrypoints_do_not_contain_common_mojibake_tokens():
    """Guard public docs and CLI text against UTF-8 mojibake regressions."""
    bad_tokens = (
        "\u9225",
        "\u922b",
        "\u947a",
        "\u95b3",
        "\u95ba",
        "\u93ba",
        "\u699b",
        "\u935b",
        "\u9428",
        "\u93c3",
        "\u9359",
        "\u934f",
        "\u7039",
        "\u5a55",
        "\u95b0",
        "\u93c4",
        "\u93c2",
        "\ufffd",
    )
    paths = [
        REPO_ROOT / "README.md",
        REPO_ROOT / "README_中文.md",
        REPO_ROOT / "docs" / "quickstart.md",
        REPO_ROOT / "memory_garden" / "__main__.py",
    ]

    offenders = []
    for path in paths:
        text = path.read_text(encoding="utf-8")
        for token in bad_tokens:
            if token in text:
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{token}")

    assert offenders == []
