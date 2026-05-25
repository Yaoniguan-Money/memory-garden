"""Garden Search: query the FTS5 full-text index.

All operations are read-only and explicit.  No index is created
or modified by calling ``search_garden()``.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

from memory_garden.soil.cjk_ngram import (
    build_cjk_fts_match_query,
    build_cjk_like_pattern,
    build_cjk_token_query,
    contains_cjk,
)
from memory_garden.soil.index import (
    DB_FILENAME,
    FTS_TABLE,
    _fts_exists,
    _fts_has_ngram_column,
    _open_db,
)
from memory_garden.soil.models import GardenSearchHit

DEFAULT_LIMIT = 10
MAX_LIMIT = 200


def search_garden(
    garden_home: str | Path,
    query: str,
    *,
    limit: int = DEFAULT_LIMIT,
    target_types: list[str] | None = None,
) -> list[GardenSearchHit]:
    """Search the FTS5 index at *garden_home*.

    Returns a list of ``GardenSearchHit`` objects ordered by FTS rank.

    If the index does not exist, returns an empty list (the caller can
    use ``check_garden_index()`` to distinguish "no index" from
    "no matches").

    *query* must be a non-empty string.
    *limit* is clamped to ``[1, 200]``.
    *target_types* optionally filters by entity type (e.g.
    ``["memory_card"]``).
    """
    db = Path(garden_home).resolve() / DB_FILENAME
    if not db.is_file():
        return []

    query = query.strip()
    if not query:
        return []

    lim = max(1, min(limit, MAX_LIMIT))

    conn = _open_db(garden_home)
    try:
        if not _fts_exists(conn):
            return []

        rows: list = []
        if contains_cjk(query) and _fts_has_ngram_column(conn):
            rows = _fts_cjk_rows(conn, query, lim, target_types)

        if not rows:
            sql = (
                f"SELECT target_type, target_id, title, body, metadata_json, rank "
                f"FROM {FTS_TABLE} "
                f"WHERE {FTS_TABLE} MATCH ? "
            )
            params: list = [query]
            if target_types is not None and len(target_types) > 0:
                placeholders = ", ".join("?" for _ in target_types)
                sql += f" AND target_type IN ({placeholders})"
                params.extend(target_types)
            sql += " ORDER BY rank LIMIT ?"
            params.append(lim)
            try:
                rows = conn.execute(sql, params).fetchall()
            except sqlite3.OperationalError:
                rows = []

        if not rows and contains_cjk(query) and _fts_has_ngram_column(conn):
            rows = _fts_cjk_rows(conn, query, lim, target_types)
        if not rows and _looks_cjk_query(query):
            rows = _like_rows(conn, query, lim, target_types)

        hits: list[GardenSearchHit] = []
        for r in rows:
            snippet = _snippet(r["body"] or "", query, max_len=200)
            meta = {}
            try:
                if r["metadata_json"]:
                    meta = json.loads(r["metadata_json"])
            except (json.JSONDecodeError, TypeError):
                # 索引元数据损坏时保留命中文本，不让单条记录中断搜索。
                pass

            hits.append(GardenSearchHit(
                target_type=r["target_type"],
                target_id=r["target_id"],
                title=r["title"] or "",
                snippet=snippet,
                rank=float(r["rank"]) if r["rank"] is not None else 0.0,
                metadata=meta,
            ))

        return hits
    except sqlite3.Error as exc:
        logger.warning("FTS search failed, returning empty results: %s", exc)
        return []
    finally:
        conn.close()


def _fts_cjk_rows(
    conn: sqlite3.Connection,
    query: str,
    lim: int,
    target_types: list[str] | None,
) -> list:
    """CJK 查询走 body_ngram 列 MATCH（jieba 或 bigram token）。"""
    ngram_match = build_cjk_token_query(query) or build_cjk_fts_match_query(query)
    if not ngram_match:
        return []
    ngram_sql = (
        f"SELECT target_type, target_id, title, body, metadata_json, rank "
        f"FROM {FTS_TABLE} "
        f"WHERE {FTS_TABLE} MATCH ? "
    )
    ngram_params: list = [f"body_ngram : ({ngram_match})"]
    if target_types is not None and len(target_types) > 0:
        placeholders = ", ".join("?" for _ in target_types)
        ngram_sql += f" AND target_type IN ({placeholders})"
        ngram_params.extend(target_types)
    ngram_sql += " ORDER BY rank LIMIT ?"
    ngram_params.append(lim)
    try:
        return conn.execute(ngram_sql, ngram_params).fetchall()
    except sqlite3.OperationalError as exc:
        logger.warning("CJK FTS MATCH failed, will try fallback: %s", exc)
        return []


def _looks_cjk_query(query: str) -> bool:
    return contains_cjk(query)


def _like_rows(
    conn: sqlite3.Connection,
    query: str,
    limit: int,
    target_types: list[str] | None,
) -> list[sqlite3.Row]:
    like_q = build_cjk_like_pattern(query) if contains_cjk(query) else query
    sql = (
        f"SELECT target_type, target_id, title, body, metadata_json, 0.0 AS rank "
        f"FROM {FTS_TABLE} WHERE (title LIKE ? OR body LIKE ?)"
    )
    params: list[object] = [f"%{like_q}%", f"%{like_q}%"]
    if target_types:
        placeholders = ", ".join("?" for _ in target_types)
        sql += f" AND target_type IN ({placeholders})"
        params.extend(target_types)
    sql += " LIMIT ?"
    params.append(limit)
    return conn.execute(sql, params).fetchall()


def search_garden_scoped(
    garden_home: str | Path,
    query: str,
    *,
    limit: int = DEFAULT_LIMIT,
    target_types: list[str] | None = None,
    scope: str | None = None,
    project_id: str | None = None,
    workspace_id: str | None = None,
) -> list[GardenSearchHit]:
    """Search FTS5 results and filter memory hits by product strategy scope.

    This is a scoped wrapper around ``search_garden()``.  The base FTS5
    function's signature and behavior stay unchanged.

    If no scoped arguments are provided, this returns ``search_garden()``
    unchanged.  When scoped arguments are provided, only ``memory_card`` hits
    with a saved product strategy profile are returned.  Global-user memories
    remain visible to project/workspace searches unless an explicit ``scope``
    narrows the result set.
    """
    if not any((scope, project_id, workspace_id)):
        return search_garden(garden_home, query, limit=limit, target_types=target_types)

    # Fetch extra rows before filtering so a few out-of-scope hits do not hide
    # relevant in-scope memories that FTS ranked slightly lower.
    base_hits = search_garden(
        garden_home,
        query,
        limit=min(MAX_LIMIT, max(limit, 1) * 5),
        target_types=target_types,
    )
    if not base_hits:
        return []

    filtered: list[GardenSearchHit] = []
    for hit in base_hits:
        if hit.target_type != "memory_card":
            continue
        profile = _load_strategy_profile(garden_home, hit.target_id)
        if profile is None:
            continue
        if _profile_matches_scope(
            profile_scope=str(profile.get("scope", "")),
            profile_scope_id=str(profile.get("scope_id", "")),
            requested_scope=scope,
            project_id=project_id,
            workspace_id=workspace_id,
        ):
            filtered.append(hit)
        if len(filtered) >= max(1, min(limit, MAX_LIMIT)):
            break
    return filtered


def _load_strategy_profile(garden_home: str | Path, memory_id: str) -> dict[str, object] | None:
    conn = _open_db(garden_home)
    try:
        row = conn.execute(
            "SELECT payload FROM memory_strategy_profiles WHERE memory_id = ?",
            (memory_id,),
        ).fetchone()
    except sqlite3.Error:
        return None
    finally:
        conn.close()
    if row is None:
        return None
    try:
        payload = json.loads(row["payload"])
    except (json.JSONDecodeError, TypeError):
        return None
    return payload if isinstance(payload, dict) else None


def hybrid_search_garden(
    garden_home: str | Path,
    query: str,
    *,
    limit: int = DEFAULT_LIMIT,
    target_types: list[str] | None = None,
    semantic_weight: float = 0.4,
) -> list[GardenSearchHit]:
    """Search with FTS5 + local embedding hybrid scoring.

    FTS5 results are re-ranked by combining keyword rank with embedding
    cosine similarity to the query.  When FTS5 returns no results, falls
    back to embedding-only search over all indexed rows.

    *semantic_weight* controls how much the embedding similarity
    influences the final ranking (0.0 = pure FTS5, 1.0 = pure embedding).
    """
    db = Path(garden_home).resolve() / DB_FILENAME
    if not db.is_file():
        return []

    query = query.strip()
    if not query:
        return []

    lim = max(1, min(limit, MAX_LIMIT))
    query_vec = None  # lazy

    from memory_garden.harvest.local_embedding import cosine_similarity, embed_local

    conn = _open_db(garden_home)
    try:
        if not _fts_exists(conn):
            return []

        # ── Step 1: FTS5 retrieval ───────────────────────────────
        base_sql = (
            f"SELECT target_type, target_id, title, body, metadata_json, rank "
            f"FROM {FTS_TABLE} "
            f"WHERE {FTS_TABLE} MATCH ? "
        )
        base_params: list = [query]

        if target_types is not None and len(target_types) > 0:
            placeholders = ", ".join("?" for _ in target_types)
            base_sql += f" AND target_type IN ({placeholders})"
            base_params.extend(target_types)

        base_sql += " ORDER BY rank LIMIT ?"
        base_params.append(lim * 3)  # fetch more for re-ranking

        fts_rows = conn.execute(base_sql, base_params).fetchall()

        if fts_rows:
            query_vec = embed_local(query)
            fts_scored: list[tuple[float, GardenSearchHit]] = []
            for r in fts_rows:
                body = r["body"] or ""
                body_vec = embed_local(body)
                sim = cosine_similarity(query_vec, body_vec)
                fts_rank = float(r["rank"]) if r["rank"] is not None else 1.0
                combined = (1.0 - semantic_weight) * (1.0 / (1.0 + fts_rank)) + semantic_weight * sim
                snippet = _snippet(body, query, max_len=200)
                meta = {}
                try:
                    if r["metadata_json"]:
                        meta = json.loads(r["metadata_json"])
                except (json.JSONDecodeError, TypeError):
                    # 索引元数据损坏时保留命中文本，不让单条记录中断搜索。
                    pass
                fts_scored.append((combined, GardenSearchHit(
                    target_type=r["target_type"],
                    target_id=r["target_id"],
                    title=r["title"] or "",
                    snippet=snippet,
                    rank=round(combined, 4),
                    metadata=meta,
                )))
            fts_scored.sort(key=lambda x: x[0], reverse=True)
            return [h for _, h in fts_scored[:lim]]

        # ── Step 2: FTS5 missed — embedding fallback ─────────────
        all_sql = (
            f"SELECT target_type, target_id, title, body, metadata_json "
            f"FROM {FTS_TABLE}"
        )
        all_params: list = []
        if target_types is not None and len(target_types) > 0:
            placeholders = ", ".join("?" for _ in target_types)
            all_sql += f" WHERE target_type IN ({placeholders})"
            all_params.extend(target_types)
        all_sql += f" LIMIT {max(lim * 4, 200)}"

        all_rows = conn.execute(all_sql, all_params).fetchall()
        if not all_rows:
            return []

        query_vec = embed_local(query)
        fallback_scored: list[tuple[float, GardenSearchHit]] = []
        for r in all_rows:
            body = r["body"] or ""
            body_vec = embed_local(body)
            sim = cosine_similarity(query_vec, body_vec)
            if sim < 0.05:
                continue
            snippet = _snippet(body, query, max_len=200)
            if not snippet:
                snippet = body[:200]
            meta = {}
            try:
                if r["metadata_json"]:
                    meta = json.loads(r["metadata_json"])
            except (json.JSONDecodeError, TypeError):
                # 索引元数据损坏时保留命中文本，不让单条记录中断搜索。
                pass
            fallback_scored.append((sim, GardenSearchHit(
                target_type=r["target_type"],
                target_id=r["target_id"],
                title=r["title"] or "",
                snippet=snippet,
                rank=round(sim, 4),
                metadata=meta,
            )))
        fallback_scored.sort(key=lambda x: x[0], reverse=True)
        return [h for _, h in fallback_scored[:lim]]

    except sqlite3.Error:
        return []
    finally:
        conn.close()


def _profile_matches_scope(
    *,
    profile_scope: str,
    profile_scope_id: str,
    requested_scope: str | None,
    project_id: str | None,
    workspace_id: str | None,
) -> bool:
    scope = (requested_scope or "").strip()
    project = (project_id or "").strip()
    workspace = (workspace_id or "").strip()

    if scope:
        if profile_scope != scope:
            return False
        if scope == "project" and project:
            return profile_scope_id == project
        if scope == "workspace" and workspace:
            return profile_scope_id == workspace
        return True

    if profile_scope == "global_user":
        return True
    if project and profile_scope == "project":
        return profile_scope_id == project
    if workspace and profile_scope == "workspace":
        return profile_scope_id == workspace
    return False


def _snippet(body: str, query: str, max_len: int = 200) -> str:
    """Extract a short snippet around a query term match.

    Falls back to a truncated prefix of *body* if no match is found.
    """
    if not body:
        return ""
    lower_body = body.lower()
    terms = [t.lower() for t in query.split() if len(t) >= 2]
    pos = -1
    for term in terms:
        idx = lower_body.find(term)
        if idx != -1:
            pos = idx
            break
    if pos == -1:
        return body[:max_len] + ("…" if len(body) > max_len else "")
    start = max(0, pos - 60)
    end = min(len(body), pos + max_len)
    snippet = body[start:end]
    if start > 0:
        snippet = "…" + snippet
    if end < len(body):
        snippet = snippet + "…"
    return snippet
