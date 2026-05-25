# Garden Soil Architecture

Garden Soil is the tenth Memory Garden layer: the local-first persistence, manifest, snapshot, and health layer. It gives the garden a physical home on the user's filesystem.

## Why It Exists

Earlier layers assumed storage existed but were deliberately silent on *where* the garden lives on disk. The Core's `GardenRepository` interface and `SQLiteGardenRepository` implementation provided the *mechanism* for persistence, but not the *convention*: where does the directory go, how is it initialized, what metadata lives alongside the database, and how do you check if the garden is healthy?

Garden Soil answers these questions with a minimal, explicit, non-magical layer.

## Design Principles

- **No automatic directory creation on import**: `import memory_garden` or `import memory_garden.soil` must never create `.memory_garden` or any other directory. All filesystem mutations require an explicit function call.
- **Minimal by design**: This is the soil layer with migration planning, bundle export/import, FTS5 full-text search, and reindex. No real SQLite schema migration, no embedding store, and no cross-machine data portability.
- **Standard library + existing deps**: No new dependencies beyond what the project already uses (Pydantic, PyYAML).
- **Stable JSON output**: `manifest.json` uses `sort_keys=True` for deterministic, diffable output.

## Modules

| Module | Role |
|---|---|
| `memory_garden/soil/models.py` | Pydantic models: `GardenHome`, `GardenManifest`, `GardenSnapshot`, `GardenHealthReport`, `GardenHealthIssue`, `GardenHealthStatus` |
| `memory_garden/soil/home.py` | `resolve_garden_home()` (no side effects) and `initialize_garden_home()` (creates directory + manifest) |
| `memory_garden/soil/manifest.py` | `load_manifest()` and `save_manifest()` for `manifest.json` |
| `memory_garden/soil/snapshot.py` | `create_garden_snapshot()` for point-in-time metadata capture |
| `memory_garden/soil/health.py` | `check_garden_health()` for structural integrity checks |
| `memory_garden/soil/migration.py` | `plan_garden_migration()` and `migrate_garden()` — skeleton migration planning |
| `memory_garden/soil/bundle.py` | `export_garden_bundle()` and `import_garden_bundle()` — metadata-only bundle |
| `memory_garden/soil/index.py` | `reindex_garden()` and `check_garden_index()` — FTS5 index management |
| `memory_garden/soil/search.py` | `search_garden()` — FTS5 full-text search |
| `memory_garden/soil/forget.py` | `plan_hard_forget()` and `execute_hard_forget()` — hard forget with FTS cleanup and audit |

## Core API

```python
from memory_garden.soil import (
    resolve_garden_home,
    initialize_garden_home,
    load_manifest,
    save_manifest,
    create_garden_snapshot,
    check_garden_health,
)
```

### resolve_garden_home

```python
def resolve_garden_home(base_path: str | Path | None = None) -> Path
```

Returns the path that *would* be used as the garden home. Does **not** create any directory or file.

- If `base_path` is provided, resolves it to an absolute path.
- If `base_path` is None, defaults to `$CWD/.memory_garden`.

### initialize_garden_home

```python
def initialize_garden_home(base_path: str | Path, *, create: bool = True) -> GardenHome
```

Creates the garden home directory (if `create=True`) and writes `manifest.json`. Returns a `GardenHome` model. Raises `FileNotFoundError` if `create=False` and the directory does not exist.

### load_manifest / save_manifest

```python
def load_manifest(garden_home: str | Path) -> GardenManifest
def save_manifest(garden_home: str | Path, manifest: GardenManifest) -> None
```

Read and write `manifest.json` with stable, sorted-key JSON output.

### create_garden_snapshot

```python
def create_garden_snapshot(garden_home: str | Path, *, include_manifest: bool = True, notes: str = "") -> GardenSnapshot
```

Creates a lightweight metadata snapshot. Does **not** copy the database file. Captures manifest key fields and a timestamp.

### check_garden_health

```python
def check_garden_health(garden_home: str | Path) -> GardenHealthReport
```

Checks: directory exists, `manifest.json` exists, is valid JSON, is a JSON object, contains `garden_name` and `schema_version` fields. Returns a `GardenHealthReport` with status (`healthy` / `degraded` / `unhealthy`) and a list of issues.

