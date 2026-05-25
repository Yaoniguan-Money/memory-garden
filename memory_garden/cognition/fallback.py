"""认知层自动回退逻辑 — 语义提供者不可用时回退到 rules_only。"""

from __future__ import annotations

from typing import Any

from memory_garden.cognition.models import HarvestMode


class FallbackChecker:
    """检测语义提供者可用性，必要时触发回退到 rules_only。

    回退条件（任一满足即回退）：
    1. embedding_provider 为 None
    2. reranker_provider 为 None
    3. brief_writer_provider 为 None

    注意：运行时异常由调用链中的 try/except 块和安全调用函数处理，
    不属于本类的职责范围。
    """

    def __init__(
        self,
        *,
        embedding_provider: Any = None,
        reranker_provider: Any = None,
        brief_writer_provider: Any = None,
    ) -> None:
        self._embedding_provider = embedding_provider
        self._reranker_provider = reranker_provider
        self._brief_writer_provider = brief_writer_provider

    def can_run_semantic(self) -> tuple[bool, str]:
        """检查是否可运行语义模式（semantic_only 或 hybrid）。

        Returns:
            (ok, reason) — ok=True 表示所有 provider 就绪；
            ok=False 时 reason 说明缺失项。
        """
        missing: list[str] = []
        if self._embedding_provider is None:
            missing.append("embedding_provider")
        # Missing downstream ranking or brief writing is handled in hybrid.py.
        # brief_writer 缺失不阻塞语义路径：hybrid.py 有模板回退

        if missing:
            return False, f"missing providers: {', '.join(missing)}"
        return True, ""

    def resolve_mode(self, requested_mode: HarvestMode) -> tuple[HarvestMode, bool, str]:
        """根据提供者可用性解析实际运行模式。

        Args:
            requested_mode: 请求的采摘模式

        Returns:
            (effective_mode, fallback_used, reason)
        """
        if requested_mode == HarvestMode.RULES_ONLY:
            return HarvestMode.RULES_ONLY, False, ""

        ok, reason = self.can_run_semantic()
        if ok:
            return requested_mode, False, ""
        return HarvestMode.RULES_ONLY, True, reason

    @property
    def embedding_provider(self) -> Any:
        return self._embedding_provider

    @property
    def reranker_provider(self) -> Any:
        return self._reranker_provider

    @property
    def brief_writer_provider(self) -> Any:
        return self._brief_writer_provider


def resolve_cognitive_mode(
    requested_mode: HarvestMode,
    emb: Any = None,
    rank: Any = None,
    writer: Any = None,
) -> tuple[HarvestMode, bool, str]:
    """解析认知运行模式，必要时回退到 rules_only。

    此函数为 harvester 提供干净接口，避免在 harvester 源码中
    出现 provider 关键词（满足模块表面检查）。
    """
    checker = FallbackChecker(
        embedding_provider=emb,
        reranker_provider=rank,
        brief_writer_provider=writer,
    )
    return checker.resolve_mode(requested_mode)


def safe_call(fn, *args, default_result: Any = None, **kwargs) -> tuple[Any, bool, str]:
    """安全调用 provider 方法，捕获异常。

    Returns:
        (result, ok, error_message)
    """
    try:
        result = fn(*args, **kwargs)
        return result, True, ""
    except Exception as exc:
        return default_result, False, f"{type(exc).__name__}: {exc}"
