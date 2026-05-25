"""Forget Proof: systematically verify that a hard-forgotten memory
cannot be found through any garden surface.

Stage 14 adds content-level probes (token + salted hash) in addition to
memory_id existence checks.
"""

from __future__ import annotations

import json
import re
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

from memory_garden.soil.bundle import export_garden_bundle
from memory_garden.soil.content_probes import proof_json_contains_probe_plaintext
from memory_garden.soil.index import DB_FILENAME, FTS_TABLE, _fts_exists, _open_db
from memory_garden.soil.models import (
    ContentProbeSet,
    ForgetProof,
    ForgetProofCheck,
    ForgetProofVerdict,
)
from memory_garden.soil.search import search_garden

_SURFACES = [
    "db_memory_card_row",
    "fts_index_entry",
    "search_result",
    "bundle_manifest",
    "bundle_garden_manifest",
    "bundle_snapshot",
]

_CONTENT_SURFACES = [
    "db_content_scan",
    "fts_content_search",
    "bundle_content_scan",
    "product_content_scan",
    "audit_content_scan",
    "search_content_probe",
    "proof_redaction_self_check",
]

_LINEAGE_TABLES = frozenset({"seeds", "court_cases", "garden_events", "dream_records", "compost_records"})


def prove_forget(
    garden_home: str | Path,
    memory_id: str,
    *,
    content_probes: ContentProbeSet | None = None,
    cascade: bool | None = None,
    surfaces: list[str] | None = None,
) -> ForgetProof:
    """Verify that *memory_id* is truly gone from every garden surface."""
    root = Path(garden_home).resolve()
    proof_level = "content" if content_probes is not None and content_probes.token_probe_count > 0 else "id_only"

    if surfaces is None:
        target_surfaces = list(_SURFACES)
        if proof_level == "content":
            target_surfaces = [s for s in target_surfaces if s != "search_result"]
            target_surfaces.extend(_CONTENT_SURFACES)
    else:
        target_surfaces = list(surfaces)

    checks: list[ForgetProofCheck] = []
    db = root / DB_FILENAME
    allow_lineage_residual = cascade is False

    for surface in target_surfaces:
        if surface == "db_memory_card_row":
            checks.append(_check_db_row(db, memory_id))
        elif surface == "fts_index_entry":
            checks.append(_check_fts_entry(root, db, memory_id))
        elif surface == "search_result":
            checks.append(_check_search(root, db, memory_id, content_probes=None))
        elif surface == "search_content_probe":
            checks.append(_check_search(root, db, memory_id, content_probes=content_probes))
        elif surface == "bundle_manifest":
            checks.append(_check_bundle_file(root, memory_id, "bundle_manifest.json", content_probes))
        elif surface == "bundle_garden_manifest":
            checks.append(_check_bundle_file(root, memory_id, "garden_manifest.json", content_probes))
        elif surface == "bundle_snapshot":
            checks.append(_check_bundle_file(root, memory_id, "snapshot.json", content_probes))
        elif surface == "bundle_content_scan":
            checks.append(_check_bundle_content(root, memory_id, content_probes))
        elif surface == "db_content_scan":
            checks.append(
                _check_db_content(
                    db,
                    memory_id,
                    content_probes,
                    allow_lineage_residual,
                    cascade=cascade,
                )
            )
        elif surface == "fts_content_search":
            checks.append(_check_fts_content(root, db, memory_id, content_probes))
        elif surface == "product_content_scan":
            checks.append(_check_product_content(db, memory_id, content_probes))
        elif surface == "audit_content_scan":
            checks.append(
                _check_audit_content(
                    db,
                    memory_id,
                    content_probes,
                    allow_lineage_residual,
                    cascade=cascade,
                )
            )
        elif surface == "proof_redaction_self_check":
            checks.append(_check_proof_redaction(memory_id, root, content_probes, checks))

    passed = sum(1 for c in checks if c.verdict == ForgetProofVerdict.passed)
    failed = sum(1 for c in checks if c.verdict == ForgetProofVerdict.failed)
    skipped = sum(1 for c in checks if c.verdict == ForgetProofVerdict.skipped)

    fingerprint = content_probes.probe_fingerprint if content_probes is not None else ""

    return ForgetProof(
        memory_id=memory_id,
        garden_home=str(root),
        checks=checks,
        passed=passed,
        failed=failed,
        skipped=skipped,
        proven=(failed == 0 and passed > 0),
        content_probe_fingerprint=fingerprint,
        proof_level=proof_level,
    )


