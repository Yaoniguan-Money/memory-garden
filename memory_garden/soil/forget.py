"""Garden Forget: hard-forget planning, execution with FTS cleanup, and audit.

This module wraps the Core's ``forget_memory()`` with additional
Soil-level cleanup: FTS index removal, orphaned record detection, and
structured ``ForgetPlan`` / ``ForgetResult`` audit trails.

Core semantics are **not** modified.  This module reads the Core models
and the FTS index, calls Core's forget entry point, and then performs
Soil-side cleanup.
"""

from __future__ import annotations

import sqlite3
import json
from pathlib import Path

from memory_garden.soil.index import (
    DB_FILENAME,
    FTS_TABLE,
    _fts_exists,
    _open_db,
)
from memory_garden.soil.content_probes import build_content_probes_from_db, proof_json_contains_probe_plaintext
from memory_garden.soil.models import (
    GardenForgetPlan,
    GardenForgetResult,
    GardenIndexIssue,
    GardenHealthStatus,
)


def plan_hard_forget(
    garden_home: str | Path,
    memory_id: str,
) -> GardenForgetPlan:
    """Audit what a hard forget of *memory_id* would affect.

    Returns a ``GardenForgetPlan`` listing the entities that would be
    touched.  Does **not** execute the forget or modify any data.
    """
    root = Path(garden_home).resolve()
    db = root / DB_FILENAME
    affected: dict[str, list[str]] = {"memory_card": [memory_id]}
    fts_count = 0
    notes: list[str] = []

    if db.is_file():
        conn = _open_db(root)
        try:
            seed_ids = _dedupe_ids([
                *_memory_payload_ids(conn, memory_id, "source_seed_ids"),
                *_find_related_seed_ids(conn, memory_id),
            ])
            if seed_ids:
                affected["seed"] = seed_ids
                notes.append(f"{len(seed_ids)} related seed(s) found (rows remain after forget)")

            case_ids = _dedupe_ids([
                *_memory_payload_ids(conn, memory_id, "court_case_ids"),
                *_find_related_case_ids(conn, memory_id, seed_ids),
            ])
            if case_ids:
                affected["court_case"] = case_ids
                notes.append(f"{len(case_ids)} related court case(s) found (rows remain after forget)")

            # Count FTS entries
            if _fts_exists(conn):
                # FTS_TABLE is a fixed internal constant; values stay parameterized.
                fts_row = conn.execute(
                    f"SELECT COUNT(*) AS cnt FROM {FTS_TABLE} WHERE target_id = ? AND target_type = 'memory_card'",
                    (memory_id,),
                ).fetchone()
                fts_count = fts_row["cnt"] if fts_row else 0
                if fts_count > 0:
                    affected["fts_entry"] = [memory_id]

        finally:
            conn.close()
    else:
        notes.append("No garden database found — plan is based on Core state only.")

    content_probes = build_content_probes_from_db(root, memory_id)

    return GardenForgetPlan(
        memory_id=memory_id,
        mode="hard",
        affected_entities=affected,
        fts_entries=fts_count,
        notes="; ".join(notes) if notes else "",
        content_probes=content_probes,
    )


def _find_related_seed_ids(conn: sqlite3.Connection, memory_id: str) -> list[str]:
    """Find seeds whose structured payload points at the forgotten memory."""

    rows = conn.execute(
        """
        SELECT id FROM seeds
        WHERE json_extract(payload, '$.source_memory_id') = ?
           OR json_extract(payload, '$.resulting_memory_id') = ?
           OR json_extract(payload, '$.target_memory_id') = ?
        ORDER BY id
        """,
        (memory_id, memory_id, memory_id),
    ).fetchall()
    return [row["id"] for row in rows]


