"""SQLite-backed product tables for advanced memory workflows."""

from __future__ import annotations

import json
import sqlite3
import struct
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

from memory_garden.product.models import (
    ConflictArbitrationRecord,
    ForgetPlanRecord,
    ForgetProofRecord,
    MemoryEvolutionPlan,
    MemoryProposal,
    MemoryRelation,
    MemoryStrategyProfile,
    MemoryVersionRecord,
)
from memory_garden.soil.index import DB_FILENAME

T = TypeVar("T", bound=BaseModel)

# Tables accepted by _get_by_id for dynamic SQL identifiers. Values in WHERE
# clauses remain parameterized; update README/SECURITY when adding entries.
_MODEL_TABLES = {
    "memory_proposals",
    "forget_plans",
}


def db_path(garden_home: str | Path) -> Path:
    return Path(garden_home).resolve() / DB_FILENAME


class ProductMemoryStore:
    """Direct product-layer store for proposal, version, relation, and proof data."""

    def __init__(self, garden_home: str | Path, *, initialize: bool = True) -> None:
        self.root = Path(garden_home).resolve()
        self.path = db_path(self.root)
        if initialize:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        conn = self._connect()
        try:
            conn.executescript(
                """
                PRAGMA foreign_keys = ON;

                CREATE TABLE IF NOT EXISTS memory_proposals (
                    id TEXT PRIMARY KEY NOT NULL,
                    status TEXT NOT NULL,
                    created_memory_id TEXT,
                    sensitivity TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_memory_proposals_status ON memory_proposals(status);
                CREATE INDEX IF NOT EXISTS idx_memory_proposals_memory ON memory_proposals(created_memory_id);

                CREATE TABLE IF NOT EXISTS memory_versions (
                    id TEXT PRIMARY KEY NOT NULL,
                    memory_id TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_memory_versions_memory ON memory_versions(memory_id);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_memory_versions_unique ON memory_versions(memory_id, version);

                CREATE TABLE IF NOT EXISTS memory_relations (
                    id TEXT PRIMARY KEY NOT NULL,
                    relation_type TEXT NOT NULL,
                    source_memory_id TEXT NOT NULL,
                    target_memory_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_memory_relations_source ON memory_relations(source_memory_id);
                CREATE INDEX IF NOT EXISTS idx_memory_relations_target ON memory_relations(target_memory_id);

                CREATE TABLE IF NOT EXISTS provider_calls (
                    id TEXT PRIMARY KEY NOT NULL,
                    provider_name TEXT NOT NULL,
                    provider_kind TEXT NOT NULL,
                    purpose TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS memory_retrieval_events (
                    id TEXT PRIMARY KEY NOT NULL,
                    query TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS memory_embeddings (
                    memory_id TEXT NOT NULL,
                    model TEXT NOT NULL,
                    dimensions INTEGER NOT NULL,
                    content_hash TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    vector_blob BLOB NOT NULL,
                    PRIMARY KEY (memory_id, model)
                );
                CREATE INDEX IF NOT EXISTS idx_memory_embeddings_model ON memory_embeddings(model);

                CREATE TABLE IF NOT EXISTS memory_retrieval_index (
                    memory_id TEXT PRIMARY KEY NOT NULL,
                    card_tokens_json TEXT NOT NULL,
                    card_embedding_blob BLOB NOT NULL,
                    card_importance REAL NOT NULL DEFAULT 0.5,
                    card_confidence REAL NOT NULL DEFAULT 0.5,
                    card_lifecycle TEXT NOT NULL DEFAULT 'bloom',
                    card_sensitivity TEXT NOT NULL DEFAULT 'none',
                    card_tags_json TEXT NOT NULL DEFAULT '[]',
                    card_updated_at TEXT NOT NULL DEFAULT '',
                    strategy_layer TEXT NOT NULL DEFAULT '',
                    strategy_scope TEXT NOT NULL DEFAULT '',
                    strategy_scope_id TEXT NOT NULL DEFAULT '',
                    strategy_maturity TEXT NOT NULL DEFAULT '',
                    strategy_strength REAL NOT NULL DEFAULT 0.5,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS memory_strategy_profiles (
                    memory_id TEXT PRIMARY KEY NOT NULL,
                    layer TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    scope_id TEXT NOT NULL,
                    maturity TEXT NOT NULL,
                    strength REAL NOT NULL,
                    updated_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_memory_strategy_layer ON memory_strategy_profiles(layer);
                CREATE INDEX IF NOT EXISTS idx_memory_strategy_scope ON memory_strategy_profiles(scope, scope_id);
                CREATE INDEX IF NOT EXISTS idx_memory_strategy_maturity ON memory_strategy_profiles(maturity);

                CREATE TABLE IF NOT EXISTS memory_conflict_arbitrations (
                    id TEXT PRIMARY KEY NOT NULL,
                    existing_memory_id TEXT NOT NULL,
                    new_memory_id TEXT NOT NULL,
                    proposal_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_memory_conflicts_existing ON memory_conflict_arbitrations(existing_memory_id);
                CREATE INDEX IF NOT EXISTS idx_memory_conflicts_new ON memory_conflict_arbitrations(new_memory_id);
                CREATE INDEX IF NOT EXISTS idx_memory_conflicts_proposal ON memory_conflict_arbitrations(proposal_id);

                CREATE TABLE IF NOT EXISTS memory_evolution_plans (
                    id TEXT PRIMARY KEY NOT NULL,
                    memory_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_memory_evolution_memory ON memory_evolution_plans(memory_id);
                CREATE INDEX IF NOT EXISTS idx_memory_evolution_status ON memory_evolution_plans(status);

                CREATE TABLE IF NOT EXISTS forget_plans (
                    id TEXT PRIMARY KEY NOT NULL,
                    memory_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_forget_plans_memory ON forget_plans(memory_id);

                CREATE TABLE IF NOT EXISTS forget_proofs (
                    id TEXT PRIMARY KEY NOT NULL,
                    plan_id TEXT NOT NULL,
                    memory_id TEXT NOT NULL,
                    proven INTEGER NOT NULL,
                    created_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_forget_proofs_plan ON forget_proofs(plan_id);
                """
            )
            conn.commit()
        finally:
            conn.close()

    def save_proposal(
        self,
        proposal: MemoryProposal,
        *,
        conn: sqlite3.Connection | None = None,
    ) -> MemoryProposal:
        # 使用 INSERT OR REPLACE 支持 status 更新（approve/reject/edit 需覆盖同 ID）
        payload = _dump(proposal)
        own = conn is None
        if own:
            conn = self._connect()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO memory_proposals
                    (id, status, created_memory_id, sensitivity, created_at, updated_at, payload)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    proposal.id,
                    proposal.status.value,
                    proposal.created_memory_id,
                    proposal.sensitivity.value,
                    proposal.created_at.isoformat(),
                    proposal.updated_at.isoformat(),
                    payload,
                ),
            )
            if own:
                conn.commit()
            return proposal
        finally:
            if own:
                conn.close()

    def get_proposal(self, proposal_id: str) -> MemoryProposal:
        return self._get_by_id("memory_proposals", proposal_id, MemoryProposal)

    def list_proposals(self, *, status: str | None = None, limit: int = 100) -> list[MemoryProposal]:
        conn = self._connect()
        try:
            sql = "SELECT payload FROM memory_proposals WHERE 1 = 1"
            params: list[Any] = []
            if status is not None:
                sql += " AND status = ?"
                params.append(status)
            sql += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            return [_load(MemoryProposal, row["payload"]) for row in conn.execute(sql, params).fetchall()]
        finally:
            conn.close()

    def save_version(
        self,
        version: MemoryVersionRecord,
        *,
        _retries: int = 5,
        conn: sqlite3.Connection | None = None,
    ) -> MemoryVersionRecord:
        own = conn is None
        if own:
            conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO memory_versions (id, memory_id, version, created_at, payload)
                VALUES (?, ?, ?, ?, ?)
                """,
                (version.id, version.memory_id, version.version, version.created_at.isoformat(), _dump(version)),
            )
            if own:
                conn.commit()
            return version
        except sqlite3.IntegrityError:
            if _retries <= 0:
                raise
            row = conn.execute(
                "SELECT MAX(version) AS max_version FROM memory_versions WHERE memory_id = ?",
                (version.memory_id,),
            ).fetchone()
            next_ver = int(row["max_version"] or 0) + 1
            bumped = version.model_copy(update={"version": next_ver})
            return self.save_version(bumped, _retries=_retries - 1, conn=conn)
        finally:
            if own:
                conn.close()

    def next_version_number(self, memory_id: str, *, conn: sqlite3.Connection | None = None) -> int:
        own = conn is None
        if own:
            conn = self._connect()
        try:
            row = conn.execute(
                "SELECT MAX(version) AS max_version FROM memory_versions WHERE memory_id = ?",
                (memory_id,),
            ).fetchone()
            return int(row["max_version"] or 0) + 1
        finally:
            if own:
                conn.close()

    def list_versions(self, memory_id: str) -> list[MemoryVersionRecord]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT payload FROM memory_versions WHERE memory_id = ? ORDER BY version",
                (memory_id,),
            ).fetchall()
            return [_load(MemoryVersionRecord, row["payload"]) for row in rows]
        finally:
            conn.close()

    def save_relation(
        self,
        relation: MemoryRelation,
        *,
        conn: sqlite3.Connection | None = None,
    ) -> MemoryRelation:
        own = conn is None
        if own:
            conn = self._connect()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO memory_relations
                    (id, relation_type, source_memory_id, target_memory_id, created_at, payload)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    relation.id,
                    relation.relation_type.value,
                    relation.source_memory_id,
                    relation.target_memory_id,
                    relation.created_at.isoformat(),
                    _dump(relation),
                ),
            )
            if own:
                conn.commit()
            return relation
        finally:
            if own:
                conn.close()

    def list_relations(self, memory_id: str) -> list[MemoryRelation]:
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT payload FROM memory_relations
                WHERE source_memory_id = ? OR target_memory_id = ?
                ORDER BY created_at DESC
                """,
                (memory_id, memory_id),
            ).fetchall()
            return [_load(MemoryRelation, row["payload"]) for row in rows]
        finally:
            conn.close()

    def save_forget_plan(self, plan: ForgetPlanRecord) -> ForgetPlanRecord:
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO forget_plans (id, memory_id, status, created_at, payload)
                VALUES (?, ?, ?, ?, ?)
                """,
                (plan.id, plan.memory_id, plan.status, plan.created_at.isoformat(), _dump(plan)),
            )
            conn.commit()
            return plan
        finally:
            conn.close()

    def get_forget_plan(self, plan_id: str) -> ForgetPlanRecord:
        return self._get_by_id("forget_plans", plan_id, ForgetPlanRecord)

    def save_forget_proof(self, proof: ForgetProofRecord) -> ForgetProofRecord:
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO forget_proofs
                    (id, plan_id, memory_id, proven, created_at, payload)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (proof.id, proof.plan_id, proof.memory_id, int(proof.proven), proof.created_at.isoformat(), _dump(proof)),
            )
            conn.commit()
            return proof
        finally:
            conn.close()

    def record_provider_call(self, payload: dict[str, Any]) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO provider_calls
                    (id, provider_name, provider_kind, purpose, created_at, payload)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["id"],
                    payload.get("provider_name", ""),
                    payload.get("provider_kind", ""),
                    payload.get("purpose", ""),
                    payload.get("created_at", ""),
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def record_retrieval_event(self, payload: dict[str, Any]) -> None:
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT INTO memory_retrieval_events (id, query, created_at, payload)
                VALUES (?, ?, ?, ?)
                """,
                (
                    payload["id"],
                    payload.get("query", ""),
                    payload.get("created_at", ""),
                    json.dumps(payload, ensure_ascii=False, sort_keys=True),
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def save_memory_embedding(
        self,
        *,
        memory_id: str,
        model: str,
        vector: list[float],
        content_hash: str,
        updated_at: str,
    ) -> None:
        dims = len(vector)
        blob = struct.pack(f"<{dims}d", *vector)
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO memory_embeddings
                    (memory_id, model, dimensions, content_hash, updated_at, vector_blob)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    memory_id,
                    model,
                    dims,
                    content_hash,
                    updated_at,
                    blob,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def get_memory_embedding(
        self,
        *,
        memory_id: str,
        model: str,
        content_hash: str | None = None,
    ) -> list[float] | None:
        conn = self._connect()
        try:
            row = conn.execute(
                """
                SELECT content_hash, vector_blob FROM memory_embeddings
                WHERE memory_id = ? AND model = ?
                """,
                (memory_id, model),
            ).fetchone()
            if row is None:
                return None
            if content_hash is not None and row["content_hash"] != content_hash:
                return None
            blob = row["vector_blob"]
            if blob is None:
                return None
            return _unpack_vector(blob)
        finally:
            conn.close()

    def list_memory_embeddings(self, *, model: str, limit: int = 1000) -> dict[str, list[float]]:
        conn = self._connect()
        try:
            rows = conn.execute(
                """
                SELECT memory_id, vector_blob FROM memory_embeddings
                WHERE model = ?
                LIMIT ?
                """,
                (model, limit),
            ).fetchall()
            out: dict[str, list[float]] = {}
            for row in rows:
                blob = row["vector_blob"]
                if blob is None:
                    continue
                vector = _unpack_vector(blob)
                if vector is not None:
                    out[row["memory_id"]] = vector
            return out
        finally:
            conn.close()

    def list_memory_embeddings_for_ids(
        self,
        *,
        model: str,
        memory_ids: set[str],
    ) -> dict[str, list[float]]:
        if not memory_ids:
            return {}
        conn = self._connect()
        try:
            placeholders = ", ".join("?" for _ in memory_ids)
            rows = conn.execute(
                f"SELECT memory_id, vector_blob FROM memory_embeddings WHERE model = ? AND memory_id IN ({placeholders})",
                [model, *memory_ids],
            ).fetchall()
            out: dict[str, list[float]] = {}
            for row in rows:
                blob = row["vector_blob"]
                if blob is None:
                    continue
                vector = _unpack_vector(blob)
                if vector is not None:
                    out[row["memory_id"]] = vector
            return out
        finally:
            conn.close()

    def delete_memory_embedding(self, memory_id: str, *, model: str | None = None) -> int:
        conn = self._connect()
        try:
            if model is None:
                cursor = conn.execute("DELETE FROM memory_embeddings WHERE memory_id = ?", (memory_id,))
            else:
                cursor = conn.execute(
                    "DELETE FROM memory_embeddings WHERE memory_id = ? AND model = ?",
                    (memory_id, model),
                )
            conn.commit()
            return int(cursor.rowcount or 0)
        finally:
            conn.close()

    def save_retrieval_index(
        self,
        *,
        memory_id: str,
        card_tokens: list[str],
        card_embedding: list[float],
        card_importance: float,
        card_confidence: float,
        card_lifecycle: str,
        card_sensitivity: str,
        card_tags: list[str],
        card_updated_at: str,
        strategy_layer: str,
        strategy_scope: str,
        strategy_scope_id: str,
        strategy_maturity: str,
        strategy_strength: float,
        updated_at: str,
    ) -> None:
        dims = len(card_embedding)
        embedding_blob = struct.pack(f"<{dims}d", *card_embedding)
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO memory_retrieval_index
                    (memory_id, card_tokens_json, card_embedding_blob,
                     card_importance, card_confidence, card_lifecycle, card_sensitivity,
                     card_tags_json, card_updated_at,
                     strategy_layer, strategy_scope, strategy_scope_id, strategy_maturity, strategy_strength,
                     updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    memory_id,
                    json.dumps(card_tokens, ensure_ascii=False),
                    embedding_blob,
                    card_importance,
                    card_confidence,
                    card_lifecycle,
                    card_sensitivity,
                    json.dumps(card_tags, ensure_ascii=False),
                    card_updated_at,
                    strategy_layer,
                    strategy_scope,
                    strategy_scope_id,
                    strategy_maturity,
                    strategy_strength,
                    updated_at,
                ),
            )
            conn.commit()
        finally:
            conn.close()

    def bulk_get_retrieval_index(
        self,
        memory_ids: set[str],
    ) -> dict[str, dict[str, Any]]:
        if not memory_ids:
            return {}
        conn = self._connect()
        try:
            placeholders = ", ".join("?" for _ in memory_ids)
            rows = conn.execute(
                f"SELECT * FROM memory_retrieval_index WHERE memory_id IN ({placeholders})",
                list(memory_ids),
            ).fetchall()
            out: dict[str, dict[str, Any]] = {}
            for row in rows:
                mid = row["memory_id"]
                blob = row["card_embedding_blob"]
                embedding = _unpack_vector(blob) if blob is not None else []
                tokens_raw: Any = json.loads(row["card_tokens_json"])
                tags_raw: Any = json.loads(row["card_tags_json"])
                out[mid] = {
                    "card_tokens": set(tokens_raw) if isinstance(tokens_raw, list) else set(),
                    "card_embedding": embedding or [],
                    "card_importance": float(row["card_importance"]),
                    "card_confidence": float(row["card_confidence"]),
                    "card_lifecycle": row["card_lifecycle"],
                    "card_sensitivity": row["card_sensitivity"],
                    "card_tags": list(tags_raw) if isinstance(tags_raw, list) else [],
                    "card_updated_at": row["card_updated_at"],
                    "strategy_layer": row["strategy_layer"],
                    "strategy_scope": row["strategy_scope"],
                    "strategy_scope_id": row["strategy_scope_id"],
                    "strategy_maturity": row["strategy_maturity"],
                    "strategy_strength": float(row["strategy_strength"]),
                }
            return out
        finally:
            conn.close()

    def delete_retrieval_index(self, memory_id: str) -> int:
        conn = self._connect()
        try:
            cursor = conn.execute("DELETE FROM memory_retrieval_index WHERE memory_id = ?", (memory_id,))
            conn.commit()
            return int(cursor.rowcount or 0)
        finally:
            conn.close()

    def save_strategy_profile(
        self,
        profile: MemoryStrategyProfile,
        *,
        conn: sqlite3.Connection | None = None,
    ) -> MemoryStrategyProfile:
        own = conn is None
        if own:
            conn = self._connect()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO memory_strategy_profiles
                    (memory_id, layer, scope, scope_id, maturity, strength, updated_at, payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    profile.memory_id,
                    profile.layer.value,
                    profile.scope.value,
                    profile.scope_id,
                    profile.maturity.value,
                    profile.strength,
                    profile.updated_at.isoformat(),
                    _dump(profile),
                ),
            )
            if own:
                conn.commit()
            return profile
        finally:
            if own:
                conn.close()

    def get_strategy_profile(self, memory_id: str) -> MemoryStrategyProfile | None:
        conn = self._connect()
        try:
            try:
                row = conn.execute(
                    "SELECT payload FROM memory_strategy_profiles WHERE memory_id = ?",
                    (memory_id,),
                ).fetchone()
            except sqlite3.OperationalError as exc:
                if "no such table" in str(exc).casefold():
                    return None
                raise
            return None if row is None else _load(MemoryStrategyProfile, row["payload"])
        finally:
            conn.close()

    def list_strategy_profiles(
        self,
        *,
        layer: str | None = None,
        scope: str | None = None,
        scope_id: str | None = None,
        maturity: str | None = None,
        limit: int = 500,
    ) -> list[MemoryStrategyProfile]:
        conn = self._connect()
        try:
            sql = "SELECT payload FROM memory_strategy_profiles WHERE 1 = 1"
            params: list[Any] = []
            if layer is not None:
                sql += " AND layer = ?"
                params.append(layer)
            if scope is not None:
                sql += " AND scope = ?"
                params.append(scope)
            if scope_id is not None:
                sql += " AND scope_id = ?"
                params.append(scope_id)
            if maturity is not None:
                sql += " AND maturity = ?"
                params.append(maturity)
            sql += " ORDER BY updated_at DESC LIMIT ?"
            params.append(limit)
            return [_load(MemoryStrategyProfile, row["payload"]) for row in conn.execute(sql, params).fetchall()]
        finally:
            conn.close()

    def save_conflict_arbitration(
        self,
        record: ConflictArbitrationRecord,
        *,
        conn: sqlite3.Connection | None = None,
    ) -> ConflictArbitrationRecord:
        own = conn is None
        if own:
            conn = self._connect()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO memory_conflict_arbitrations
                    (id, existing_memory_id, new_memory_id, proposal_id, status, created_at, payload)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.existing_memory_id,
                    record.new_memory_id,
                    record.proposal_id,
                    record.status.value,
                    record.created_at.isoformat(),
                    _dump(record),
                ),
            )
            if own:
                conn.commit()
            return record
        finally:
            if own:
                conn.close()

    def list_conflict_arbitrations(self, memory_id: str | None = None, *, limit: int = 100) -> list[ConflictArbitrationRecord]:
        conn = self._connect()
        try:
            sql = "SELECT payload FROM memory_conflict_arbitrations WHERE 1 = 1"
            params: list[Any] = []
            if memory_id is not None:
                sql += " AND (existing_memory_id = ? OR new_memory_id = ?)"
                params.extend([memory_id, memory_id])
            sql += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            return [_load(ConflictArbitrationRecord, row["payload"]) for row in conn.execute(sql, params).fetchall()]
        finally:
            conn.close()

    def save_evolution_plan(self, plan: MemoryEvolutionPlan) -> MemoryEvolutionPlan:
        conn = self._connect()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO memory_evolution_plans
                    (id, memory_id, action, status, created_at, payload)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    plan.id,
                    plan.memory_id,
                    plan.action.value,
                    plan.status,
                    plan.created_at.isoformat(),
                    _dump(plan),
                ),
            )
            conn.commit()
            return plan
        finally:
            conn.close()

    def list_evolution_plans(
        self,
        memory_id: str | None = None,
        *,
        status: str | None = None,
        limit: int = 100,
    ) -> list[MemoryEvolutionPlan]:
        conn = self._connect()
        try:
            sql = "SELECT payload FROM memory_evolution_plans WHERE 1 = 1"
            params: list[Any] = []
            if memory_id is not None:
                sql += " AND memory_id = ?"
                params.append(memory_id)
            if status is not None:
                sql += " AND status = ?"
                params.append(status)
            sql += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            return [_load(MemoryEvolutionPlan, row["payload"]) for row in conn.execute(sql, params).fetchall()]
        finally:
            conn.close()

    def proposals_for_memory(self, memory_id: str) -> list[MemoryProposal]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT payload FROM memory_proposals WHERE created_memory_id = ? ORDER BY created_at DESC",
                (memory_id,),
            ).fetchall()
            return [_load(MemoryProposal, row["payload"]) for row in rows]
        finally:
            conn.close()

    def delete_memory_products(self, memory_id: str) -> list[str]:
        """删除与指定 memory_id 关联的所有产品存储记录。

        在硬遗忘执行后调用，防止孤立行残留。
        Returns:
            被清理的表名列表。
        """
        conn = self._connect()
        cleaned: list[str] = []
        try:
            tables_columns: list[tuple[str, str]] = [
                ("memory_versions", "memory_id"),
                ("memory_strategy_profiles", "memory_id"),
                ("memory_evolution_plans", "memory_id"),
                ("memory_embeddings", "memory_id"),
                ("memory_proposals", "created_memory_id"),
                ("forget_plans", "memory_id"),
                ("forget_proofs", "memory_id"),
                ("memory_relations", "source_memory_id"),
                ("memory_relations", "target_memory_id"),
                ("memory_retrieval_index", "memory_id"),
                ("memory_conflict_arbitrations", "existing_memory_id"),
                ("memory_conflict_arbitrations", "new_memory_id"),
            ]
            for table, column in tables_columns:
                try:
                    cursor = conn.execute(
                        f"DELETE FROM {table} WHERE {column} = ?",
                        (memory_id,),
                    )
                    if cursor.rowcount > 0:
                        cleaned.append(f"{table}.{column}")
                except sqlite3.OperationalError:
                    # 表或列可能不存在（旧版 schema），跳过
                    pass
            conn.commit()
        finally:
            conn.close()
        return cleaned

    def purge_retrieval_events_for_memory(self, memory_id: str) -> int:
        conn = self._connect()
        try:
            rows = conn.execute("SELECT id, payload FROM memory_retrieval_events").fetchall()
            event_ids: list[str] = []
            for row in rows:
                try:
                    payload = json.loads(row["payload"])
                except (TypeError, json.JSONDecodeError):
                    continue
                if _retrieval_event_references_memory(payload, memory_id):
                    event_ids.append(row["id"])
            if not event_ids:
                return 0
            cursor = conn.executemany(
                "DELETE FROM memory_retrieval_events WHERE id = ?",
                [(event_id,) for event_id in event_ids],
            )
            conn.commit()
            return len(event_ids) if cursor.rowcount == -1 else cursor.rowcount
        finally:
            conn.close()

    def _get_by_id(self, table: str, row_id: str, model: type[T]) -> T:
        if table not in _MODEL_TABLES:
            raise ValueError(f"unsupported product table: {table}")
        conn = self._connect()
        try:
            row = conn.execute(f"SELECT payload FROM {table} WHERE id = ?", (row_id,)).fetchone()
            if row is None:
                raise KeyError(row_id)
            return _load(model, row["payload"])
        finally:
            conn.close()


def _dump(model: BaseModel) -> str:
    return json.dumps(model.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)


def _load(model: type[T], payload: str) -> T:
    return model.model_validate(json.loads(payload))


def _unpack_vector(blob: bytes, elem_count: int | None = None) -> list[float] | None:
    """struct.unpack BLOB，兼容遗留 JSON TEXT 字段。"""
    try:
        if elem_count is None:
            if len(blob) % 8 != 0:
                return None
            elem_count = len(blob) // 8
        return list(struct.unpack(f"<{elem_count}d", blob))
    except (struct.error, TypeError):
        return None


def _retrieval_event_references_memory(payload: dict[str, Any], memory_id: str) -> bool:
    for key in ("memory_ids", "blocked_memory_ids"):
        value = payload.get(key)
        if isinstance(value, list) and any(item == memory_id for item in value):
            return True
    return False
