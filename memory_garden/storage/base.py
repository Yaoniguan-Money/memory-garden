"""本地存储抽象：仅接口与异常，不包含具体后端实现。"""

from __future__ import annotations

from abc import ABC, abstractmethod

from memory_garden.core.growth.lifecycle import MemoryLifecycle
from memory_garden.core.models import (
    CompostRecord,
    CourtCase,
    DreamRecord,
    GardenEvent,
    GardenEventType,
    GardenObjectType,
    GreenhouseRecord,
    MemoryCard,
    PruningRecord,
    Seed,
    SeedStatus,
)


class RepositoryError(Exception):
    """仓储层通用错误（读写失败、约束违反等）。"""


class NotFoundError(RepositoryError):
    """按主键查询不到实体时抛出。"""


class DuplicateIdError(RepositoryError):
    """创建或冲突写入时主键已存在（具体语义由实现约定）。"""


class GardenRepository(ABC):
    """花园持久化契约：由本地 SQLite 等实现，不含业务编排逻辑。"""

    # —— Seed —— #

    @abstractmethod
    def save_seed(self, seed: Seed) -> Seed:
        """首次插入种子；主键已存在则抛出 DuplicateIdError（修改请用 update_seed）。"""

    @abstractmethod
    def get_seed(self, seed_id: str) -> Seed:
        """按 id 读取种子；不存在则抛出 NotFoundError。"""

    @abstractmethod
    def list_seeds(
        self,
        status: SeedStatus | None = None,
        limit: int | None = None,
    ) -> list[Seed]:
        """列出种子；可按状态筛选并限制条数。"""

    @abstractmethod
    def update_seed(self, seed: Seed) -> Seed:
        """更新已有种子；不存在则抛出 NotFoundError。"""

    # —— MemoryCard —— #

    @abstractmethod
    def save_memory_card(self, memory: MemoryCard) -> MemoryCard:
        """首次插入记忆卡；主键已存在则抛出 DuplicateIdError（修改请用 update_memory_card）。"""

    @abstractmethod
    def get_memory_card(self, memory_id: str) -> MemoryCard:
        """按 id 读取记忆卡；不存在则抛出 NotFoundError。"""

    @abstractmethod
    def list_memory_cards(
        self,
        lifecycle: MemoryLifecycle | None = None,
        include_greenhouse: bool = False,
        limit: int | None = None,
    ) -> list[MemoryCard]:
        """列出记忆卡；可按生命周期筛选。

        include_greenhouse=False 时实现应排除温室隔离中的记忆（具体判定由实现完成）。
        """

    @abstractmethod
    def count_memory_cards(
        self,
        lifecycle: MemoryLifecycle | None = None,
        include_greenhouse: bool = False,
    ) -> int:
        """统计记忆卡数量；与 list_memory_cards 使用相同筛选语义，但不反序列化 payload。"""

    @abstractmethod
    def update_memory_card(self, memory: MemoryCard) -> MemoryCard:
        """更新已有记忆卡；不存在则抛出 NotFoundError。"""

    @abstractmethod
    def delete_memory_card(self, memory_id: str) -> None:
        """删除记忆卡；不存在则抛出 NotFoundError。"""

    # —— CourtCase —— #

    @abstractmethod
    def save_court_case(self, case: CourtCase) -> CourtCase:
        """首次插入法庭案件；主键已存在则抛出 DuplicateIdError。"""

    @abstractmethod
    def get_court_case(self, case_id: str) -> CourtCase:
        """按 id 读取案件；不存在则抛出 NotFoundError。"""

    @abstractmethod
    def list_court_cases(
        self,
        seed_id: str | None = None,
        limit: int | None = None,
    ) -> list[CourtCase]:
        """列出案件；可按种子 id 筛选。"""

    @abstractmethod
    def delete_court_case(self, case_id: str) -> None:
        """删除法庭案件；不存在则抛出 NotFoundError。"""

    # —— DreamRecord —— #

    @abstractmethod
    def save_dream_record(self, record: DreamRecord) -> DreamRecord:
        """追加写入梦境记录；主键已存在则抛出 DuplicateIdError（接口不提供 update/delete）。"""

    @abstractmethod
    def get_dream_record(self, record_id: str) -> DreamRecord:
        """按 id 读取梦境记录；不存在则抛出 NotFoundError。"""

    @abstractmethod
    def list_dream_records(self, limit: int | None = None) -> list[DreamRecord]:
        """列出梦境记录（实现可约定时间倒序等）。"""

    # —— CompostRecord —— #

    @abstractmethod
    def save_compost_record(self, record: CompostRecord) -> CompostRecord:
        """追加写入堆肥记录；主键已存在则抛出 DuplicateIdError（接口不提供 update/delete）。"""

    @abstractmethod
    def get_compost_record(self, record_id: str) -> CompostRecord:
        """按 id 读取堆肥记录；不存在则抛出 NotFoundError。"""

    @abstractmethod
    def list_compost_records(
        self,
        source_seed_id: str | None = None,
        source_memory_id: str | None = None,
        limit: int | None = None,
    ) -> list[CompostRecord]:
        """列出堆肥记录；可按来源种子或来源记忆筛选。"""

    # —— GreenhouseRecord —— #

    @abstractmethod
    def save_greenhouse_record(self, record: GreenhouseRecord) -> GreenhouseRecord:
        """追加写入温室记录；主键已存在则抛出 DuplicateIdError（接口不提供 update/delete）。"""

    @abstractmethod
    def get_greenhouse_record(self, record_id: str) -> GreenhouseRecord:
        """按 id 读取温室记录；不存在则抛出 NotFoundError。"""

    @abstractmethod
    def list_greenhouse_records(
        self,
        memory_id: str | None = None,
        limit: int | None = None,
    ) -> list[GreenhouseRecord]:
        """列出温室记录；可按记忆 id 筛选。"""

    # —— PruningRecord —— #

    @abstractmethod
    def save_pruning_record(self, record: PruningRecord) -> PruningRecord:
        """追加写入修剪记录；主键已存在则抛出 DuplicateIdError（接口不提供 update/delete）。"""

    @abstractmethod
    def get_pruning_record(self, record_id: str) -> PruningRecord:
        """按 id 读取修剪记录；不存在则抛出 NotFoundError。"""

    @abstractmethod
    def list_pruning_records(
        self,
        memory_id: str | None = None,
        limit: int | None = None,
    ) -> list[PruningRecord]:
        """列出修剪记录；可按记忆 id 筛选。"""

    # —— GardenEvent —— #

    @abstractmethod
    def save_garden_event(self, event: GardenEvent) -> GardenEvent:
        """追加写入花园日志；主键已存在则抛出 DuplicateIdError（接口不提供 update/delete）。"""

    @abstractmethod
    def get_garden_event(self, event_id: str) -> GardenEvent:
        """按 id 读取日志事件；不存在则抛出 NotFoundError。"""

    @abstractmethod
    def list_garden_events(
        self,
        event_type: GardenEventType | None = None,
        object_type: GardenObjectType | None = None,
        object_id: str | None = None,
        limit: int | None = None,
    ) -> list[GardenEvent]:
        """列出日志事件；可按类型与关联对象筛选。"""
