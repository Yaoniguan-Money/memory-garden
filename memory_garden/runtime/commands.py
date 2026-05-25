"""第二层：运行时控制口令解析（花花开 / 花花关及别名）。

本模块不调用第一层 Core，不生成 Seed 或 MemoryCard。
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class CommandType(str, Enum):
    """用户可见的控制类命令种类。"""

    OPEN = "open"
    CLOSE = "close"
    UNKNOWN = "unknown"


# 精确整句匹配别名（供编排层与测试引用；解析逻辑仍以 ``parse_runtime_command`` 为准）
OPEN_COMMAND_ALIASES: tuple[str, ...] = ("花花开", "/garden on")
CLOSE_COMMAND_ALIASES: tuple[str, ...] = ("花花关", "/garden off")


class CommandResult(BaseModel):
    """单次解析结果：仅在识别为控制口令时返回。"""

    model_config = ConfigDict(validate_assignment=True)

    command_type: CommandType
    raw_text: str = Field(..., description="调用方传入的原始字符串")
    normalized_text: str = Field(..., description="strip 后的全文，用于精确匹配判定")
    matched_alias: str = Field(..., description="命中的别名或规范形式")
    is_runtime_command: bool = Field(default=True, description="本阶段恒为 True；保留字段供编排扩展")
    user_visible_message: str | None = Field(
        default=None,
        description="可选的简短提示，供 UI 或日志展示",
    )


def parse_runtime_command(user_message: str) -> CommandResult | None:
    """识别运行时控制口令；仅当**整段**文本（去首尾空白后）完全匹配某一条命令时返回结果。

    - 子串命中不算命令（例如普通聊天里提到「花花开」）。
    - 空串与未知文本返回 ``None``（不返回 UNKNOWN 类型的 ``CommandResult``）。
    - 英文别名 ``/garden on`` / ``/garden off`` 大小写不敏感。
    """
    raw_text = user_message
    normalized = user_message.strip()
    if not normalized:
        return None

    # 中文：整句精确匹配
    if normalized == "花花开":
        return CommandResult(
            command_type=CommandType.OPEN,
            raw_text=raw_text,
            normalized_text=normalized,
            matched_alias="花花开",
            user_visible_message="花园控制：开启请求（由运行时后续处理）",
        )
    if normalized == "花花关":
        return CommandResult(
            command_type=CommandType.CLOSE,
            raw_text=raw_text,
            normalized_text=normalized,
            matched_alias="花花关",
            user_visible_message="花园控制：关闭请求（由运行时后续处理）",
        )

    # 英文别名：整句大小写不敏感
    key = normalized.casefold()
    if key == "/garden on":
        return CommandResult(
            command_type=CommandType.OPEN,
            raw_text=raw_text,
            normalized_text=normalized,
            matched_alias="/garden on",
            user_visible_message="Garden runtime: open request (pending orchestration)",
        )
    if key == "/garden off":
        return CommandResult(
            command_type=CommandType.CLOSE,
            raw_text=raw_text,
            normalized_text=normalized,
            matched_alias="/garden off",
            user_visible_message="Garden runtime: close request (pending orchestration)",
        )

    return None
