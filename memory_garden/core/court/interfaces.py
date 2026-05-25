"""法庭引擎抽象边界（Protocol），便于后续替换实现。"""

from __future__ import annotations

from typing import Protocol

from memory_garden.core.models import CourtCase, Seed


class MemoryCourtEngineProtocol(Protocol):
    """规则版或未来的 LLM 版引擎均应支持的对外契约。"""

    def open_case(self, seed: Seed) -> CourtCase:
        """对单颗种子开庭并产出持久化 CourtCase。"""

    def open_cases(self, seeds: list[Seed]) -> list[CourtCase]:
        """批量开庭，顺序与输入一致。"""
