"""Anthropic SDK adapter — drop-in memory layer for the Anthropic Python SDK.

Usage::

    import anthropic
    from memory_garden.sdk import MemoryGarden
    from memory_garden.integrations.adapters.anthropic import GardenAnthropic

    garden = MemoryGarden.local("./my_garden")
    client = anthropic.Anthropic(api_key="...")
    wrapped = GardenAnthropic(client=client, garden=garden)

    wrapped.skill.open()
    response = wrapped.messages.create(
        messages=[{"role": "user", "content": "I prefer dark mode."}],
        model="claude-sonnet-4-6",
        max_tokens=1024,
    )
    wrapped.skill.close()

Zero hard dependency on ``anthropic`` — if not installed, the class
still imports but won't work without the package.
"""

from __future__ import annotations

from typing import Any


class GardenAnthropic:
    """Anthropic client wrapper that injects Memory Garden context.

    Wraps an ``anthropic.Anthropic`` or ``anthropic.AsyncAnthropic``
    instance.  Every ``messages.create()`` call is intercepted.
    """

    def __init__(self, *, client: Any, garden: Any, providers: Any | None = None) -> None:
        self._client = client
        self._garden = garden
        from memory_garden.integrations.adapters._cognitive_brief import resolve_provider_registry
        from memory_garden.skill import GardenSkill

        self._skill: GardenSkill = garden.as_skill()
        self._providers = resolve_provider_registry(garden, providers)
        if self._providers is not None:
            self._skill.configure_providers(self._providers)

    @property
    def skill(self) -> Any:
        return self._skill

    @property
    def client(self) -> Any:
        return self._client

    @property
    def messages(self) -> "GardenAnthropicMessages":
        return GardenAnthropicMessages(self._client, self._skill, self._garden, self._providers)


class GardenAnthropicMessages:
    """Intercepted messages proxy for Anthropic SDK."""

    def __init__(self, client: Any, skill: Any, garden: Any, providers: Any | None) -> None:
        self._client = client
        self._skill = skill
        self._garden = garden
        self._providers = providers

    def create(self, *, messages: list[dict], model: str, system: str = "", **kwargs: Any) -> Any:
        """Inject Garden Brief, call Anthropic, observe response."""
        user_text = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                user_text = str(m.get("content", ""))
                break

        from memory_garden.integrations.adapters._cognitive_brief import build_cognitive_skill_context

        ctx = build_cognitive_skill_context(
            garden=self._garden,
            skill=self._skill,
            providers=self._providers,
            user_message=user_text,
            metadata={"adapter": "anthropic", "source_role": "user"},
            messages=messages,
            max_candidates=5,
        )
        if ctx is None:
            ctx = self._skill.before(user_text, messages=messages)

        # Inject brief into system prompt
        augmented_system = system or ""
        if ctx.brief_text.strip():
            brief_prefix = ctx.to_system_prefix()
            augmented_system = augmented_system + "\n\n" + brief_prefix if augmented_system else brief_prefix

        response = self._client.messages.create(
            messages=ctx.messages if ctx.messages else messages,
            model=model,
            system=augmented_system,
            **kwargs,
        )

        try:
            reply = ""
            for block in response.content:
                if hasattr(block, "text"):
                    reply += block.text
            if reply:
                self._skill.after(user_text, reply)
        except Exception:
            # 适配器不得因响应解析失败破坏调用方的原始 Anthropic 响应。
            pass

        return response
