"""DeepSeek 旧版集成适配器。

本模块保留 ``memory_garden.integrations`` 的历史导入路径，但实际实现委托给
``memory_garden.providers.openai_compatible.DeepSeekLLMProvider``。新代码应优先使用
``memory_garden.providers`` 下的 canonical provider。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from memory_garden.integrations.providers import LLMProvider, ProviderConfig
from memory_garden.providers.openai_compatible import DeepSeekLLMProvider as _CanonicalDeepSeekLLMProvider


class DeepSeekProvider(_CanonicalDeepSeekLLMProvider, LLMProvider):
    """兼容旧 ABC 的 DeepSeek provider。

    旧接口需要 ``config`` 属性和 ``structured_generate`` 返回通过 Pydantic 校验的
    ``dict``；底层网络调用、OpenAI 兼容协议与可选依赖处理统一复用 canonical provider。
    """

    def __init__(
        self,
        api_key: str,
        model: str = "deepseek-chat",
        api_base: str = "https://api.deepseek.com/v1",
        temperature: float = 0.0,
        max_tokens: int = 1024,
        client: Any | None = None,
    ) -> None:
        super().__init__(
            api_key=api_key,
            model=model,
            base_url=api_base,
            temperature=temperature,
            max_tokens=max_tokens,
            client=client,
        )
        self._config = ProviderConfig(
            provider="deepseek",
            model=model,
            api_base_url=api_base,
        )

    def structured_generate(self, prompt: str, schema: type, *, system: str = "", **kwargs: Any) -> dict:
        """调用 DeepSeek 并返回经过 schema 校验的结构化结果。"""
        data = super().structured_generate(prompt, schema, system=system, **kwargs)
        if isinstance(schema, type) and issubclass(schema, BaseModel):
            return schema.model_validate(data).model_dump()
        return dict(data)

    @property
    def config(self) -> ProviderConfig:
        return self._config


__all__ = ["DeepSeekProvider"]
