"""Garden Soil: local-first persistence, manifest, snapshot, health,
migration, bundle, FTS5 search, and reindex layer.

This is the soil layer (v0.10.2). It does **not** include:
- Real SQLite schema migration (only a planning skeleton)
- Embedding storage or index
- Cross-machine data portability
- Automatic background indexing

All directory and file creation is explicit. No directory is created
on ``import memory_garden`` or ``import memory_garden.soil``.
"""

from memory_garden.soil.bundle import export_garden_bundle, import_garden_bundle
from memory_garden.soil.forget import execute_hard_forget, plan_hard_forget
from memory_garden.soil.forget_proof import prove_forget
from memory_garden.soil.health import check_garden_health
from memory_garden.soil.home import initialize_garden_home, resolve_garden_home
from memory_garden.soil.index import check_garden_index, reindex_garden
from memory_garden.soil.manifest import load_manifest, save_manifest
from memory_garden.soil.migration import migrate_garden, plan_garden_migration
from memory_garden.soil.models import (
    ForgetProof,
    ForgetProofCheck,
    ForgetProofVerdict,
    GardenBundleExportResult,
    GardenBundleImportResult,
    GardenBundleManifest,
    GardenForgetPlan,
    GardenForgetResult,
    GardenHealthIssue,
    GardenHealthReport,
    GardenHealthStatus,
    GardenHome,
    GardenIndexIssue,
    GardenIndexStatus,
    GardenManifest,
    GardenMigrationPlan,
    GardenMigrationResult,
    GardenMigrationStatus,
    GardenMigrationStep,
    GardenReindexResult,
    GardenSearchHit,
    GardenSnapshot,
)
from memory_garden.soil.search import hybrid_search_garden, search_garden, search_garden_scoped
from memory_garden.soil.snapshot import create_garden_snapshot

__all__ = [
    "ForgetProof",
    "ForgetProofCheck",
    "ForgetProofVerdict",
    "GardenBundleExportResult",
    "GardenBundleImportResult",
    "GardenBundleManifest",
    "GardenForgetPlan",
    "GardenForgetResult",
    "GardenHealthIssue",
    "GardenHealthReport",
    "GardenHealthStatus",
    "GardenHome",
    "GardenIndexIssue",
    "GardenIndexStatus",
    "GardenManifest",
    "GardenMigrationPlan",
    "GardenMigrationResult",
    "GardenMigrationStatus",
    "GardenMigrationStep",
    "GardenReindexResult",
    "GardenSearchHit",
    "GardenSnapshot",
    "check_garden_health",
    "check_garden_index",
    "create_garden_snapshot",
    "execute_hard_forget",
    "export_garden_bundle",
    "import_garden_bundle",
    "initialize_garden_home",
    "load_manifest",
    "migrate_garden",
    "plan_garden_migration",
    "plan_hard_forget",
    "prove_forget",
    "reindex_garden",
    "resolve_garden_home",
    "save_manifest",
    "hybrid_search_garden",
    "search_garden",
    "search_garden_scoped",
]
