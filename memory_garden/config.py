"""Memory Garden 最小本地配置（不含密钥、同步与云端）。"""

from pydantic import BaseModel, Field

from memory_garden.runtime_config import GardenRuntimeConfig, default_garden_runtime_config

__all__ = [
    "MemoryGardenConfig",
    "GardenRuntimeConfig",
    "default_garden_runtime_config",
]


class MemoryGardenConfig(BaseModel):
    """可调运行时参数，默认适用于单元测试。"""

    sqlite_path: str = Field(
        default=":memory:",
        description="SQLite 数据库路径；测试常用 :memory: 或临时文件路径",
    )
    runtime: GardenRuntimeConfig = Field(
        default_factory=GardenRuntimeConfig.default,
        description="Harvest / 检索 / 冲突等子系统运行时参数树",
    )
