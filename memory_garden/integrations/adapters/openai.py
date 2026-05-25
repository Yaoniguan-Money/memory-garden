"""OpenAI client wrapper — drop-in memory layer for OpenAI SDK.

Usage::

    import openai
    from memory_garden.sdk import MemoryGarden
    from memory_garden.integrations.adapters.openai import GardenOpenAI

    garden = MemoryGarden.local("./my_garden")
    client = openai.OpenAI(api_key="...")
    wrapped = GardenOpenAI(client=client, garden=garden)

    wrapped.skill.open()
    response = wrapped.chat("I prefer dark mode.")
    wrapped.skill.close()
"""

from __future__ import annotations

from typing import Any


class GardenOpenAI:
    """OpenAI client wrapper that injects Memory Garden context.

    Wraps an ``openai.OpenAI`` or ``openai.AsyncOpenAI`` instance.
    Every ``chat.completions.create()`` call is intercepted to inject
    the Garden Brief as a system message before the call, and to observe
    the response after.
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
    def chat(self) -> "GardenChatCompletions":
        return GardenChatCompletions(self._client, self._skill, self._garden, self._providers)


class GardenChatCompletions:
    """Intercepted chat.completions proxy."""

    def __init__(self, client: Any, skill: Any, garden: Any, providers: Any | None) -> None:
        self._client = client
        self._skill = skill
        self._garden = garden
        self._providers = providers

    def create(self, *, messages: list[dict], model: str, **kwargs: Any) -> Any:
        """Inject Garden Brief, call LLM, observe response.

        If *messages* ends with a user message, that message is extracted
        and used as the garden input.  The Brief is injected as a system
        message before the LLM call.
        """
        # Extract the last user message
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
            metadata={"adapter": "openai", "source_role": "user"},
            messages=messages,
            max_candidates=5,
        )
        if ctx is None:
            ctx = self._skill.before(user_text, messages=messages)
        modified_messages = ctx.messages if ctx.messages else messages

        # Call real LLM
        response = self._client.chat.completions.create(
            messages=modified_messages, model=model, **kwargs
        )

        # Observe response
        try:
            reply = response.choices[0].message.content
            if reply:
                self._skill.after(user_text, reply)
        except (AttributeError, IndexError):
            # SDK 响应形态不稳定时，只跳过 after 观察，不吞掉主响应。
            pass

        return response
