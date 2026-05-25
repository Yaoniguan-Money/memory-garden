"""梦境周期引擎接口：仅类型契约，无实现。"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from memory_garden.core.models import DreamRecord


@runtime_checkable
class DreamCycleEngineProtocol(Protocol):
    """规则版夜间整理：对种子与记忆卡做可审计的整合，不调用 LLM。"""

    def dream(
        self,
        seed_ids: list[str] | None = None,
        memory_ids: list[str] | None = None,
    ) -> "DreamRecord | None":
        """执行一轮梦境周期；无材料时返回 None，不写入 dream_completed 事件。"""
        ...