### plan_garden_migration

```python
def plan_garden_migration(garden_home: str | Path, target_schema_version: int) -> GardenMigrationPlan
```

Reads the current manifest and produces a migration plan. Returns a no-op plan when versions match. Returns a blocked plan on downgrade. Each version increment produces one placeholder `GardenMigrationStep`.

### migrate_garden

```python
def migrate_garden(garden_home: str | Path, target_schema_version: int, *, dry_run: bool = True) -> GardenMigrationResult
```

Plans and (optionally) executes a migration. When `dry_run=True` (default), the manifest is never modified. When `dry_run=False`, this skeleton updates `manifest.schema_version` but does **not** alter SQLite tables or columns.

### export_garden_bundle

```python
def export_garden_bundle(garden_home: str | Path, bundle_path: str | Path, *, notes: str = "") -> GardenBundleExportResult
```

Exports garden metadata to a directory bundle containing `bundle_manifest.json`, `garden_manifest.json`, and `snapshot.json`. The source garden is never modified. The SQLite database is not copied.

### import_garden_bundle

```python
def import_garden_bundle(bundle_path: str | Path, target_garden_home: str | Path) -> GardenBundleImportResult
```

Imports metadata files from a bundle into a new, empty garden home. Blocked if the target already has a `manifest.json` or is non-empty.

## Models

### GardenHome

| Field | Type | Description |
|---|---|---|
| `root` | `Path` | Absolute path to the garden home directory |
| `manifest` | `GardenManifest` | Parsed manifest |

### GardenManifest

| Field | Type | Default | Description |
|---|---|---|---|
| `garden_name` | `str` | `"memory-garden"` | Human-readable garden name |
| `schema_version` | `int` | `1` | Reserved for future migration |
| `created_at` | `datetime` | `utcnow()` | Initialization timestamp |
| `description` | `str` | `""` | Optional description |

### GardenSnapshot

| Field | Type | Description |
|---|---|---|
| `garden_home` | `str` | Path at snapshot time |
| `manifest_summary` | `dict` | Selected manifest fields |
| `created_at` | `datetime` | Snapshot timestamp |
| `schema_version` | `int` | Schema version at snapshot time |
| `notes` | `str` | Optional annotation |

### GardenHealthReport

| Field | Type | Description |
|---|---|---|
| `garden_home` | `str` | Inspected path |
| `status` | `GardenHealthStatus` | Overall health |
| `issues` | `list[GardenHealthIssue]` | Detected issues |
| `checked_at` | `datetime` | Check timestamp |

## Current Limits

- **No real SQLite schema migration**: Migration planning skeleton exists, but `migrate_garden()` only updates `manifest.schema_version`. No tables, columns, or indexes are altered.
- **No embedding index**: Embedding storage is out of scope.
- **No cross-machine portability**: Bundle export/import copies metadata files only — no database, no large payloads.
- **No automatic indexing**: `reindex_garden()` must be called explicitly. Health check reports index status but does not create or repair the index.
- **No Chinese tokenizer**: FTS5 uses the default `unicode61` tokenizer. CJK text will not be segmented.
- **No full cascade delete**: `execute_hard_forget()` deletes the MemoryCard and its FTS entry, but related Seeds and CourtCases remain for audit. The `ForgetPlan` documents what stays.
- **Stale FTS detection only**: Health check reports stale FTS entries (from incomplete forgets) but does not remove them. Use `reindex_garden()` to rebuild.

These are noted in the ROADMAP for future versions.

## FTS5 Search & Index API

### reindex_garden

```python
def reindex_garden(garden_home: str | Path, *, target_types: list[str] | None = None, dry_run: bool = False) -> GardenReindexResult
```

Creates or rebuilds the FTS5 index. When `dry_run=True` (default), counts what would be indexed but does not modify the index. When `dry_run=False`, drops and recreates the FTS virtual table and populates it from the source tables. Supports filtering by `target_types` (e.g. `["memory_card", "seed"]`).

### check_garden_index

```python
def check_garden_index(garden_home: str | Path) -> GardenIndexStatus
```

Read-only inspection of the FTS index. Returns `exists`, `healthy`, `indexed_count`, `target_types`, and a list of issues.

### search_garden