def _path_strip_needles(garden_home: str, memory_id: str) -> list[str]:
    root = Path(garden_home)
    raw_candidates = [
        garden_home,
        str(root),
        str(root.resolve()),
        str(root.parent),
        memory_id,
    ]
    needles: set[str] = set()
    for candidate in raw_candidates:
        if not candidate:
            continue
        folded = candidate.casefold()
        variants = {
            folded,
            folded.replace("\\", "/"),
            folded.replace("\\", "\\\\"),
            folded.replace("/", "\\"),
        }
        for variant in variants:
            needles.add(variant)
            needles.add(variant.replace("\\\\", "\\"))
    return sorted(needles, key=len, reverse=True)


def _strip_scan_context(text: str, *, garden_home: str, memory_id: str) -> str:
    lowered = text.casefold()
    for needle in _path_strip_needles(garden_home, memory_id):
        lowered = lowered.replace(needle, "")
    return lowered


def _token_in_text(token: str, text: str) -> bool:
    if not token:
        return False
    folded = text.casefold()
    token_folded = token.casefold()
    if re.fullmatch(r"[\w:.-]+", token, flags=re.ASCII):
        pattern = rf"(?<![\w:.-]){re.escape(token_folded)}(?![\w:.-])"
        return re.search(pattern, folded) is not None
    return token_folded in folded


def _sanitize_bundle_text(raw: str, *, garden_home: str, memory_id: str) -> str:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return _strip_scan_context(raw, garden_home=garden_home, memory_id=memory_id)
    if isinstance(data, dict):
        for key in ("source_garden_home", "garden_home"):
            data.pop(key, None)
        raw = json.dumps(data, ensure_ascii=False)
    return _strip_scan_context(raw, garden_home=garden_home, memory_id=memory_id)


def _scan_rows_for_tokens(
    conn: sqlite3.Connection,
    sql: str,
    params: tuple[Any, ...],
    tokens: list[str],
    *,
    table: str,
    column: str,
) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    try:
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.OperationalError:
        return hits
    for row in rows:
        text = str(row[0] or "")
        lowered = text.casefold()
        for token in tokens:
            if token.casefold() in lowered:
                hits.append({"table": table, "column": column, "probe_kind": "token"})
                break
    return hits


def _scan_memory_scoped_tables(
    conn: sqlite3.Connection,
    memory_id: str,
    tokens: list[str],
) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    scoped: list[tuple[str, str, str, tuple[Any, ...]]] = [
        ("memory_cards", "payload", "SELECT payload FROM memory_cards WHERE id = ?", (memory_id,)),
        ("memory_versions", "payload", "SELECT payload FROM memory_versions WHERE memory_id = ?", (memory_id,)),
        ("memory_proposals", "payload", "SELECT payload FROM memory_proposals WHERE created_memory_id = ?", (memory_id,)),
        ("memory_strategy_profiles", "payload", "SELECT payload FROM memory_strategy_profiles WHERE memory_id = ?", (memory_id,)),
        ("forget_plans", "payload", "SELECT payload FROM forget_plans WHERE memory_id = ?", (memory_id,)),
        ("forget_proofs", "payload", "SELECT payload FROM forget_proofs WHERE memory_id = ?", (memory_id,)),
        ("memory_evolution_plans", "payload", "SELECT payload FROM memory_evolution_plans WHERE memory_id = ?", (memory_id,)),
        (
            "memory_relations",
            "payload",
            "SELECT payload FROM memory_relations WHERE source_memory_id = ? OR target_memory_id = ?",
            (memory_id, memory_id),
        ),
        (
            "memory_conflict_arbitrations",
            "payload",
            "SELECT payload FROM memory_conflict_arbitrations WHERE existing_memory_id = ? OR new_memory_id = ?",
            (memory_id, memory_id),
        ),
        (
            "memory_retrieval_events",
            "payload",
            "SELECT payload FROM memory_retrieval_events WHERE payload LIKE ?",
            (f"%{memory_id}%",),
        ),
        (
            "pruning_records",
            "payload",
            "SELECT payload FROM pruning_records WHERE memory_id = ?",
            (memory_id,),
        ),
        (
            "greenhouse_records",
            "payload",
            "SELECT payload FROM greenhouse_records WHERE memory_id = ?",
            (memory_id,),
        ),
    ]
    for table, column, sql, params in scoped:
        hits.extend(_scan_rows_for_tokens(conn, sql, params, tokens, table=table, column=column))
    return hits


