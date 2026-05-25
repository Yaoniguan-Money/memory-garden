"""冲突检测与仲裁编排服务。"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any, Protocol

from memory_garden.core.models import MemoryCard
from memory_garden.core.text_utils import card_text, tokenize_text
from memory_garden.harvest.bounded_scan import scan_memory_cards
from memory_garden.harvest.local_embedding import cosine_similarity
from memory_garden.harvest.retrieval_diagnostics import RETRIEVAL_DIAGNOSTICS_KEY
from memory_garden.product.models import (
    MemoryProposal,
    MemoryRelation,
    MemoryRelationType,
    utc_now,
)
from memory_garden.product.storage import ProductMemoryStore
from memory_garden.product.strategy import MemoryStrategyEngine
from memory_garden.runtime_config import (
    ConflictDetectionConfig,
    default_garden_runtime_config,
    resolved_contradiction_pairs,
)


def contradiction_score(
    a: str,
    b: str,
    *,
    config: ConflictDetectionConfig | None = None,
    pairs: tuple[tuple[str, str], ...] | None = None,
) -> float:
    """词表对立命中累计分数。"""
    cfg = config or default_garden_runtime_config().conflict
    word_pairs = pairs if pairs is not None else resolved_contradiction_pairs(cfg)
    lower_a = a.casefold()
    lower_b = b.casefold()
    score = 0.0
    for x, y in word_pairs:
        if (x in lower_a and y in lower_b) or (y in lower_a and x in lower_b):
            score += cfg.pair_score
    return score


def looks_contradictory(
    a: str,
    b: str,
    *,
    config: ConflictDetectionConfig | None = None,
) -> bool:
    cfg = config or default_garden_runtime_config().conflict
    return contradiction_score(a, b, config=cfg) > cfg.conflict_threshold


def _embedding_conflict_boost(
    proposal_text: str,
    card_text_value: str,
    embedding_provider: Any,
    *,
    config: ConflictDetectionConfig,
) -> float:
    """同主题高相似 + 已有词表信号时加分。"""
    try:
        vectors = getattr(embedding_provider.embed_texts([proposal_text, card_text_value]), "vectors", None)
        if vectors is None:
            result = embedding_provider.embed_texts([proposal_text, card_text_value])
            vectors = getattr(result, "vectors", result)
        if not isinstance(vectors, list) or len(vectors) < 2:
            return 0.0
        sim = cosine_similarity(list(vectors[0]), list(vectors[1]))
        if sim >= config.embedding_similarity_threshold:
            return config.embedding_boost
    except Exception:
        return 0.0
    return 0.0


class MemoryRepository(Protocol):
    def get_memory_card(self, memory_id: str) -> MemoryCard: ...

    def list_memory_cards(
        self,
        lifecycle: object | None = None,
        include_greenhouse: bool = False,
        limit: int | None = None,
    ) -> list[MemoryCard]: ...


@dataclass
class ConflictScanResult:
    proposal: MemoryProposal
    diagnostics: dict[str, Any]


class ConflictService:
    """提案冲突检测与 approve 阶段仲裁持久化。"""

    def __init__(
        self,
        *,
        repository: MemoryRepository,
        store: ProductMemoryStore,
        strategy: MemoryStrategyEngine,
        conflict_config: ConflictDetectionConfig | None = None,
    ) -> None:
        self._repository = repository
        self._store = store
        self._strategy = strategy
        self._conflict_config = conflict_config or default_garden_runtime_config().conflict
        self._pairs = resolved_contradiction_pairs(self._conflict_config)

    def annotate_proposal(
        self,
        proposal: MemoryProposal,
        *,
        embedding_provider: Any | None = None,
    ) -> MemoryProposal:
        cfg = self._conflict_config
        duplicates: list[str] = []
        conflicts: list[str] = []
        proposal_tokens = set(tokenize_text(f"{proposal.title} {proposal.essence} {' '.join(proposal.tags)}"))
        proposal_text = f"{proposal.title} {proposal.essence}"
        scan = scan_memory_cards(
            self._repository,
            include_greenhouse=True,
            source="product_conflict_scan",
        )
        for mem in scan.cards:
            card_tokens = set(tokenize_text(card_text(mem)))
            overlap = len(proposal_tokens & card_tokens)
            if overlap >= cfg.duplicate_token_overlap or proposal.title.casefold() == mem.title.casefold():
                duplicates.append(mem.id)
            mem_text = card_text(mem)
            score = contradiction_score(
                f"{proposal.essence} {' '.join(proposal.tags)}",
                mem_text,
                config=cfg,
                pairs=self._pairs,
            )
            if embedding_provider is not None and score > 0.0:
                score += _embedding_conflict_boost(proposal_text, mem_text, embedding_provider, config=cfg)
            if score > cfg.conflict_threshold:
                conflicts.append(mem.id)
        meta = dict(proposal.metadata)
        meta[RETRIEVAL_DIAGNOSTICS_KEY] = scan.diagnostics
        return proposal.model_copy(
            update={
                "duplicate_memory_ids": duplicates,
                "conflict_memory_ids": conflicts,
                "metadata": meta,
            }
        )

    def persist_approval_conflicts(
        self,
        proposal: MemoryProposal,
        new_memory_id: str,
        *,
        conn: sqlite3.Connection | None = None,
    ) -> None:
        """写入 duplicate 关系与 conflict 仲裁记录（每条冲突仅一次）。"""
        for duplicate_id in proposal.duplicate_memory_ids:
            self._store.save_relation(
                MemoryRelation(
                    relation_type=MemoryRelationType.duplicates,
                    source_memory_id=new_memory_id,
                    target_memory_id=duplicate_id,
                    reason="Proposal appeared to duplicate an existing memory",
                    confidence=0.75,
                ),
                conn=conn,
            )
        seen_conflicts: set[str] = set()
        for conflict_id in proposal.conflict_memory_ids:
            if conflict_id in seen_conflicts:
                continue
            seen_conflicts.add(conflict_id)
            existing = self._repository.get_memory_card(conflict_id)
            existing_profile = self._store.get_strategy_profile(conflict_id)
            arbitration = self._strategy.arbitrate_conflict(
                proposal=proposal,
                existing=existing,
                existing_profile=existing_profile,
                new_memory_id=new_memory_id,
            )
            self._store.save_conflict_arbitration(arbitration, conn=conn)
            self._store.save_relation(self._strategy.relation_for_arbitration(arbitration), conn=conn)
            if existing_profile is not None:
                self._store.save_strategy_profile(
                    existing_profile.model_copy(
                        update={
                            "contradiction_count": existing_profile.contradiction_count + 1,
                            "updated_at": utc_now(),
                        }
                    ),
                    conn=conn,
                )
