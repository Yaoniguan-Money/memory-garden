"""记忆卡片生命周期枚举（字符串值便于 JSON / SQLite 序列化）。"""

from enum import Enum


class MemoryLifecycle(str, Enum):
    """MemoryCard 的生长阶段。"""

    sprout = "sprout"
    bloom = "bloom"
    rooted = "rooted"
    fading = "fading"
    pruned = "pruned"
    composted = "composted"  # 预留：记忆卡级堆肥待 Stage 5A-2 实现，当前仅种子级堆肥可用
    greenhouse = "greenhouse"
