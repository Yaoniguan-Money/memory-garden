"""第二层：运行时会话状态枚举。"""

from enum import Enum


class RuntimeState(str, Enum):
    """Garden 会话与编排层的生命周期状态（字符串值便于 JSON）。"""

    CLOSED = "closed"
    OPEN = "open"
    CLOSING = "closing"
