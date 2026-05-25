"""Provider 请求与响应的 Pydantic Schema。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TextCompletionResult(BaseModel):
    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    text: str
    model: str = ""
    usage: dict[str, Any] = Field(default_factory=dict)
    raw: dict[str, Any] = Field(default_factory=dict)


class JsonCompletionResult(BaseModel):
    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    data: dict[str, Any]
    model: str = ""
    usage: dict[str, Any] = Field(default_factory=dict)
    raw: dict[str, Any] = Field(default_factory=dict)


class EmbeddingResult(BaseModel):
    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    vectors: list[list[float]]
    model: str = ""
    dimensions: int = 0
    usage: dict[str, Any] = Field(default_factory=dict)


class RerankCandidate(BaseModel):
    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    id: str
    text: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class RerankResult(BaseModel):
    model_config = ConfigDict(validate_assignment=True, extra="forbid")

    ranked_ids: list[str]
    scores: dict[str, float] = Field(default_factory=dict)
    explanations: dict[str, list[str]] = Field(default_factory=dict)
    model: str = ""
    usage: dict[str, Any] = Field(default_factory=dict)
