"""LLM Reranker 单元测试 — 使用 MockLLMProvider，不依赖真实 API。

覆盖场景：
- 空候选列表
- LLM 返回完整排序
- LLM 返回部分排序（未提及的候选追加到末尾）
- LLM 返回空列表（全部保留原序）
- 注入到 GardenHarvester.harvest_cognitive() 集成
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from memory_garden.cognition.models import HarvestCandidate
from memory_garden.harvest.policy import HarvestBudgetPolicy
from memory_garden.harvest.reranker.llm_reranker import LLMReranker, RerankOrder
from memory_garden.integrations.mock_providers import MockLLMProvider
from memory_garden.providers.errors import ProviderPolicyError


# ── 辅助函数 ──────────────────────────────────────────────────────────


def _make_candidates(n: int) -> list[HarvestCandidate]:
    """生成 n 个``HarvestCandidate`` 用于测试。"""
    return [
        HarvestCandidate(
            memory_id=f"mem_{i:03d}",
            source_ids=[f"src_{i:03d}"],
            text=f"这是记忆 {i} 的内容：{'测试 ' * (i + 1)}",
            tags=["test"] if i % 2 == 0 else [],
            rule_score=round(1.0 - i * 0.08, 4),
        )
        for i in range(n)
    ]


# ── 测试：空候选列表 ──────────────────────────────────────────────────


def test_rerank_empty_candidates() -> None:
    llm = MockLLMProvider()
    reranker = LLMReranker(llm)
    result = reranker.rerank("查询", [])
    assert result.candidates == []
    assert result.provider_name == "llm_reranker"


# ── 测试：MockLLMProvider 的默认行为 ──────────────────────────────────


def test_rerank_with_mock_keeps_order() -> None:
    """MockLLMProvider 返回的 ranked_ids 是空的，所以原序保留。"""
    llm = MockLLMProvider()
    reranker = LLMReranker(llm)

    candidates = _make_candidates(5)
    result = reranker.rerank("测试查询", candidates)

    # 候选数量不变
    assert len(result.candidates) == 5
    # 因为 MockLLMProvider 返回空 dict，所有候选按原序保留
    assert [c.memory_id for c in result.candidates] == [
        "mem_000",
        "mem_001",
        "mem_002",
        "mem_003",
        "mem_004",
    ]


# ── 测试：Echo 模式（MockLLMProvider 回显 prompt）────────────────────


def test_rerank_with_echo_mode() -> None:
    """Echo 模式会返回 prompt 文本（单个字段），验证错误处理。"""
    llm = MockLLMProvider(echo=True)
    reranker = LLMReranker(llm)

    candidates = _make_candidates(3)
    # 应该不会崩溃，RerankOrder 的 ranked_ids 字段会得到默认 []
    result = reranker.rerank("测试", candidates)
    assert len(result.candidates) == 3


# ── 测试：集成到 GardenHarvester.harvest_cognitive() 的接口兼容性 ────


def test_reranker_implements_required_interface() -> None:
    """验证 LLMReranker 的 rerank 签名与 run_hybrid_harvest 期望一致。"""
    llm = MockLLMProvider()
    reranker = LLMReranker(llm)
    candidates = _make_candidates(3)
    policy = HarvestBudgetPolicy()

    # 这个调用应该能正常返回 HarvestRerankResult
    result = reranker.rerank("查询", candidates, policy)
    assert hasattr(result, "candidates")
    assert hasattr(result, "provider_name")
    assert hasattr(result, "prompt_version")
    assert hasattr(result, "metadata")


def test_reranker_accepts_canonical_complete_json_provider() -> None:
    class _CanonicalJsonLLM:
        name = "canonical-json"
        is_remote = False

        def complete_json(self, *, system, user, schema, context):
            return SimpleNamespace(data={"ranked_ids": ["mem_002", "mem_000"]})

    reranker = LLMReranker(_CanonicalJsonLLM())
    candidates = _make_candidates(3)

    result = reranker.rerank("查询", candidates)

    assert [c.memory_id for c in result.candidates] == ["mem_002", "mem_000", "mem_001"]


def test_llm_reranker_blocks_remote_provider_without_policy() -> None:
    class _RemoteJsonLLM:
        name = "remote-json"
        is_remote = True

        def complete_json(self, *, system, user, schema, context):
            return SimpleNamespace(data={"ranked_ids": ["mem_000"]})

    reranker = LLMReranker(_RemoteJsonLLM())

    with pytest.raises(ProviderPolicyError):
        reranker.rerank("查询", _make_candidates(1))


# ── 测试：RerankOrder schema ──────────────────────────────────────────


def test_rerank_order_model() -> None:
    """验证 RerankOrder Pydantic 模型。"""
    obj = RerankOrder(ranked_ids=["a", "b", "c"])
    assert obj.ranked_ids == ["a", "b", "c"]

    # model_dump 后再验证
    dumped = obj.model_dump()
    assert dumped["ranked_ids"] == ["a", "b", "c"]
