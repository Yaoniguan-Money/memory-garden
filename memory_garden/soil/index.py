"""Garden FTS5 Index: create, rebuild, and check the full-text search index.

All operations are explicit.  The index is never created or rebuilt
automatically on ``import``.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from memory_garden.soil.models import (
    GardenHealthStatus,
    GardenIndexIssue,
    GardenIndexStatus,
    GardenReindexResult,
)

FTS_TABLE = "garden_fts_index"
DB_FILENAME = "garden.db"

# Target types whose payload contains fields we can index.
# Each entry: (target_type, db_table, title_expr, body_expr, extra_json_keys)
_INDEXABLE: list[tuple[str, str, str, str, list[str]]] = [
    (
        "memory_card",
        "memory_cards",
        "json_extract(payload, '$.title')",
        "json_extract(payload, '$.essence')",
        ["tags", "memory_type", "lifecycle"],
    ),
    (
        "seed",
        "seeds",
        "json_extract(payload, '$.content')",
        "json_extract(payload, '$.content')",
        ["tags", "signal_type", "status"],
    ),
    (
        "court_case",
        "court_cases",
        "json_extract(payload, '$.prosecutor_argument')",
        "json_extract(payload, '$.judge_verdict') || ' ' || json_extract(payload, '$.prosecutor_argument')",
        ["seed_id", "verdict"],
    ),
    (
        "dream_record",
        "dream_records",
        "json_extract(payload, '$.observation')",
        "json_extract(payload, '$.reflection') || ' ' || json_extract(payload, '$.transformation')",
        [],
    ),
]


def _db_path(garden_home: str | Path) -> Path:
    return Path(garden_home).resolve() / DB_FILENAME


# 注意：_open_db / _fts_exists 虽以下划线前缀命名，但被多个 soil 子模块共用
#（forget.py, forget_proof.py, health.py, search.py），修改签名时需同步更新所有调用方。
def _open_db(garden_home: str | Path) -> sqlite3.Connection:
    db = _db_path(garden_home)
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    return conn


def _fts_exists(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (FTS_TABLE,),
    ).fetchone()
    return row is not None


def _fts_has_ngram_column(conn: sqlite3.Connection) -> bool:
    if not _fts_exists(conn):
        return False
    try:
        conn.execute(f"SELECT body_ngram FROM {FTS_TABLE} LIMIT 0")
        return True
    except sqlite3.Error:
        return False


def check_garden_index(garden_home: str | Path) -> GardenIndexStatus:
    """Inspect the FTS index and return its status.

    This is **read-only** — it never creates or modifies the index.
    """
    db = _db_path(garden_home)
    if not db.is_file():
        return GardenIndexStatus(exists=False, healthy=False, issues=[
            GardenIndexIssue(code="database_missing",
                             message=f"Garden database not found: {db}",
                             severity=GardenHealthStatus.degraded),
        ])

    conn = _open_db(garden_home)
    try:
        if not _fts_exists(conn):
            return GardenIndexStatus(exists=False, healthy=False, issues=[
                GardenIndexIssue(code="fts_table_missing",
                                 message="FTS index table does not exist. Run reindex_garden() to create it.",
                                 severity=GardenHealthStatus.degraded),
            ])

        try:
            row = conn.execute(f"SELECT COUNT(*) AS cnt FROM {FTS_TABLE}").fetchone()
            count = row["cnt"] if row else 0
        except sqlite3.Error as exc:
            return GardenIndexStatus(exists=True, healthy=False, indexed_count=0, issues=[
                GardenIndexIssue(code="fts_table_corrupt",
                                 message=f"FTS table exists but cannot be queried: {exc}",
                                 severity=GardenHealthStatus.unhealthy),
            ])

        target_types: list[str] = []
        try:
            types_row = conn.execute(
                f"SELECT DISTINCT target_type FROM {FTS_TABLE}"
            ).fetchall()
            target_types = sorted(r["target_type"] for r in types_row)
        except sqlite3.Error:
            # 旧索引缺字段时保留 exists/healthy 主判断。
            pass

        return GardenIndexStatus(
            exists=True,
            healthy=True,
            indexed_count=count,
            target_types=target_types,
            issues=[],
        )
    finally:
        conn.close()


def reindex_garden(
    garden_home: str | Path,
    *,
    target_types: list[str] | None = None,
    dry_run: bool = False,
) -> GardenReindexResult:
    """Create or rebuild the FTS5 index for *garden_home*.

    When *dry_run* is ``True`` (default), the index is **not** modified.
    When *dry_run* is ``False``, the FTS table is dropped and recreated,
    then populated from the source tables.

    *target_types* filters which entity types to index.  When ``None``,
    all supported types are indexed (``memory_card``, ``seed``,
    ``court_case``, ``dream_record``).
    """
    db = _db_path(garden_home)
    started_at = datetime.now(timezone.utc)
    issues: list[GardenIndexIssue] = []

    if not db.is_file():
        return GardenReindexResult(
            status="failed",
            dry_run=dry_run,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            issues=[GardenIndexIssue(code="database_missing",
                                      message=f"Garden database not found: {db}",
                                      severity=GardenHealthStatus.unhealthy)],
        )

    conn = _open_db(garden_home)
    try:
        # Determine which target types to process
        selected = _INDEXABLE
        if target_types is not None:
            allowed = set(target_types)
            selected = [e for e in _INDEXABLE if e[0] in allowed]

        indexed_count = 0
        skipped_count = 0
        used_types: list[str] = []

        if dry_run:
            # Count what would be indexed
            for target_type, table, _title, _body, _extra in selected:
                try:
                    row = conn.execute(f"SELECT COUNT(*) AS cnt FROM {table}").fetchone()
                    cnt = row["cnt"] if row else 0
                    indexed_count += cnt
                    if cnt > 0:
                        used_types.append(target_type)
                except sqlite3.Error:
                    # 某类源表缺失时跳过该类，继续重建其它可用类型。
                    continue
            return GardenReindexResult(
                status="ok",
                indexed_count=indexed_count,
                skipped_count=skipped_count,
                target_types=used_types,
                dry_run=True,
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
            )

        # ── Real reindex ────────────────────────────────────────
        # Drop old FTS table if it exists
        conn.execute(f"DROP TABLE IF EXISTS {FTS_TABLE}")

        # Create FTS5 virtual table
        conn.execute(
            f"""
            CREATE VIRTUAL TABLE {FTS_TABLE} USING fts5(
                target_type,
                target_id,
                title,
                body,
                body_ngram,
                metadata_json,
                tokenize='unicode61'
            )
            """
        )

        # Populate from each selected source table
        for target_type, table, title_expr, body_expr, extra_keys in selected:
            # Build metadata JSON from extra keys
            meta_parts = ", ".join(
                f"'{k}', json_extract(payload, '$.{k}')" for k in extra_keys
            )
            if meta_parts:
                meta_expr = f"json_object({meta_parts})"
            else:
                meta_expr = "'{}'"

            # Count how many rows exist in source
            try:
                cnt_row = conn.execute(f"SELECT COUNT(*) AS cnt FROM {table}").fetchone()
                total = cnt_row["cnt"] if cnt_row else 0
            except sqlite3.Error:
                total = 0

            if total == 0:
                skipped_count += 0
                continue

            # Insert from source table into FTS（Python 侧生成 CJK ngram）
            try:
                from memory_garden.soil.cjk_ngram import cjk_index_text

                source_rows = conn.execute(
                    f"""
                    SELECT
                        id,
                        {title_expr} AS title,
                        {body_expr} AS body,
                        {meta_expr} AS metadata_json
                    FROM {table}
                    """
                ).fetchall()
                from memory_garden.runtime_config import default_garden_runtime_config

                batch_size = default_garden_runtime_config().reindex.fts_batch_size
                batch: list[tuple[str, str, str, str, str, str]] = []
                inserted = 0
                for row in source_rows:
                    title = row["title"] or ""
                    body = row["body"] or ""
                    ngram = cjk_index_text(f"{title} {body}")
                    batch.append(
                        (
                            target_type,
                            row["id"],
                            title,
                            body,
                            ngram,
                            row["metadata_json"],
                        )
                    )
                    if len(batch) >= batch_size:
                        conn.executemany(
                            f"""
                            INSERT INTO {FTS_TABLE}
                            (target_type, target_id, title, body, body_ngram, metadata_json)
                            VALUES (?, ?, ?, ?, ?, ?)
                            """,
                            batch,
                        )
                        inserted += len(batch)
                        batch.clear()
                if batch:
                    conn.executemany(
                        f"""
                        INSERT INTO {FTS_TABLE}
                        (target_type, target_id, title, body, body_ngram, metadata_json)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        batch,
                    )
                    inserted += len(batch)
                indexed_count += inserted
                used_types.append(target_type)
            except sqlite3.Error as exc:
                issues.append(GardenIndexIssue(
                    code="fts_insert_error",
                    message=f"Failed to index {target_type} from {table}: {exc}",
                    severity=GardenHealthStatus.degraded,
                ))

        conn.commit()
        return GardenReindexResult(
            status="ok",
            indexed_count=indexed_count,
            skipped_count=skipped_count,
            target_types=used_types,
            dry_run=False,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            issues=issues,
        )
    finally:
        conn.close()
