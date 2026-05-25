"""Garden Home: resolve and initialize the local garden directory."""

from __future__ import annotations

from pathlib import Path

from memory_garden.soil.manifest import load_manifest, save_manifest
from memory_garden.soil.models import GardenHome, GardenManifest


def resolve_garden_home(base_path: str | Path | None = None) -> Path:
    """Return the path that *would* be used as the garden home directory.

    This function does **not** create any directories or files.
    Use ``initialize_garden_home()`` to perform the actual initialization.
    """
    if base_path is not None:
        return Path(base_path).resolve()
    return Path.cwd().resolve() / ".memory_garden"


def initialize_garden_home(
    base_path: str | Path,
    *,
    create: bool = True,
) -> GardenHome:
    """Create (if *create* is True) and initialize a garden home directory.

    Writes ``manifest.json`` into the garden home root.
    Returns a fully populated ``GardenHome`` model.

    Raises ``FileNotFoundError`` if *create* is False and the directory
    does not already exist.
    """
    root = Path(base_path).resolve()

    if create:
        root.mkdir(parents=True, exist_ok=True)

    if not root.is_dir():
        raise FileNotFoundError(f"Garden home directory does not exist: {root}")

    manifest_path = root / "manifest.json"

    if manifest_path.exists():
        manifest = load_manifest(root)
    else:
        manifest = GardenManifest()
        if create:
            save_manifest(root, manifest)

    return GardenHome(root=root, manifest=manifest)
