"""花园日志（Garden Journal）：领域事件的创建与查询，不承担业务裁决。"""

from __future__ import annotations

from memory_garden.core.models import GardenEvent, GardenEventType, GardenObjectType
from memory_garden.storage.base import GardenRepository


class GardenJournal:
    """围绕 GardenRepository 的领域日志门面：仅记录与读取 GardenEvent，不改写业务实体。"""

    def __init__(self, repository: GardenRepository) -> None:
        self._repository = repository

    def record_event(
        self,
        event_type: GardenEventType,
        object_type: GardenObjectType,
        object_id: str,
        summary: str,
        metadata: dict | None = None,
    ) -> GardenEvent:
        """构造 GardenEvent 并持久化；metadata 未传入时使用空字典。"""
        event = GardenEvent(
            event_type=event_type,
            object_type=object_type,
            object_id=object_id,
            summary=summary,
            metadata=dict(metadata) if metadata is not None else {},
        )
        return self._repository.save_garden_event(event)

    def recent_events(self, limit: int = 20) -> list[GardenEvent]:
        """返回最近若干条花园事件，语义委托给仓储列表接口。"""
        return self._repository.list_garden_events(limit=limit)
