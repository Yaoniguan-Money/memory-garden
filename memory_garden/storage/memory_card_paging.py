"""MemoryCard 分页与计数 helper（不扩展 GardenRepository 公开契约）。"""

from __future__ import annotations

from typing import Any, Protocol

from memory_garden.core.growth.lifecycle import MemoryLifecycle
from memory_garden.core.models import MemoryCard


class MemoryCardCounter(Protocol):
    def count_memory_cards(
        self,
        lifecycle: MemoryLifecycle | None = None,
        include_greenhouse: bool = False,
    ) -> int: ...


class MemoryCardPageLister(Protocol):
    def list_memory_cards_paged(
        self,
        *,
        lifecycle: MemoryLifecycle | None = None,
        include_greenhouse: bool = False,
        limit: int,
        offset: int = 0,
    ) -> list[MemoryCard]: ...


def count_memory_cards(
    repository: Any,
    *,
    lifecycle: MemoryLifecycle | None = None,
    include_greenhouse: bool = False,
) -> int:
    """优先使用仓储 COUNT 查询，避免反序列化全库。"""
    counter = getattr(repository, "count_memory_cards", None)
    if callable(counter):
        return int(
            counter(
                lifecycle=lifecycle,
                include_greenhouse=include_greenhouse,
            )
        )
    return len(
        repository.list_memory_cards(
            lifecycle=lifecycle,
            include_greenhouse=include_greenhouse,
            limit=None,
        )
    )


def list_memory_cards_page(
    repository: Any,
    *,
    lifecycle: MemoryLifecycle | None = None,
    include_greenhouse: bool = False,
    limit: int,
    offset: int = 0,
) -> list[MemoryCard]:
    """按页读取记忆卡；SQLite 走内部 paging，Fake 仓储实现同名 helper。"""
    paged = getattr(repository, "list_memory_cards_paged", None)
    if callable(paged):
        return paged(
            lifecycle=lifecycle,
            include_greenhouse=include_greenhouse,
            limit=limit,
            offset=offset,
        )
    rows = repository.list_memory_cards(
        lifecycle=lifecycle,
        include_greenhouse=include_greenhouse,
        limit=None,
    )
    start = max(0, offset)
    return rows[start : start + limit]
