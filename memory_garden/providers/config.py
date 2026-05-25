"""外部模型 Provider 的策略配置。

默认阻止远程 LLM、Embedding 与 Reranker。调用方必须显式 opt in 远程 provider，
并且用户原文、敏感文本等更细的策略仍会继续由本模型校验。
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ProviderPolicy(BaseModel):
    """控制 provider 调用何时可以离开本地进程。"""

    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    allow_remote_llm: bool = False
    allow_remote_embeddings: bool = False
    allow_remote_rerank: bool = False
    allow_raw_user_text: bool = False
    allow_sensitive_text: bool = False
    max_candidates_per_call: int = Field(default=32, ge=1, le=500)
    max_chars_per_call: int = Field(default=12000, ge=256, le=200000)
    timeout_seconds: float = Field(default=30.0, ge=0.1, le=300.0)

    def allows_remote(self, provider_kind: str) -> bool:
        if provider_kind == "llm":
            return self.allow_remote_llm
        if provider_kind == "embedding":
            return self.allow_remote_embeddings
        if provider_kind == "reranker":
            return self.allow_remote_rerank
        return False
