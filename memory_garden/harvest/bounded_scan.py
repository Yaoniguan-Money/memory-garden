"""分页扫描 MemoryCard 列表，附带 retrieval diagnostics。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from memory_garden.core.growth.lifecycle import MemoryLifecycle
from memory_garden.core.models import MemoryCard
from memory_garden.harvest.retrieval_diagnostics import (
    RETRIEVAL_DIAGNOSTICS_KEY,
    build_retrieval_diagnostics,
    get_product_scan_limit,
)
from memory_garden.runtime.session import TurnContext
from memory_garden.storage.memory_card_paging import count_memory_cards, list_memory_cards_page


class MemoryCardLister(Protocol):
    def list_memory_cards(
        self,
        lifecycle: MemoryLifecycle | None = None,
        include_greenhouse: bool = False,
        limit: int | None = None,
    ) -> list[MemoryCard]: ...


@dataclass(frozen=True)
class MemoryCardScanResult:
    cards: list[MemoryCard]
    diagnostics: dict[str, Any]
    truncated: bool
    total_available: int
    scanned_count: int


def scan_memory_cards(
    repository: MemoryCardLister,
    *,
    lifecycle: MemoryLifecycle | None = None,
    include_greenhouse: bool = False,
    page_size: int | None = None,
    max_cards: int | None = None,
    match_fn: Callable[[MemoryCard], bool] | None = None,
    source: str = "bounded_scan",
) -> MemoryCardScanResult:
    """按页扫描记忆卡；可选提前终止或限制最大扫描条数。"""
    resolved_page_size = page_size if page_size is not None else get_product_scan_limit()
    if resolved_page_size < 1:
        raise ValueError("page_size must be >= 1")

    collected: list[MemoryCard] = []
    offset = 0
    complete_scan = False

    while True:
        page = list_memory_cards_page(
            repository,
            lifecycle=lifecycle,
            include_greenhouse=include_greenhouse,
            limit=resolved_page_size,
            offset=offset,
        )
        if not page:
            complete_scan = True
            break

        for card in page:
            collected.append(card)
            if match_fn is not None and match_fn(card):
                scanned_count = len(collected)
                total_available = count_memory_cards(
                    repository,
                    lifecycle=lifecycle,
                    include_greenhouse=include_greenhouse,
                )
                diagnostics = build_retrieval_diagnostics(
                    total_available=total_available,
                    scanned_count=scanned_count,
                    candidate_count=scanned_count,
                    source=source,
                )
                return MemoryCardScanResult(
                    cards=list(collected),
                    diagnostics=diagnostics,
                    truncated=scanned_count < total_available,
                    total_available=total_available,
                    scanned_count=scanned_count,
                )
            if max_cards is not None and len(collected) >= max_cards:
                break

        if max_cards is not None and len(collected) >= max_cards:
            break
        if len(page) < resolved_page_size:
            complete_scan = True
            break
        offset += resolved_page_size

    scanned_count = len(collected)
    if complete_scan and (max_cards is None or scanned_count < max_cards):
        total_available = scanned_count
    else:
        total_available = count_memory_cards(
            repository,
            lifecycle=lifecycle,
            include_greenhouse=include_greenhouse,
        )

    truncated = scanned_count < total_available
    fallback_reason = ""
    if truncated and max_cards is not None and scanned_count >= max_cards:
        fallback_reason = "scan_limit_reached"

    diagnostics = build_retrieval_diagnostics(
        total_available=total_available,
        scanned_count=scanned_count,
        candidate_count=scanned_count,
        source=source,
        fallback_reason=fallback_reason,
    )
    cards_out = collected[:max_cards] if max_cards is not None else collected
    return MemoryCardScanResult(
        cards=cards_out,
        diagnostics=diagnostics,
        truncated=truncated,
        total_available=total_available,
        scanned_count=scanned_count,
    )


def inject_scan_metadata_into_turn(turn: TurnContext, scan: MemoryCardScanResult) -> None:
    """将扫描 diagnostics 写入回合 metadata，供 Harvest 流水线读取。"""
    meta = dict(turn.metadata or {})
    meta[RETRIEVAL_DIAGNOSTICS_KEY] = dict(scan.diagnostics)
    meta["total_available"] = scan.total_available
    meta["truncated"] = scan.truncated
    meta["retrieval_source"] = scan.diagnostics.get("source", "runtime_memory_provider")
    turn.metadata = meta


def create_bounded_runtime_memory_provider(
    repository: MemoryCardLister,
    *,
    include_greenhouse: bool = False,
    page_size: int | None = None,
) -> Callable[[TurnContext], list[MemoryCard]]:
    """Runtime 默认记忆供给：单页 bounded scan + turn metadata diagnostics。"""
    resolved = page_size if page_size is not None else get_product_scan_limit()

    def provider(turn: TurnContext) -> list[MemoryCard]:
        scan = scan_memory_cards(
            repository,
            include_greenhouse=include_greenhouse,
            page_size=resolved,
            max_cards=resolved,
            source="runtime_memory_provider",
        )
        inject_scan_metadata_into_turn(turn, scan)
        return list(scan.cards)

    return provider
