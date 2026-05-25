"""Shared optional provider loading for local agent adapters."""

from __future__ import annotations

import json
import os
from typing import Any

_AUTOLOAD_ENV = "MEMORY_GARDEN_ENABLE_PROVIDER_AUTOLOAD"
_TRUE_VALUES = {"1", "true", "yes", "on"}


def _autoload_enabled() -> bool:
    return os.environ.get(_AUTOLOAD_ENV, "").strip().casefold() in _TRUE_VALUES


def provider_registry_from_env(default_garden_path: str, *, autoload: bool | None = None) -> Any | None:
    """Build a ProviderRegistry from env vars or local provider_config.json.

    Auto-loading is disabled by default so adapter CLIs stay rules-only unless the
    caller explicitly opts in.
    """

    if autoload is None:
        autoload = _autoload_enabled()
    if not autoload:
        return None

    deepseek_key = os.environ.get("DEEPSEEK_API_KEY")
    dashscope_key = os.environ.get("DASHSCOPE_API_KEY")

    if not deepseek_key and not dashscope_key:
        config_file = os.path.join(default_garden_path, "provider_config.json")
        try:
            if os.path.isfile(config_file):
                with open(config_file, encoding="utf-8") as f:
                    cfg = json.load(f)
                deepseek_key = cfg.get("deepseek_api_key") or os.environ.get("DEEPSEEK_API_KEY")
                dashscope_key = cfg.get("dashscope_api_key") or os.environ.get("DASHSCOPE_API_KEY")
        except Exception:
            pass

    if not deepseek_key and not dashscope_key:
        return None
    try:
        from memory_garden.providers import (
            DeepSeekLLMProvider,
            OpenAICompatibleEmbeddingProvider,
            ProviderPolicy,
            ProviderRegistry,
        )

        policy = ProviderPolicy(
            allow_remote_llm=bool(deepseek_key),
            allow_remote_embeddings=bool(dashscope_key),
            allow_raw_user_text=True,
        )
        llm = DeepSeekLLMProvider(api_key=deepseek_key) if deepseek_key else None
        embedding = (
            OpenAICompatibleEmbeddingProvider(
                api_key=dashscope_key,
                model="text-embedding-v4",
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                name="dashscope-embedding",
            )
            if dashscope_key
            else None
        )
        return ProviderRegistry(policy=policy, llm=llm, embedding=embedding)
    except Exception:
        return None


__all__ = ["provider_registry_from_env"]