```python
def search_garden(garden_home: str | Path, query: str, *, limit: int = 10, target_types: list[str] | None = None) -> list[GardenSearchHit]
```

Queries the FTS5 index. Returns `GardenSearchHit` objects with `target_type`, `target_id`, `title`, `snippet`, `rank`, and `metadata`. Returns an empty list if the index does not exist or the query is empty. *limit* is clamped to [1, 200].

## FTS5 / Search Models

### GardenIndexStatus

| Field | Type | Description |
|---|---|---|
| `exists` | `bool` | Whether the FTS table exists |
| `healthy` | `bool` | Whether the table is queryable |
| `indexed_count` | `int` | Approximate indexed row count |
| `target_types` | `list[str]` | Entity types in the index |
| `issues` | `list[GardenIndexIssue]` | Detected issues |

### GardenReindexResult

| Field | Type | Description |
|---|---|---|
| `status` | `str` | ok / failed / skipped |
| `indexed_count` | `int` | Rows indexed |
| `skipped_count` | `int` | Rows skipped |
| `target_types` | `list[str]` | Types processed |
| `started_at` / `finished_at` | `datetime` | Timestamps |
| `dry_run` | `bool` | Whether no writes occurred |

### GardenSearchHit

| Field | Type | Description |
|---|---|---|
| `target_type` | `str` | e.g. memory_card, seed |
| `target_id` | `str` | Entity ID |
| `title` | `str` | Short title from entity |
| `snippet` | `str` | Relevant text snippet |
| `rank` | `float` | FTS rank (lower is better) |
| `metadata` | `dict` | Extra fields from the entity |

## Migration Models

### GardenMigrationPlan

| Field | Type | Description |
|---|---|---|
| `garden_home` | `str` | Garden home path |
| `current_schema_version` | `int` | Version from manifest |
| `target_schema_version` | `int` | Requested target |
| `steps` | `list[GardenMigrationStep]` | Ordered steps |
| `status` | `GardenMigrationStatus` | noop / plan_ready / blocked |
| `notes` | `str` | Human-readable notes |

### GardenMigrationResult

| Field | Type | Description |
|---|---|---|
| `garden_home` | `str` | Garden home path |
| `current_schema_version` | `int` | Version before migration |
| `target_schema_version` | `int` | Target version |
| `status` | `GardenMigrationStatus` | noop / completed / failed / blocked |
| `steps_applied` | `list[int]` | Sequence numbers applied |
| `steps_skipped` | `list[int]` | Sequence numbers skipped |
| `dry_run` | `bool` | Whether no changes were applied |
| `notes` | `str` | Human-readable notes |

## Bundle Models

### GardenBundleManifest

| Field | Type | Description |
|---|---|---|
| `bundle_version` | `str` | Bundle format version (`"1.0"`) |
| `garden_name` | `str` | Original garden name |
| `source_garden_home` | `str` | Path to exported garden |
| `schema_version` | `int` | Schema version at export time |
| `exported_at` | `datetime` | Export timestamp |
| `notes` | `str` | Optional annotation |

### GardenBundleExportResult / GardenBundleImportResult

Export result: `bundle_path`, `manifest`, `files_written`.
Import result: `target_garden_home`, `bundle_path`, `manifest`, `files_imported`, `status` (`ok` / `blocked` / `failed`).

## Boundaries

Garden Soil does not:

- Call Core, Runtime, Harvest, Observatory, Integration, Lab, or Covenant flows.
- Modify Memory Garden domain objects.
- Create or manage the SQLite database (that remains the Repository's responsibility).
- Execute on `import memory_garden`.
- Create `.memory_garden` in the user's current working directory without an explicit call.

## Integration Pattern

The Soil layer is designed to be called explicitly by application code, not by the library internals:

```python
from memory_garden.soil import initialize_garden_home, check_garden_health

# Application startup
home = initialize_garden_home("./my_garden")
print(f"Garden at {home.root}, schema v{home.manifest.schema_version}")

# Health check
report = check_garden_health(home.root)
if report.status != "healthy":
    for issue in report.issues:
        print(f"[{issue.severity}] {issue.code}: {issue.message}")
```

Future layers (CLI, SDK wrappers) may call Soil functions, but Soil itself stays minimal and passive.