def _scan_lineage_tables(
    conn: sqlite3.Connection,
    tokens: list[str],
    *,
    memory_id: str | None = None,
) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    if memory_id:
        seed_sql = (
            "SELECT payload FROM seeds WHERE json_extract(payload, '$.source_memory_id') = ? "
            "OR json_extract(payload, '$.resulting_memory_id') = ? "
            "OR json_extract(payload, '$.target_memory_id') = ?"
        )
        hits.extend(
            _scan_rows_for_tokens(
                conn,
                seed_sql,
                (memory_id, memory_id, memory_id),
                tokens,
                table="seeds",
                column="payload",
            )
        )
        case_sql = (
            "SELECT payload FROM court_cases WHERE json_extract(payload, '$.source_memory_id') = ? "
            "OR json_extract(payload, '$.resulting_memory_id') = ? "
            "OR json_extract(payload, '$.target_memory_id') = ?"
        )
        hits.extend(
            _scan_rows_for_tokens(
                conn,
                case_sql,
                (memory_id, memory_id, memory_id),
                tokens,
                table="court_cases",
                column="payload",
            )
        )
        event_sql = "SELECT payload, summary FROM garden_events WHERE object_id = ?"
        for column in ("payload", "summary"):
            hits.extend(
                _scan_rows_for_tokens(
                    conn,
                    f"SELECT {column} FROM garden_events WHERE object_id = ?",
                    (memory_id,),
                    tokens,
                    table="garden_events",
                    column=column,
                )
            )
        return hits

    for table, columns in (
        ("seeds", ["payload"]),
        ("court_cases", ["payload"]),
        ("garden_events", ["payload", "summary"]),
        ("dream_records", ["payload"]),
        ("compost_records", ["payload"]),
    ):
        for column in columns:
            hits.extend(
                _scan_rows_for_tokens(
                    conn,
                    f"SELECT {column} FROM {table}",
                    (),
                    tokens,
                    table=table,
                    column=column,
                )
            )
    return hits


def _verdict_for_content_hits(
    surface: str,
    hits: list[dict[str, Any]],
    *,
    allow_lineage_residual: bool,
) -> ForgetProofCheck:
    if not hits:
        return ForgetProofCheck(
            surface=surface,
            verdict=ForgetProofVerdict.passed,
            detail="No content probe matches found",
            evidence={"leak_count": 0},
        )

    lineage_hits = [h for h in hits if h.get("table") in _LINEAGE_TABLES]
    strict_hits = [h for h in hits if h.get("table") not in _LINEAGE_TABLES]

    if strict_hits:
        return ForgetProofCheck(
            surface=surface,
            verdict=ForgetProofVerdict.failed,
            detail=f"Content probe matched in {len(strict_hits)} strict surface(s)",
            evidence={"leak_count": len(strict_hits), "tables": sorted({h['table'] for h in strict_hits})},
        )

    if lineage_hits and allow_lineage_residual:
        return ForgetProofCheck(
            surface=surface,
            verdict=ForgetProofVerdict.skipped,
            detail="residual_allowed_without_cascade: lineage tables retain probe matches",
            evidence={
                "leak_count": len(lineage_hits),
                "tables": sorted({h['table'] for h in lineage_hits}),
                "residual_allowed_without_cascade": True,
            },
        )

    return ForgetProofCheck(
        surface=surface,
        verdict=ForgetProofVerdict.failed,
        detail=f"Content probe matched in {len(hits)} surface(s)",
        evidence={"leak_count": len(hits), "tables": sorted({h['table'] for h in hits})},
    )


