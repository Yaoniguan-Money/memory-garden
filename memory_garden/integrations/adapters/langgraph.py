"""LangGraph node adapter — Memory Garden as a LangGraph StateGraph node.

Design source: planning Layer 4, Section 10.

Usage::

    from langgraph.graph import StateGraph, MessagesState
    from memory_garden.integrations.adapters.langgraph import garden_memory_node

    graph = StateGraph(MessagesState)
    graph.add_node("memory", garden_memory_node)
    graph.add_edge("memory", "agent")
    # ... compile and run

Zero hard dependency on ``langgraph``.
"""

from __future__ import annotations

from typing import Any


def garden_memory_node(
    state: dict,
    *,
    garden: Any | None = None,
    garden_path: str | None = None,
    providers: Any | None = None,
) -> dict:
    """LangGraph StateGraph node: inject garden context into agent state.

    Reads the last user message from ``state["messages"]``, queries
    the garden, and injects the brief into the state.

    Use as a LangGraph node::

        from langgraph.graph import StateGraph

        graph = StateGraph(MyState)
        graph.add_node("memory", lambda s: garden_memory_node(s, garden=garden))
    """
    if garden is None:
        from memory_garden.sdk import MemoryGarden
        garden = MemoryGarden.local(garden_path or "./.memory_garden")

    from memory_garden.skill import GardenSkill
    skill: GardenSkill = garden.as_skill()
    from memory_garden.integrations.adapters._cognitive_brief import (
        build_cognitive_skill_context,
        resolve_provider_registry,
    )
    provider_registry = resolve_provider_registry(garden, providers)
    if provider_registry is not None:
        skill.configure_providers(provider_registry)

    messages = state.get("messages", [])
    user_text = ""
    for m in reversed(messages):
        content = getattr(m, "content", str(m)) if hasattr(m, "content") else str(m)
        role = getattr(m, "role", "") if hasattr(m, "role") else ""
        type_val = getattr(m, "type", "") if hasattr(m, "type") else ""
        if role == "user" or type_val == "human":
            user_text = str(content)
            break

    msg = user_text or "[LangGraph step]"
    ctx = build_cognitive_skill_context(
        garden=garden,
        skill=skill,
        providers=provider_registry,
        user_message=msg,
        metadata={"adapter": "langgraph_node", "source_role": "user"},
        max_candidates=5,
    )
    if ctx is None:
        ctx = skill.before(msg)

    state["garden_context"] = ctx.brief_text or ""
    state["garden_session_id"] = ctx.session_id or ""
    # 独立节点函数无法跨调用维持会话，在产出 brief 后关闭
    try:
        skill.close()
    except Exception:
        pass
    return state


class GardenLangGraphMemory:
    """Persistent memory across a LangGraph agent loop.

    Unlike ``garden_memory_node`` which runs per-node, this class
    maintains a single garden session across the full graph execution.
    """

    def __init__(
        self,
        *,
        garden: Any | None = None,
        garden_path: str | None = None,
        providers: Any | None = None,
    ) -> None:
        if garden is None:
            from memory_garden.sdk import MemoryGarden
            garden = MemoryGarden.local(garden_path or "./.memory_garden")
        self._garden = garden
        from memory_garden.integrations.adapters._cognitive_brief import resolve_provider_registry
        from memory_garden.skill import GardenSkill
        self._skill: GardenSkill = garden.as_skill()
        self._providers = resolve_provider_registry(garden, providers)
        if self._providers is not None:
            self._skill.configure_providers(self._providers)
        self._is_open = False

    @property
    def skill(self) -> Any:
        return self._skill

    @property
    def garden(self) -> Any:
        return self._garden

    def open(self) -> None:
        if not self._is_open:
            self._skill.open()
            self._is_open = True

    def close(self) -> Any:
        if self._is_open:
            self._is_open = False
            return self._skill.close()
        return None

    def inject(self, state: dict) -> dict:
        """Inject garden context into LangGraph state (use in a node)."""
        self.open()
        messages = state.get("messages", [])
        user_text = ""
        for m in reversed(messages):
            content = getattr(m, "content", str(m)) if hasattr(m, "content") else str(m)
            role = getattr(m, "role", "") if hasattr(m, "role") else ""
            if role == "user" or getattr(m, "type", "") == "human":
                user_text = str(content)
                break

        msg = user_text or "[LangGraph step]"
        from memory_garden.integrations.adapters._cognitive_brief import build_cognitive_skill_context

        ctx = build_cognitive_skill_context(
            garden=self._garden,
            skill=self._skill,
            providers=self._providers,
            user_message=msg,
            metadata={"adapter": "langgraph", "source_role": "user"},
            max_candidates=5,
        )
        if ctx is None:
            ctx = self._skill.before(msg)
        state["garden_context"] = ctx.brief_text or ""
        state["garden_session_id"] = ctx.session_id or ""
        return state

    def observe(self, state: dict) -> dict:
        """Observe agent output (use in a separate node after agent generation)."""
        reply = state.get("output", state.get("agent_reply", ""))
        messages = state.get("messages", [])
        user_text = ""
        for m in reversed(messages):
            content = getattr(m, "content", str(m)) if hasattr(m, "content") else str(m)
            role = getattr(m, "role", "") if hasattr(m, "role") else ""
            if role == "user" or getattr(m, "type", "") == "human":
                user_text = str(content)
                break

        if reply:
            if not self._is_open:
                self.open()
            self._skill.after(user_text or "[LangGraph output]", str(reply))
        return state
