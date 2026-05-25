"""OpenAI 兼容远程 providers，用于产品级 Memory Garden 工作流。

这些适配器实现 canonical ``memory_garden.providers`` 协议。``openai`` 依赖保持
可选：安装 ``memory-garden[llm]``，或传入已经构造好的兼容 client。
"""

from __future__ import annotations

import json
import os
from typing import Any

from pydantic import BaseModel

from memory_garden.providers.base import ProviderCallContext
from memory_garden.providers.errors import ProviderError
from memory_garden.providers.schemas import (
    EmbeddingResult,
    JsonCompletionResult,
    RerankCandidate,
    RerankResult,
    TextCompletionResult,
)


def _build_client(*, api_key: str | None, base_url: str | None) -> Any:
    try:
        from openai import OpenAI
    except ImportError as exc:  # pragma: no cover - exercised when optional extra is missing
        raise ProviderError("使用 OpenAI 兼容 provider 前请先安装 memory-garden[llm]") from exc

    kwargs: dict[str, Any] = {}
    if api_key:
        kwargs["api_key"] = api_key
    if base_url:
        kwargs["base_url"] = base_url
    return OpenAI(**kwargs)


def _message_content(response: Any) -> str:
    try:
        content = response.choices[0].message.content
    except (AttributeError, IndexError, KeyError, TypeError) as exc:
        raise ProviderError("OpenAI 兼容响应缺少 choices[0].message.content") from exc
    if content is None:
        raise ProviderError("OpenAI 兼容 provider 返回了空消息内容")
    return str(content)


def _usage(response: Any) -> dict[str, Any]:
    usage = getattr(response, "usage", None)
    if usage is None:
        return {}
    if hasattr(usage, "model_dump"):
        return dict(usage.model_dump(mode="json"))
    if isinstance(usage, dict):
        return dict(usage)
    return {}