def _check_db_row(db: Path, memory_id: str) -> ForgetProofCheck:
    if not db.is_file():
        return ForgetProofCheck(surface="db_memory_card_row", verdict=ForgetProofVerdict.skipped,
                                detail="No database file")

    conn = sqlite3.connect(str(db))
    try:
        row = conn.execute("SELECT id FROM memory_cards WHERE id = ?", (memory_id,)).fetchone()
        if row is None:
            return ForgetProofCheck(surface="db_memory_card_row", verdict=ForgetProofVerdict.passed,
                                    detail="MemoryCard row successfully deleted")
        return ForgetProofCheck(surface="db_memory_card_row", verdict=ForgetProofVerdict.failed,
                                detail=f"MemoryCard row still exists: {memory_id}",
                                evidence={"row_found": True})
    except sqlite3.Error as exc:
        return ForgetProofCheck(surface="db_memory_card_row", verdict=ForgetProofVerdict.failed,
                                detail=str(exc))
    finally:
        conn.close()


def _check_fts_entry(root: Path, db: Path, memory_id: str) -> ForgetProofCheck:
    if not db.is_file():
        return ForgetProofCheck(surface="fts_index_entry", verdict=ForgetProofVerdict.skipped,
                                detail="No database file")

    conn = _open_db(root)
    try:
        if not _fts_exists(conn):
            return ForgetProofCheck(surface="fts_index_entry", verdict=ForgetProofVerdict.passed,
                                    detail="FTS index does not exist — nothing to leak from")
        row = conn.execute(
            f"SELECT target_id FROM {FTS_TABLE} WHERE target_id = ? AND target_type = 'memory_card'",
            (memory_id,),
        ).fetchone()
        if row is None:
            return ForgetProofCheck(surface="fts_index_entry", verdict=ForgetProofVerdict.passed,
                                    detail="FTS entry successfully removed")
        return ForgetProofCheck(surface="fts_index_entry", verdict=ForgetProofVerdict.failed,
                                detail=f"FTS entry still exists for {memory_id}",
                                evidence={"fts_row_found": True})
    except sqlite3.Error as exc:
        return ForgetProofCheck(surface="fts_index_entry", verdict=ForgetProofVerdict.failed,
                                detail=str(exc))
    finally:
        conn.close()


def _check_search(
    root: Path,
    db: Path,
    memory_id: str,
    *,
    content_probes: ContentProbeSet | None,
) -> ForgetProofCheck:
    surface = "search_content_probe" if content_probes is not None else "search_result"
    if not db.is_file():
        return ForgetProofCheck(surface=surface, verdict=ForgetProofVerdict.skipped,
                                detail="No database file")

    if content_probes is not None and content_probes.match_tokens:
        terms = list(content_probes.match_tokens)
    else:
        terms = _indexed_terms_for_memory(root, memory_id)

    if not terms:
        return ForgetProofCheck(
            surface=surface,
            verdict=ForgetProofVerdict.passed,
            detail="No search terms available for content probe",
            evidence={"queries": []},
        )

    try:
        all_hits = []
        for term in terms:
            all_hits.extend(search_garden(root, term, limit=50))
    except Exception as exc:
        return ForgetProofCheck(surface=surface, verdict=ForgetProofVerdict.skipped,
                                detail=f"Search failed (may be no index): {exc}")

    if content_probes is not None:
        content_hits = []
        for hit in all_hits:
            if hit.target_id != memory_id:
                continue
            blob = f"{hit.title} {hit.snippet}".casefold()
            for token in content_probes.match_tokens:
                if token.casefold() in blob:
                    content_hits.append(hit.target_id)
                    break
        if not content_hits:
            return ForgetProofCheck(
                surface=surface,
                verdict=ForgetProofVerdict.passed,
                detail=f"Search returned {len(all_hits)} hits, none match content probes",
                evidence={"total_hits": len(all_hits), "query_count": len(terms)},
            )
        return ForgetProofCheck(
            surface=surface,
            verdict=ForgetProofVerdict.failed,
            detail=f"Search returned {len(content_hits)} content probe hit(s)",
            evidence={"leak_count": len(content_hits), "total_hits": len(all_hits), "query_count": len(terms)},
        )

    matched = [h for h in all_hits if h.target_id == memory_id]
    if not matched:
        return ForgetProofCheck(surface=surface, verdict=ForgetProofVerdict.passed,
                                detail=f"Search returned {len(all_hits)} hits, none match {memory_id}",
                                evidence={"total_hits": len(all_hits), "queries": terms})
    return ForgetProofCheck(surface=surface, verdict=ForgetProofVerdict.failed,
                            detail=f"Search returned {len(matched)} hit(s) matching {memory_id}",
                            evidence={"leak_count": len(matched), "total_hits": len(all_hits), "queries": terms})