def _memory_payload_ids(conn: sqlite3.Connection, memory_id: str, key: str) -> list[str]:
    """Read source ids recorded on the MemoryCard payload itself."""

    row = conn.execute(
        "SELECT payload FROM memory_cards WHERE id = ?",
        (memory_id,),
    ).fetchone()
    if row is None:
        return []
    try:
        payload = json.loads(row["payload"])
    except (json.JSONDecodeError, TypeError):
        return []
    values = payload.get(key) if isinstance(payload, dict) else None
    if not isinstance(values, list):
        return []
    return [item for item in values if isinstance(item, str) and item.strip()]


def _dedupe_ids(ids: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in ids:
        item = raw.strip()
        if not item or item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def _find_related_case_ids(
    conn: sqlite3.Connection,
    memory_id: str,
    seed_ids: list[str],
) -> list[str]:
    """Find court cases attached to related seeds or directly to the memory."""

    case_ids: set[str] = set()
    if seed_ids:
        placeholders = ",".join("?" for _ in seed_ids)
        rows = conn.execute(
            f"SELECT id FROM court_cases WHERE seed_id IN ({placeholders})",
            seed_ids,
        ).fetchall()
        case_ids.update(row["id"] for row in rows)

    rows = conn.execute(
        """
        SELECT id FROM court_cases
        WHERE json_extract(payload, '$.source_memory_id') = ?
           OR json_extract(payload, '$.resulting_memory_id') = ?
           OR json_extract(payload, '$.target_memory_id') = ?
        """,
        (memory_id, memory_id, memory_id),
    ).fetchall()
    case_ids.update(row["id"] for row in rows)
    return sorted(case_ids)


def _delete_fts_entries(conn: sqlite3.Connection, target_type: str, target_ids: list[str]) -> int:
    """Delete FTS rows for a fixed target type and list of ids."""

    if not target_ids or not _fts_exists(conn):
        return 0
    removed = 0
    for target_id in target_ids:
        # FTS_TABLE is an internal constant from soil.index, not user input.
        cur = conn.execute(
            f"DELETE FROM {FTS_TABLE} WHERE target_id = ? AND target_type = ?",
            (target_id, target_type),
        )
        removed += cur.rowcount
    return removed


def execute_hard_forget(
    garden_home: str | Path,
    memory_id: str,
    *,
    reason: str = "",
    dry_run: bool = False,
    cascade: bool = False,
) -> GardenForgetResult:
    """Execute a hard forget with full Soil-side cleanup.

    1. Generates a ``ForgetPlan`` to audit affected entities.
    2. Calls Core's ``forget_memory(hard)`` via a temporary in-memory repository.
    3. Removes the corresponding FTS5 index entries.
    4. Returns a ``GardenForgetResult`` audit trail.

    When *dry_run* is ``True``, no deletions are performed and the
    result reflects what **would** happen.
    """
    root = Path(garden_home).resolve()
    plan = plan_hard_forget(root, memory_id)
    content_probes = plan.content_probes

    if dry_run:
        return GardenForgetResult(
            memory_id=memory_id,
            mode="hard",
            status="ok",
            memory_deleted=False,
            fts_entries_removed=plan.fts_entries,
            seed_ids_cleaned=plan.affected_entities.get("seed", []),
            case_ids_cleaned=plan.affected_entities.get("court_case", []),
            dry_run=True,
            issues=[],
            content_probe_fingerprint=(
                content_probes.probe_fingerprint if content_probes is not None else ""
            ),
        )

    issues: list[GardenIndexIssue] = []
    memory_deleted = False
    fts_removed = 0
    seeds_cleaned: list[str] = []
    cases_cleaned: list[str] = []

    # ── 1. Call Core's forget_memory ──────────────────────────────
    db_path = root / DB_FILENAME
    if not db_path.is_file():
        return GardenForgetResult(
            memory_id=memory_id,
            mode="hard",
            status="failed",
            dry_run=False,
            issues=[GardenIndexIssue(
                code="database_missing",
                message=f"Garden database not found: {db_path}",
                severity=GardenHealthStatus.unhealthy,
            )],
        )

    if db_path.is_file():
        from memory_garden.core.garden import MemoryGardenCore
        from memory_garden.storage.sqlite import SQLiteGardenRepository

        repo = SQLiteGardenRepository(str(db_path))
        core = MemoryGardenCore(repository=repo)
        try:
            repo.begin()
            core.forget(memory_id=memory_id, mode="hard", reason=reason or "hard forget via Soil")

            # FTS + cascade cleanup 在同一 repo 连接上执行，begin() 抑制了 _maybe_commit 的自动提交
            if _fts_exists(repo._conn):
                cur = repo._conn.execute(
                    f"DELETE FROM {FTS_TABLE} WHERE target_id = ? AND target_type = 'memory_card'",
                    (memory_id,),
                )
                fts_removed = cur.rowcount

            if cascade:
                seeds_cleaned = list(plan.affected_entities.get("seed", []))
                cases_cleaned = list(plan.affected_entities.get("court_case", []))

                for case_id in cases_cleaned:
                    repo._conn.execute("DELETE FROM court_cases WHERE id = ?", (case_id,))
                for seed_id in seeds_cleaned:
                    repo._conn.execute("DELETE FROM seeds WHERE id = ?", (seed_id,))

                _delete_fts_entries(repo._conn, "court_case", cases_cleaned)
                _delete_fts_entries(repo._conn, "seed", seeds_cleaned)

                # 清理直接关联的修剪和温室记录
                repo._conn.execute(
                    "DELETE FROM pruning_records WHERE memory_id = ?", (memory_id,)
                )
                repo._conn.execute(
                    "DELETE FROM greenhouse_records WHERE memory_id = ?", (memory_id,)
                )

                event_object_ids = [memory_id, *seeds_cleaned, *cases_cleaned]
                for object_id in event_object_ids:
                    repo._conn.execute(
                        "DELETE FROM garden_events WHERE object_id = ?",
                        (object_id,),
                    )

            repo._conn.commit()
            memory_deleted = True
        except Exception as exc:
            try:
                repo._conn.rollback()
            except Exception:
                pass
            issues.append(GardenIndexIssue(
                code="forget_cleanup_error",
                message=f"Failed during forget: {exc}",
                severity=GardenHealthStatus.unhealthy if not memory_deleted else GardenHealthStatus.degraded,
            ))
            if not memory_deleted:
                return GardenForgetResult(
                    memory_id=memory_id,
                    mode="hard",
                    status="failed",
                    issues=issues,
                )
        finally:
            repo.close()

    # ── 4. Verify ─────────────────────────────────────────────────
    if db_path.is_file():
        conn = _open_db(root)
        try:
            # Verify memory card is gone
            card_row = conn.execute(
                "SELECT id FROM memory_cards WHERE id = ?", (memory_id,)
            ).fetchone()
            if card_row:
                issues.append(GardenIndexIssue(
                    code="forget_verification_failed",
                    message=f"MemoryCard {memory_id} still exists after hard forget",
                    severity=GardenHealthStatus.unhealthy,
                ))

            # Verify FTS entry is gone
            if _fts_exists(conn):
                fts_row = conn.execute(
                    f"SELECT target_id FROM {FTS_TABLE} WHERE target_id = ? AND target_type = 'memory_card'",
                    (memory_id,),
                ).fetchone()
                if fts_row:
                    issues.append(GardenIndexIssue(
                        code="fts_cleanup_verification_failed",
                        message=f"FTS entry for {memory_id} still exists after cleanup",
                        severity=GardenHealthStatus.unhealthy,
                    ))
        finally:
            conn.close()

    status = "ok"
    if any(i.severity == GardenHealthStatus.unhealthy for i in issues):
        status = "failed"
    elif issues:
        status = "partial"

    return GardenForgetResult(
        memory_id=memory_id,
        mode="hard",
        status=status,
        memory_deleted=memory_deleted,
        fts_entries_removed=fts_removed,
        seed_ids_cleaned=seeds_cleaned,
        case_ids_cleaned=cases_cleaned,
        issues=issues,
        content_probe_fingerprint=(
            content_probes.probe_fingerprint if content_probes is not None else ""
        ),
    )