class OpenAICompatibleLLMProvider:
    """Remote LLM provider using the OpenAI chat completions API shape."""

    is_remote = True

    def __init__(
        self,
        *,
        model: str,
        api_key: str | None = None,
        base_url: str | None = None,
        client: Any | None = None,
        name: str = "openai-compatible-llm",
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> None:
        self.name = name
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._client = client or _build_client(api_key=api_key, base_url=base_url)

    def complete_text(
        self,
        *,
        system: str,
        user: str,
        context: ProviderCallContext,
    ) -> TextCompletionResult:
        response = self._client.chat.completions.create(
            model=self.model,
            messages=_messages(system, user),
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        return TextCompletionResult(text=_message_content(response), model=self.model, usage=_usage(response))

    def complete_json(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, Any],
        context: ProviderCallContext,
    ) -> JsonCompletionResult:
        prompt = _json_prompt(user, schema)
        response = self._client.chat.completions.create(
            model=self.model,
            messages=_messages(system, prompt),
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            response_format={"type": "json_object"},
        )
        content = _message_content(response)
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ProviderError(f"OpenAI 兼容 provider 返回了非 JSON 内容：{content[:200]}") from exc
        if not isinstance(data, dict):
            raise ProviderError("OpenAI 兼容 provider 返回的 JSON 不是对象")
        return JsonCompletionResult(data=data, model=self.model, usage=_usage(response))

    def complete(self, prompt: str, *, max_tokens: int | None = None) -> str:
        context = ProviderCallContext(
            purpose="text_completion",
            provider_kind="llm",
            allow_remote=True,
            metadata={"compat_method": "complete"},
        )
        old_max = self.max_tokens
        if max_tokens is not None:
            self.max_tokens = max_tokens
        try:
            return self.complete_text(system="", user=prompt, context=context).text
        finally:
            self.max_tokens = old_max

    def structured_generate(self, prompt: str, schema: type, *, system: str = "", **kwargs: Any) -> dict[str, Any]:
        _ = kwargs
        pydantic_schema = isinstance(schema, type) and issubclass(schema, BaseModel)
        if pydantic_schema:
            schema_dict = schema.model_json_schema()
        elif isinstance(schema, dict):
            schema_dict = schema
        else:
            schema_dict = {"type": "object"}
        context = ProviderCallContext(
            purpose="structured_generate",
            provider_kind="llm",
            allow_remote=True,
            metadata={"compat_method": "structured_generate"},
        )
        data = self.complete_json(system=system, user=prompt, schema=schema_dict, context=context).data
        if pydantic_schema:
            return schema.model_validate(data).model_dump()
        return data


class DeepSeekLLMProvider(OpenAICompatibleLLMProvider):
    """DeepSeek chat provider via its OpenAI-compatible endpoint."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = "deepseek-chat",
        base_url: str = "https://api.deepseek.com/v1",
        client: Any | None = None,
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> None:
        super().__init__(
            model=model,
            api_key=api_key or os.environ.get("DEEPSEEK_API_KEY"),
            base_url=base_url,
            client=client,
            name="deepseek-llm",
            temperature=temperature,
            max_tokens=max_tokens,
        )


class OpenAICompatibleEmbeddingProvider:
    """Remote embedding provider using the OpenAI embeddings API shape."""

    is_remote = True

    def __init__(
        self,
        *,
        model: str,
        api_key: str | None = None,
        base_url: str | None = None,
        client: Any | None = None,
        name: str = "openai-compatible-embedding",
    ) -> None:
        self.name = name
        self.model = model
        self._client = client or _build_client(api_key=api_key, base_url=base_url)

    def embed_texts(
        self,
        texts: list[str],
        *,
        truncate: bool = True,
        context: ProviderCallContext | None = None,
    ) -> EmbeddingResult | list[list[float]]:
        _ = truncate
        if not texts:
            result = EmbeddingResult(vectors=[], model=self.model, dimensions=0)
            return result if context is not None else []
        response = self._client.embeddings.create(model=self.model, input=texts)
        vectors = [_embedding_vector(item) for item in response.data]
        dimensions = len(vectors[0]) if vectors else 0
        result = EmbeddingResult(vectors=vectors, model=self.model, dimensions=dimensions, usage=_usage(response))
        return result if context is not None else vectors


class OpenAICompatibleRerankerProvider:
    """Reranker provider backed by an OpenAI-compatible JSON LLM call."""

    is_remote = True

    def __init__(
        self,
        *,
        llm: OpenAICompatibleLLMProvider,
        name: str = "openai-compatible-reranker",
    ) -> None:
        self.name = name
        self._llm = llm

    def rerank(
        self,
        *,
        query: str,
        candidates: list[RerankCandidate],
        top_k: int,
        context: ProviderCallContext,
    ) -> RerankResult:
        schema = {
            "type": "object",
            "properties": {
                "ranked_ids": {"type": "array", "items": {"type": "string"}},
                "scores": {"type": "object"},
                "explanations": {"type": "object"},
            },
            "required": ["ranked_ids"],
        }
        user = "\n".join(
            [
                f"Query: {query}",
                f"Return the best {top_k} candidate ids in descending relevance.",
                "Candidates:",
                *[f"- {candidate.id}: {candidate.text}" for candidate in candidates],
            ]
        )
        result = self._llm.complete_json(
            system="You rerank memory candidates. Return only JSON.",
            user=user,
            schema=schema,
            context=context,
        )
        ranked_ids = [str(mid) for mid in result.data.get("ranked_ids", [])]
        allowed = {candidate.id for candidate in candidates}
        ranked_ids = [mid for mid in ranked_ids if mid in allowed][: max(1, top_k)]
        scores = {
            str(key): float(value)
            for key, value in dict(result.data.get("scores") or {}).items()
            if str(key) in allowed and isinstance(value, (int, float))
        }
        explanations = {
            str(key): [str(item) for item in value]
            for key, value in dict(result.data.get("explanations") or {}).items()
            if str(key) in allowed and isinstance(value, list)
        }
        return RerankResult(ranked_ids=ranked_ids, scores=scores, explanations=explanations, model=result.model)


def _messages(system: str, user: str) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": user})
    return messages


def _json_prompt(user: str, schema: dict[str, Any]) -> str:
    return "\n\n".join(
        [
            user,
            "Return a JSON object matching this schema:",
            json.dumps(schema, ensure_ascii=False, sort_keys=True),
        ]
    )


def _embedding_vector(item: Any) -> list[float]:
    embedding = item.get("embedding") if isinstance(item, dict) else getattr(item, "embedding", None)
    if embedding is None:
        raise ProviderError("OpenAI 兼容 embedding 响应项缺少 embedding 字段")
    return [float(value) for value in embedding]


__all__ = [
    "DeepSeekLLMProvider",
    "OpenAICompatibleEmbeddingProvider",
    "OpenAICompatibleLLMProvider",
    "OpenAICompatibleRerankerProvider",
]