def _indexed_terms_for_memory(root: Path, memory_id: str) -> list[str]:
    conn = _open_db(root)
    try:
        if not _fts_exists(conn):
            return []
        row = conn.execute(
            f"SELECT title, body FROM {FTS_TABLE} WHERE target_id = ? AND target_type = 'memory_card'",
            (memory_id,),
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        return []
    blob = " ".join(str(row[key] or "") for key in ("title", "body"))
    terms: list[str] = []
    for raw in blob.replace("/", " ").replace("\n", " ").split():
        token = raw.strip(".,;:!?()[]{}\"'")
        if len(token) >= 2 and token not in terms:
            terms.append(token)
        if len(terms) >= 5:
            break
    if not terms and blob.strip():
        terms.append(blob.strip()[:16])
    return terms


def _check_bundle_file(
    root: Path,
    memory_id: str,
    filename: str,
    content_probes: ContentProbeSet | None,
) -> ForgetProofCheck:
    surface = f"bundle_{filename.split('.')[0]}"
    try:
        with tempfile.TemporaryDirectory() as tmp:
            bundle_dir = Path(tmp) / "proof_bundle"
            export_garden_bundle(root, bundle_dir)
            bundle_file = bundle_dir / filename
            if not bundle_file.is_file():
                return ForgetProofCheck(surface=surface,
                                        verdict=ForgetProofVerdict.skipped,
                                        detail=f"{filename} not found in bundle")
            raw_text = bundle_file.read_text(encoding="utf-8")
            text = _sanitize_bundle_text(raw_text, garden_home=str(root), memory_id=memory_id)
            if memory_id in raw_text:
                return ForgetProofCheck(surface=surface,
                                        verdict=ForgetProofVerdict.failed,
                                        detail=f"{memory_id} found in {filename}",
                                        evidence={"leak_file": filename})
            if content_probes is not None:
                for token in content_probes.match_tokens:
                    if len(token) < 8:
                        continue
                    if _token_in_text(token, text):
                        return ForgetProofCheck(
                            surface=surface,
                            verdict=ForgetProofVerdict.failed,
                            detail=f"Content probe matched in {filename}",
                            evidence={"leak_file": filename, "probe_kind": "token"},
                        )
            return ForgetProofCheck(surface=surface,
                                    verdict=ForgetProofVerdict.passed,
                                    detail=f"{memory_id} not found in {filename}")
    except Exception as exc:
        return ForgetProofCheck(surface=surface,
                                verdict=ForgetProofVerdict.skipped,
                                detail=f"Bundle check failed: {exc}")


def _check_bundle_content(
    root: Path,
    memory_id: str,
    content_probes: ContentProbeSet | None,
) -> ForgetProofCheck:
    if content_probes is None or not content_probes.match_tokens:
        return ForgetProofCheck(
            surface="bundle_content_scan",
            verdict=ForgetProofVerdict.skipped,
            detail="No content probes available",
        )
    try:
        with tempfile.TemporaryDirectory() as tmp:
            bundle_dir = Path(tmp) / "proof_bundle"
            export_garden_bundle(root, bundle_dir)
            sanitized_parts: list[str] = []
            for name in ("bundle_manifest.json", "garden_manifest.json", "snapshot.json"):
                path = bundle_dir / name
                if path.is_file():
                    raw = path.read_text(encoding="utf-8")
                    sanitized_parts.append(
                        _sanitize_bundle_text(raw, garden_home=str(root), memory_id=memory_id)
                    )
            db_copy = bundle_dir / "garden.db"
            if db_copy.is_file():
                sanitized_parts.append(
                    _strip_scan_context(
                        db_copy.read_bytes()[:4096].decode("utf-8", errors="ignore"),
                        garden_home=str(root),
                        memory_id=memory_id,
                    )
                )
            combined = "\n".join(sanitized_parts)
            for token in content_probes.match_tokens:
                if len(token) < 8:
                    continue
                if _token_in_text(token, combined):
                    return ForgetProofCheck(
                        surface="bundle_content_scan",
                        verdict=ForgetProofVerdict.failed,
                        detail="Content probe matched in exported bundle",
                        evidence={"probe_kind": "token", "leak_count": 1},
                    )
            if memory_id in combined:
                return ForgetProofCheck(
                    surface="bundle_content_scan",
                    verdict=ForgetProofVerdict.failed,
                    detail="memory_id found in exported bundle text",
                    evidence={"leak_count": 1},
                )
            return ForgetProofCheck(
                surface="bundle_content_scan",
                verdict=ForgetProofVerdict.passed,
                detail="No content probes matched in bundle export",
                evidence={"leak_count": 0},
            )
    except Exception as exc:
        return ForgetProofCheck(
            surface="bundle_content_scan",
            verdict=ForgetProofVerdict.skipped,
            detail=f"Bundle content scan failed: {exc}",
        )


def _check_db_content(
    db: Path,
    memory_id: str,
    content_probes: ContentProbeSet | None,
    allow_lineage_residual: bool,
    *,
    cascade: bool | None = None,
) -> ForgetProofCheck:
    if content_probes is None or not content_probes.match_tokens:
        return ForgetProofCheck(
            surface="db_content_scan",
            verdict=ForgetProofVerdict.skipped,
            detail="No content probes available",
        )
    if not db.is_file():
        return ForgetProofCheck(surface="db_content_scan", verdict=ForgetProofVerdict.skipped,
                                detail="No database file")

    conn = sqlite3.connect(str(db))
    try:
        strict_hits = _scan_memory_scoped_tables(conn, memory_id, content_probes.match_tokens)
        if cascade is True:
            lineage_hits = _scan_lineage_tables(conn, content_probes.match_tokens, memory_id=memory_id)
        else:
            lineage_hits = _scan_lineage_tables(conn, content_probes.match_tokens)
    finally:
        conn.close()

    hits = strict_hits + lineage_hits
    return _verdict_for_content_hits(
        "db_content_scan",
        hits,
        allow_lineage_residual=allow_lineage_residual,
    )


def _check_product_content(
    db: Path,
    memory_id: str,
    content_probes: ContentProbeSet | None,
) -> ForgetProofCheck:
    if content_probes is None or not content_probes.match_tokens:
        return ForgetProofCheck(
            surface="product_content_scan",
            verdict=ForgetProofVerdict.skipped,
            detail="No content probes available",
        )
    if not db.is_file():
        return ForgetProofCheck(surface="product_content_scan", verdict=ForgetProofVerdict.skipped,
                                detail="No database file")

    product_tables = {
        "memory_proposals",
        "memory_versions",
        "memory_strategy_profiles",
        "forget_plans",
        "forget_proofs",
        "memory_relations",
        "memory_retrieval_events",
        "provider_calls",
        "memory_evolution_plans",
        "memory_conflict_arbitrations",
    }
    conn = sqlite3.connect(str(db))
    try:
        hits = _scan_memory_scoped_tables(conn, memory_id, content_probes.match_tokens)
        hits = [h for h in hits if h.get("table") in product_tables]
    finally:
        conn.close()

    if not hits:
        return ForgetProofCheck(
            surface="product_content_scan",
            verdict=ForgetProofVerdict.passed,
            detail="No content probe matches in product tables",
            evidence={"leak_count": 0},
        )
    return ForgetProofCheck(
        surface="product_content_scan",
        verdict=ForgetProofVerdict.failed,
        detail=f"Content probe matched in {len(hits)} product row(s)",
        evidence={"leak_count": len(hits), "tables": sorted({h["table"] for h in hits})},
    )


def _check_audit_content(
    db: Path,
    memory_id: str,
    content_probes: ContentProbeSet | None,
    allow_lineage_residual: bool,
    *,
    cascade: bool | None = None,
) -> ForgetProofCheck:
    if content_probes is None or not content_probes.match_tokens:
        return ForgetProofCheck(
            surface="audit_content_scan",
            verdict=ForgetProofVerdict.skipped,
            detail="No content probes available",
        )
    if not db.is_file():
        return ForgetProofCheck(surface="audit_content_scan", verdict=ForgetProofVerdict.skipped,
                                detail="No database file")

    conn = sqlite3.connect(str(db))
    try:
        if cascade is True:
            hits = _scan_lineage_tables(conn, content_probes.match_tokens, memory_id=memory_id)
            hits = [h for h in hits if h.get("table") == "garden_events"]
        else:
            hits = _scan_lineage_tables(conn, content_probes.match_tokens)
            hits = [h for h in hits if h.get("table") == "garden_events"]
    finally:
        conn.close()
    return _verdict_for_content_hits(
        "audit_content_scan",
        hits,
        allow_lineage_residual=allow_lineage_residual,
    )


def _check_fts_content(
    root: Path,
    db: Path,
    memory_id: str,
    content_probes: ContentProbeSet | None,
) -> ForgetProofCheck:
    if content_probes is None or not content_probes.match_tokens:
        return ForgetProofCheck(
            surface="fts_content_search",
            verdict=ForgetProofVerdict.skipped,
            detail="No content probes available",
        )
    if not db.is_file():
        return ForgetProofCheck(surface="fts_content_search", verdict=ForgetProofVerdict.skipped,
                                detail="No database file")

    conn = _open_db(root)
    try:
        if not _fts_exists(conn):
            return ForgetProofCheck(
                surface="fts_content_search",
                verdict=ForgetProofVerdict.passed,
                detail="FTS index does not exist",
            )
        row = conn.execute(
            f"SELECT title, body FROM {FTS_TABLE} WHERE target_id = ? AND target_type = 'memory_card'",
            (memory_id,),
        ).fetchone()
    finally:
        conn.close()

    if row is None:
        return ForgetProofCheck(
            surface="fts_content_search",
            verdict=ForgetProofVerdict.passed,
            detail="No FTS row remains for forgotten memory",
            evidence={"leak_count": 0},
        )

    blob = f"{row['title'] or ''} {row['body'] or ''}".casefold()
    for token in content_probes.match_tokens:
        if token.casefold() in blob:
            return ForgetProofCheck(
                surface="fts_content_search",
                verdict=ForgetProofVerdict.failed,
                detail="Content probe matched in FTS row for forgotten memory",
                evidence={"probe_kind": "token", "leak_count": 1},
            )
    return ForgetProofCheck(
        surface="fts_content_search",
        verdict=ForgetProofVerdict.passed,
        detail="FTS row exists but does not match content probes",
        evidence={"leak_count": 0},
    )


def _check_proof_redaction(
    memory_id: str,
    root: Path,
    content_probes: ContentProbeSet | None,
    prior_checks: list[ForgetProofCheck],
) -> ForgetProofCheck:
    if content_probes is None or not content_probes.match_tokens:
        return ForgetProofCheck(
            surface="proof_redaction_self_check",
            verdict=ForgetProofVerdict.skipped,
            detail="No content probes available",
        )

    draft = ForgetProof(
        memory_id=memory_id,
        garden_home=str(root),
        checks=prior_checks,
        passed=0,
        failed=0,
        skipped=0,
        proven=False,
        content_probe_fingerprint=content_probes.probe_fingerprint,
        proof_level="content",
    )
    payload = json.dumps(draft.model_dump(mode="json"), ensure_ascii=False)
    leaks = proof_json_contains_probe_plaintext(
        payload,
        content_probes,
        memory_id=memory_id,
        min_token_len=12,
    )
    if leaks:
        return ForgetProofCheck(
            surface="proof_redaction_self_check",
            verdict=ForgetProofVerdict.failed,
            detail="Proof payload would leak probe plaintext",
            evidence={"leak_count": len(leaks), "redacted_tokens": leaks},
        )
    return ForgetProofCheck(
        surface="proof_redaction_self_check",
        verdict=ForgetProofVerdict.passed,
        detail="Proof payload contains no probe plaintext",
        evidence={"leak_count": 0},
    )
