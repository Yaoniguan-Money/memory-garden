"""
同步 Chat 接入最小示例（演示用本地规则 Agent，不接外部 LLM）。

运行（仓库根目录）::

    python examples/sync_chat_agent.py
"""

from __future__ import annotations

from typing import NamedTuple

from memory_garden.core import MemoryGardenCore
from memory_garden.integrations.config import BriefInjectionMode, GardenAdapterConfig
from memory_garden.integrations.models import IntegrationResult
from memory_garden.integrations.sync import SyncGardenChatAdapter
from memory_garden.runtime import GardenSessionManager, NullHarvester, RuntimeHooks, TemplateBriefWriter
from memory_garden.runtime.runtime import GardenRuntime


class RuleBasedDemoAgent:
    """教学用假 Agent：回显短语并标记是否收到简报上下文（不写网络、不调模型）。"""

    __slots__ = ("calls",)

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def generate_assistant_reply(
        self,
        *,
        user_message: str,
        session_id: str,
        extra_context: str | None = None,
    ) -> str:
        self.calls.append((user_message, session_id))
        has_ctx = "有简报上下文" if (extra_context and extra_context.strip()) else "无简报上下文"
        return f"[demo] {has_ctx} | 用户这句 len={len(user_message)}"


class DemoChatBundle(NamedTuple):
    """便于测试同时拿到适配器与假 Agent（非公开 API，仅示例与单元测试使用）。"""

    adapter: SyncGardenChatAdapter
    agent: RuleBasedDemoAgent


def build_demo_runtime() -> GardenRuntime:
    """构造与测试套件一致的最小 Runtime（内存 SQLite、模板简报）。"""
    core = MemoryGardenCore()
    manager = GardenSessionManager()
    hooks = RuntimeHooks(manager, NullHarvester(), TemplateBriefWriter(), core)
    return GardenRuntime(core, manager, hooks)


def build_demo_stack(*, injection_mode: BriefInjectionMode | None = None) -> DemoChatBundle:
    """创建 ``SyncGardenChatAdapter`` + ``RuleBasedDemoAgent``。"""
    agent = RuleBasedDemoAgent()
    cfg = GardenAdapterConfig(
        brief_injection_mode=injection_mode if injection_mode is not None else BriefInjectionMode.context_argument,
        debug=False,
    )
    adapter = SyncGardenChatAdapter(agent=agent, runtime=build_demo_runtime(), config=cfg)
    return DemoChatBundle(adapter=adapter, agent=agent)


def build_demo_adapter() -> SyncGardenChatAdapter:
    """Quickstart：只返回适配器。"""
    return build_demo_stack().adapter


def run_demo() -> list[IntegrationResult]:
    """执行一轮最小对话：花花开 → 普通句 → 花花关；返回每步 ``IntegrationResult``。"""
    bundle = build_demo_stack()
    adapter = bundle.adapter
    results: list[IntegrationResult] = []

    r_open = adapter.reply("花花开")
    results.append(r_open)
    sid = r_open.session_id

    r_chat = adapter.reply("今天想记录一条偏好：界面用深色模式。", session_id=sid)
    results.append(r_chat)

    r_close = adapter.reply("花花关", session_id=sid)
    results.append(r_close)

    return results


def _summarize_result(i: int, r: IntegrationResult) -> str:
    brief = "有" if r.garden_brief is not None else "无"
    fb = "有" if r.feedback is not None else "无"
    rep = r.reply if len(r.reply) <= 120 else r.reply[:117] + "…"
    return f"[{i}] session_id={r.session_id!r} reply={rep!r} brief={brief} feedback={fb} trace_id={r.trace_id!r}"


def main() -> None:
    """打印短摘要，不 dump 大对象或长 trace。"""
    for i, r in enumerate(run_demo()):
        print(_summarize_result(i, r))


if __name__ == "__main__":
    main()
