"""通用 LLM 重排序组件 — 不绑定任何具体厂商。

通过 ``LLMProvider`` 接口调用底层模型，对 Harvest 候选记忆进行语义重排序。
可在 ``run_hybrid_harvest()`` 中作为 ``rank_provider`` 注入。

使用方式::

    from memory_garden.integrations.deepseek_provider import DeepSeekProvider
    from memory_garden.harvest.reranker.llm_reranker import LLMReranker

    llm = DeepSeekProvider(api_key="<DEEPSEEK_API_KEY>")
    reranker = LLMReranker(llm)
    result = reranker.rerank(query_text, candidates, policy)
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

from memory_garden.cognition.models import HarvestCandidate, HarvestRerankResult
from memory_garden.harvest.policy import HarvestBudgetPolicy
from memory_garden.providers.base import ProviderCallContext
from memory_garden.providers.errors import ProviderPolicyError

# ── 数据模型 ──────────────────────────────────────────────────────────


class RerankOrder(BaseModel):
    """LLM 返回的排序结果 schema。"""

    ranked_ids: list[str] = Field(..., description="按相关性排序的记忆 ID 列表")


# ── 默认 Prompt 模板 ──────────────────────────────────────────────────

_DEFAULT_SYSTEM_PROMPT = """你是一个精确的记忆排序助手。
你需要根据查询的相关性，对候选记忆进行重排序。

规则：
1. 只考虑与查询直接相关的记忆
2. 返回排序后的记忆ID列表（从最相关到最不相关）
3. 如果某个记忆完全无关，移到列表末尾
4. 严格返回 JSON 数组，不要附加说明"""

_DEFAULT_USER_TEMPLATE = """查询：
{query}

候选记忆列表（ID: 摘要）：
{candidates}

请按相关性从高到低输出这些记忆的 ID 数组，格式如：
["mem_xxx", "mem_yyy", "mem_zzz"]
只输出 JSON 数组，不要其他文字。"""


# ── LLM 重排序器 ──────────────────────────────────────────────────────


class LLMReranker:
    """通用 LLM 重排序器。

    使用 ``LLMProvider.structured_generate()`` 对候选记忆排序。
    不依赖任何特定厂商。
    """

    def __init__(
        self,
        llm_provider: Any,
        *,
        system_prompt: str = _DEFAULT_SYSTEM_PROMPT,
        user_template: str = _DEFAULT_USER_TEMPLATE,
        temperature: float = 0.0,
        provider_policy: Any | None = None,
        garden_home: str = "",
    ) -> None:
        self._llm = llm_provider
        self._system_prompt = system_prompt
        self._user_template = user_template
        self._temperature = temperature
        self._provider_policy = provider_policy
        self._garden_home = garden_home

    def rerank(
        self,
        query_text: str,
        candidates: list[HarvestCandidate],
        policy: HarvestBudgetPolicy | None = None,
    ) -> HarvestRerankResult:
        """对候选列表进行 LLM 重排序。

        Args:
            query_text: 用户查询原文。
            candidates: Harvest 候选列表（至少已规则召回）。
            policy: 可选的预算策略（仅读取 limit 参数）。

        Returns:
            HarvestRerankResult：排序后的候选列表。
        """
        if not candidates:
            return HarvestRerankResult(
                candidates=[],
                provider_name="llm_reranker",
            )

        # 构建候选清单字符串
        candidate_lines = []
        for c in candidates:
            tags_str = f" [{', '.join(c.tags)}]" if c.tags else ""
            candidate_lines.append(f"{c.memory_id}: {c.text}{tags_str}")

        user_prompt = self._user_template.format(
            query=query_text,
            candidates="\n".join(candidate_lines),
        )

        result_dict = self._structured_generate(user_prompt)

        ranked_ids = result_dict.get("ranked_ids", [])

        # 将候选按 LLM 排序重排，未出现在排名中的追加到末尾
        candidate_map = {c.memory_id: c for c in candidates}
        reranked: list[HarvestCandidate] = []
        seen: set[str] = set()

        for mid in ranked_ids:
            if mid in candidate_map and mid not in seen:
                c = candidate_map[mid]
                c = c.model_copy(update={"rerank_score": 1.0 - len(reranked) * 0.01})
                reranked.append(c)
                seen.add(mid)

        # 追加 LLM 未提及的候选（排在末尾）
        for c in candidates:
            if c.memory_id not in seen:
                reranked.append(c)

        return HarvestRerankResult(
            candidates=reranked,
            provider_name="llm_reranker",
        )

    def _structured_generate(self, user_prompt: str) -> dict[str, Any]:
        context = ProviderCallContext(
            purpose="harvest_rerank",
            provider_kind="llm",
            garden_home=self._garden_home,
            allow_remote=bool(getattr(self._llm, "is_remote", False)),
        )
        self._assert_provider_call_allowed(context, user_prompt)

        if hasattr(self._llm, "structured_generate"):
            result = self._llm.structured_generate(
                prompt=user_prompt,
                schema=RerankOrder,
                system=self._system_prompt,
                temperature=self._temperature,
            )
            return _coerce_result_dict(result)

        if hasattr(self._llm, "complete_json"):
            result = self._llm.complete_json(
                system=self._system_prompt,
                user=user_prompt,
                schema=RerankOrder.model_json_schema(),
                context=context,
            )
            return _coerce_result_dict(getattr(result, "data", result))

        if hasattr(self._llm, "complete"):
            text = self._llm.complete(user_prompt, max_tokens=512)
            return _json_to_order_dict(str(text))

        if hasattr(self._llm, "complete_text"):
            result = self._llm.complete_text(
                system=self._system_prompt,
                user=user_prompt,
                context=context,
            )
            return _json_to_order_dict(str(getattr(result, "text", result)))

        raise TypeError("LLM provider 必须实现 structured_generate、complete_json、complete 或 complete_text 之一")

    def _assert_provider_call_allowed(self, context: ProviderCallContext, text: str) -> None:
        if self._provider_policy is not None:
            from memory_garden.product.policy import MemoryPolicy

            MemoryPolicy(provider_policy=self._provider_policy).assert_provider_call_allowed(context, text)
        elif context.allow_remote:
            raise ProviderPolicyError("Remote LLM reranker requires an explicit ProviderPolicy opt-in")


def _coerce_result_dict(result: Any) -> dict[str, Any]:
    if isinstance(result, BaseModel):
        return result.model_dump(mode="json")
    if isinstance(result, dict):
        return dict(result)
    return _json_to_order_dict(str(result))


def _json_to_order_dict(text: str) -> dict[str, Any]:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {"ranked_ids": []}
    if isinstance(parsed, list):
        return {"ranked_ids": [str(x) for x in parsed]}
    if isinstance(parsed, dict):
        return dict(parsed)
    return {"ranked_ids": []}
