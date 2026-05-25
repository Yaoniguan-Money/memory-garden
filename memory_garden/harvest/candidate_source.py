"""粗召回 CandidateSource：FTS primary + bounded fallback + diagnostics。"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

from memory_garden.core.growth.lifecycle import MemoryLifecycle
from memory_garden.core.models import MemoryCard
from memory_garden.harvest.bounded_scan import MemoryCardLister, scan_memory_cards
from memory_garden.harvest.coarse_scoring import compute_coarse_lexical_score
from memory_garden.harvest.retrieval_diagnostics import get_coarse_top_m, get_product_scan_limit
from memory_garden.soil.index import check_garden_index
from memory_garden.soil.search import search_garden
from memory_garden.storage.base import NotFoundError
from memory_garden.storage.memory_card_paging import count_memory_cards

logger = logging.getLogger(__name__)

FTS_LOW_CONFIDENCE_MIN_HITS = 1


@dataclass(frozen=True)
class CoarseRecallResult:
    cards: list[MemoryCard]
    memory_ids: list[str]
    candidate_source: str
    total_available: int
    scanned_count: int
    fallback_reason: str = ""
    metadata_by_id: dict[str, dict[str, object]] | None = None


class CandidateSource(Protocol):
    def recall(self, query: str, *, top_m: int | None = None) -> CoarseRecallResult: ...


def _score_and_pick(query: str, cards: list[MemoryCard], *, top_m: int) -> list[MemoryCard]:
    scored = [(compute_coarse_lexical_score(query, card), card) for card in cards]
    scored.sort(key=lambda item: (item[0], item[1].updated_at), reverse=True)
    positive = [card for score, card in scored if score > 0.0]
    if positive:
        return positive[: max(1, top_m)]
    return [card for _score, card in scored[: max(1, top_m)]]


def _coarse_metadata(query: str, cards: list[MemoryCard], *, source: str) -> dict[str, dict[str, object]]:
    return {
        card.id: {
            "candidate_source": source,
            "coarse_lexical_score": compute_coarse_lexical_score(query, card),
            "coarse_position": index,
        }
        for index, card in enumerate(cards)
    }


class InMemoryCandidateSource:
    """有界分页扫描 + 轻量词法粗排，保留 Harvest 规则语义。"""

    def __init__(
        self,
        repository: MemoryCardLister,
        *,
        include_greenhouse: bool = False,
        max_scan: int | None = None,
    ) -> None:
        self._repository = repository
        self._include_greenhouse = include_greenhouse
        self._max_scan = max_scan if max_scan is not None else get_product_scan_limit()

    def recall(self, query: str, *, top_m: int | None = None) -> CoarseRecallResult:
        top_m = top_m if top_m is not None else get_coarse_top_m()
        scan = scan_memory_cards(
            self._repository,
            include_greenhouse=self._include_greenhouse,
            max_cards=self._max_scan,
            source="in_memory",
        )
        picked = _score_and_pick(query, scan.cards, top_m=top_m)
        return CoarseRecallResult(
            cards=picked,
            memory_ids=[card.id for card in picked],
            candidate_source="in_memory",
            total_available=scan.total_available,
            scanned_count=scan.scanned_count,
            fallback_reason=scan.diagnostics.get("fallback_reason", ""),
            metadata_by_id=_coarse_metadata(query, picked, source="in_memory"),
        )


class FtsCandidateSource:
    """Soil FTS 粗召回 memory_card。"""

    def __init__(
        self,
        garden_home,
        repository: MemoryCardLister,
        *,
        include_greenhouse: bool = False,
    ) -> None:
        self._garden_home = garden_home
        self._repository = repository
        self._include_greenhouse = include_greenhouse

    def recall(self, query: str, *, top_m: int | None = None) -> CoarseRecallResult:
        top_m = top_m if top_m is not None else get_coarse_top_m()
        lim = max(1, min(top_m, get_coarse_top_m()))
        hits = search_garden(
            self._garden_home,
            query,
            limit=lim,
            target_types=["memory_card"],
        )
        cards: list[MemoryCard] = []
        metadata_by_id: dict[str, dict[str, object]] = {}
        for hit in hits:
            try:
                card = self._repository.get_memory_card(hit.target_id)
            except NotFoundError:
                continue
            if card.lifecycle == MemoryLifecycle.greenhouse and not self._include_greenhouse:
                continue
            cards.append(card)
            position = len(cards) - 1
            metadata_by_id[card.id] = {
                "candidate_source": "fts",
                "fts_rank": hit.rank,
                "fts_position": position,
                "fts_position_score": 1.0 / float(position + 1),
                "fts_title": hit.title,
                "fts_snippet": hit.snippet,
                "fts_metadata": dict(hit.metadata),
            }
        total_available = count_memory_cards(
            self._repository,
            include_greenhouse=self._include_greenhouse,
        )
        fallback_reason = ""
        if not hits:
            fallback_reason = "fts_empty_results"
        elif not cards:
            fallback_reason = "fts_low_confidence"
        elif len(cards) < FTS_LOW_CONFIDENCE_MIN_HITS:
            fallback_reason = "fts_low_confidence"
        return CoarseRecallResult(
            cards=cards,
            memory_ids=[card.id for card in cards],
            candidate_source="fts",
            total_available=total_available,
            scanned_count=len(hits),
            fallback_reason=fallback_reason,
            metadata_by_id=metadata_by_id,
        )


def _merge_coarse_candidates(
    query: str,
    *,
    primary_cards: list[MemoryCard],
    fallback_cards: list[MemoryCard],
    top_m: int,
) -> list[MemoryCard]:
    merged: list[MemoryCard] = []
    seen: set[str] = set()
    for card in [*primary_cards, *fallback_cards]:
        if card.id in seen:
            continue
        seen.add(card.id)
        merged.append(card)
    return _score_and_pick(query, merged, top_m=top_m)


def _merge_metadata(
    primary: CoarseRecallResult,
    fallback: CoarseRecallResult,
    cards: list[MemoryCard],
) -> dict[str, dict[str, object]]:
    merged: dict[str, dict[str, object]] = {}
    for source in (primary.metadata_by_id or {}, fallback.metadata_by_id or {}):
        for memory_id, meta in source.items():
            current = dict(merged.get(memory_id, {}))
            current.update(meta)
            merged[memory_id] = current
    for index, card in enumerate(cards):
        meta = dict(merged.get(card.id, {}))
        meta.setdefault("merged_position", index)
        merged[card.id] = meta
    return merged


def _should_probe_bounded_fallback(fts_result: CoarseRecallResult) -> bool:
    if not fts_result.cards:
        return True
    if fts_result.fallback_reason:
        return True
    if fts_result.total_available <= get_product_scan_limit():
        return len(fts_result.cards) >= max(1, fts_result.total_available - 2)
    return False


def _needs_bounded_merge(
    fts_result: CoarseRecallResult,
    fallback_result: CoarseRecallResult,
    query: str,
) -> bool:
    if not fallback_result.cards:
        return False
    fts_ids = set(fts_result.memory_ids)
    best_fallback = fallback_result.cards[0]
    best_fallback_score = compute_coarse_lexical_score(query, best_fallback)
    best_fts_score = max(compute_coarse_lexical_score(query, card) for card in fts_result.cards)
    return best_fallback.id not in fts_ids and best_fallback_score > best_fts_score


class FallbackCandidateSource:
    """FTS 主路径；空结果、低置信或小库 FTS 近全命中却漏召回时 bounded 合并。"""

    def __init__(self, primary: CandidateSource, fallback: CandidateSource) -> None:
        self._primary = primary
        self._fallback = fallback

    def recall(self, query: str, *, top_m: int | None = None) -> CoarseRecallResult:
        top_m = top_m if top_m is not None else get_coarse_top_m()
        try:
            fts_result = self._primary.recall(query, top_m=top_m)
            if not _should_probe_bounded_fallback(fts_result):
                return fts_result

            fallback = self._fallback.recall(query, top_m=top_m)
            if not fts_result.cards:
                return CoarseRecallResult(
                    cards=fallback.cards,
                    memory_ids=fallback.memory_ids,
                    candidate_source="fallback",
                    total_available=fallback.total_available,
                    scanned_count=fallback.scanned_count,
                    fallback_reason=fts_result.fallback_reason or "fts_empty_results",
                    metadata_by_id=fallback.metadata_by_id,
                )

            if not _needs_bounded_merge(fts_result, fallback, query):
                return fts_result

            merged = _merge_coarse_candidates(
                query,
                primary_cards=fts_result.cards,
                fallback_cards=fallback.cards,
                top_m=top_m,
            )
            return CoarseRecallResult(
                cards=merged,
                memory_ids=[card.id for card in merged],
                candidate_source="fallback",
                total_available=fallback.total_available,
                scanned_count=fts_result.scanned_count + fallback.scanned_count,
                fallback_reason=fts_result.fallback_reason or "fts_low_confidence",
                metadata_by_id=_merge_metadata(fts_result, fallback, merged),
            )
        except Exception as exc:
            logger.warning("primary candidate source failed, falling back: %s", exc)
            fallback = self._fallback.recall(query, top_m=top_m)
            return CoarseRecallResult(
                cards=fallback.cards,
                memory_ids=fallback.memory_ids,
                candidate_source="fallback",
                total_available=fallback.total_available,
                scanned_count=fallback.scanned_count,
                fallback_reason=f"{type(exc).__name__}:{exc}",
                metadata_by_id=fallback.metadata_by_id,
            )


def select_product_candidate_source(garden_home, repository: MemoryCardLister) -> CandidateSource:
    """Product 检索：FTS 可用时 primary + bounded fallback，否则有界内存粗召回。"""
    bounded_in_memory = InMemoryCandidateSource(
        repository,
        include_greenhouse=False,
        max_scan=get_product_scan_limit(),
    )
    status = check_garden_index(garden_home)
    if status.exists and status.healthy and (status.indexed_count or 0) > 0:
        fts = FtsCandidateSource(garden_home, repository, include_greenhouse=False)
        return FallbackCandidateSource(fts, bounded_in_memory)
    return bounded_in_memory
