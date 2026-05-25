"""Garden Bundle: export and import a garden home as a directory bundle.

This is a **skeleton** for v0.10.1.  It copies metadata files only —
it does **not** copy the SQLite database, large payloads, or unknown
files.  Real portability across machines is deferred to a future version.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from memory_garden.soil.manifest import load_manifest
from memory_garden.soil.models import (
    GardenBundleExportResult,
    GardenBundleImportResult,
    GardenBundleManifest,
)
from memory_garden.soil.snapshot import create_garden_snapshot

_BUNDLE_FILES = ("bundle_manifest.json", "garden_manifest.json", "snapshot.json")
_MAX_BUNDLE_FILE_BYTES = 512 * 1024


def export_garden_bundle(
    garden_home: str | Path,
    bundle_path: str | Path,
    *,
    notes: str = "",
) -> GardenBundleExportResult:
    """Export garden metadata to a directory bundle.

    Creates *bundle_path* as a directory containing:

    * ``bundle_manifest.json`` — bundle-level metadata
    * ``garden_manifest.json`` — copy of the source ``manifest.json``
    * ``snapshot.json`` — point-in-time metadata snapshot

    The source garden is **never** modified.
    The SQLite database is **not** copied.
    """
    source = Path(garden_home).resolve()
    dest = Path(bundle_path).resolve()

    dest.mkdir(parents=True, exist_ok=True)

    manifest = load_manifest(source)
    snapshot = create_garden_snapshot(source, notes=notes)

    bundle_manifest = GardenBundleManifest(
        garden_name=manifest.garden_name,
        source_garden_home=str(source),
        schema_version=manifest.schema_version,
        notes=notes,
    )

    files_written: list[str] = []

    # bundle_manifest.json
    _write_json(dest / "bundle_manifest.json", bundle_manifest.model_dump(mode="json"))
    files_written.append("bundle_manifest.json")

    # garden_manifest.json
    _write_json(dest / "garden_manifest.json", manifest.model_dump(mode="json"))
    files_written.append("garden_manifest.json")

    # snapshot.json
    _write_json(dest / "snapshot.json", snapshot.model_dump(mode="json"))
    files_written.append("snapshot.json")

    return GardenBundleExportResult(
        bundle_path=str(dest),
        manifest=bundle_manifest,
        files_written=files_written,
    )


def import_garden_bundle(
    bundle_path: str | Path,
    target_garden_home: str | Path,
) -> GardenBundleImportResult:
    """Import a bundle into a **new, empty** garden home directory.

    *target_garden_home* must not already contain a ``manifest.json``.
    If the directory is non-empty or already has a manifest the import
    is **blocked** — no files are written.

    The bundle is expected to be a directory containing at least
    ``bundle_manifest.json``.
    """
    src = Path(bundle_path).resolve()
    dest = Path(target_garden_home).resolve()

    # ── Pre-import safety checks ──────────────────────────────────
    manifest_path = dest / "manifest.json"
    if manifest_path.exists():
        return GardenBundleImportResult(
            target_garden_home=str(dest),
            bundle_path=str(src),
            status="blocked",
        )

    if dest.exists() and any(dest.iterdir()):
        return GardenBundleImportResult(
            target_garden_home=str(dest),
            bundle_path=str(src),
            status="blocked",
        )

    if not src.is_dir():
        return GardenBundleImportResult(
            target_garden_home=str(dest),
            bundle_path=str(src),
            status="failed",
        )

    try:
        bundle_manifest_path = _validated_bundle_file(src, "bundle_manifest.json")
    except OSError:
        bundle_manifest_path = None
    if bundle_manifest_path is None:
        return GardenBundleImportResult(
            target_garden_home=str(dest),
            bundle_path=str(src),
            status="failed",
        )

    # ── Read bundle manifest ──────────────────────────────────────
    try:
        bundle_data = json.loads(_read_limited_text(bundle_manifest_path))
        bundle_manifest = GardenBundleManifest(**bundle_data)
    except (json.JSONDecodeError, OSError, TypeError, ValidationError, ValueError):
        return GardenBundleImportResult(
            target_garden_home=str(dest),
            bundle_path=str(src),
            status="failed",
        )

    # ── Copy files ────────────────────────────────────────────────
    files_to_import: list[tuple[str, str]] = []
    for name in _BUNDLE_FILES:
        try:
            src_file = _validated_bundle_file(src, name)
            if src_file is None:
                continue
            files_to_import.append((name, _read_limited_text(src_file)))
        except (OSError, ValueError):
            return GardenBundleImportResult(
                target_garden_home=str(dest),
                bundle_path=str(src),
                status="failed",
            )

    dest.mkdir(parents=True, exist_ok=True)
    imported: list[str] = []
    for name, text in files_to_import:
        _write_text(dest / name, text)
        imported.append(name)

    return GardenBundleImportResult(
        target_garden_home=str(dest),
        bundle_path=str(src),
        manifest=bundle_manifest,
        files_imported=imported,
        status="ok",
    )


def _write_json(path: Path, data: dict) -> None:
    _write_text(path, json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False))


def _write_text(path: Path, text: str) -> None:
    if path.is_symlink():
        raise OSError(f"Refusing to write through symlink: {path}")
    path.write_text(text, encoding="utf-8")


def _validated_bundle_file(bundle_dir: Path, name: str) -> Path | None:
    path = bundle_dir / name
    if not path.exists():
        return None
    if path.is_symlink():
        raise OSError(f"Refusing symlinked bundle file: {path}")
    if not path.is_file():
        return None
    resolved = path.resolve(strict=True)
    if resolved.parent != bundle_dir:
        raise OSError(f"Bundle file escapes bundle directory: {path}")
    if resolved.stat().st_size > _MAX_BUNDLE_FILE_BYTES:
        raise ValueError(f"Bundle file is too large: {path}")
    return resolved


def _read_limited_text(path: Path) -> str:
    if path.stat().st_size > _MAX_BUNDLE_FILE_BYTES:
        raise ValueError(f"Bundle file is too large: {path}")
    return path.read_text(encoding="utf-8")
