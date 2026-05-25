"""Manifest read/write for garden home metadata."""

from __future__ import annotations

import json
from pathlib import Path

from memory_garden.soil.models import GardenManifest


def load_manifest(garden_home: str | Path) -> GardenManifest:
    """Load and parse the ``manifest.json`` from a garden home directory."""
    manifest_path = Path(garden_home) / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"manifest.json not found in {garden_home}")
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    return GardenManifest(**data)


def save_manifest(garden_home: str | Path, manifest: GardenManifest) -> None:
    """Serialize *manifest* to ``manifest.json`` inside *garden_home*.

    The output is stable: ``indent=2``, ``sort_keys=True``, UTF-8.
    """
    manifest_path = Path(garden_home) / "manifest.json"
    payload = manifest.model_dump(mode="json")
    manifest_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )
