"""LlamaIndex adapter — Memory Garden as a LlamaIndex `BaseMemory` or `ChatMemory`.

LlamaIndex has a ``ChatMemory`` / ``BaseMemory`` abstraction similar to
LangChain's.  This adapter implements the duck-typed interface so Memory
Garden works as a drop-in memory backend.

Usage::

    from llama_index.core.memory import ChatMemoryBuffer
    from memory_garden.integrations.adapters.llamaindex import GardenLlamaIndexMemory

    garden_memory = GardenLlamaIndexMemory(garden=garden)
    # Use with any LlamaIndex agent or chat engine that accepts memory

Zero hard dependency on ``llama-index``.
"""

from __future__ import annotations

from typing import Any


class GardenLlamaIndexMemory:
    """Duck-typed LlamaIndex ChatMemory — zero import-time dependency.

    Implements the standard LlamaIndex memory interface:
    ``get()`` → list[ChatMessage], ``put(message)``, ``reset()``,
    ``get_all()``, ``token_limit`` property.
    """

    def __init__(self, *, garden: Any, token_limit: int = 3000, providers: Any | None = None) -> None:
        self._garden = garden
        from memory_garden.integrations.adapters._cognitive_brief import resolve_provider_registry
        from memory_garden.skill import GardenSkill

        self._skill: GardenSkill = garden.as_skill()
        self._providers = resolve_provider_registry(garden, providers)
        if self._providers is not None:
            self._skill.configure_providers(self._providers)
        self._token_limit = token_limit
        self._chat_history: list[Any] = []
        self._is_open = False

    @property
    def skill(self) -> Any:
        return self._skill

    @property
    def garden(self) -> Any:
        return self._garden

    @property
    def token_limit(self) -> int:
        return self._token_limit

    @token_limit.setter
    def token_limit(self, value: int) -> None:
        self._token_limit = value

    def get(self, **kwargs: Any) -> list[Any]:
        """Return chat history + injected garden context.

        Called by LlamaIndex before generating a response.
        """
        if not self._is_open:
            self._skill.open()
            self._is_open = True

        # Extract last user message from kwargs or history
        user_text = str(kwargs.get("input", ""))
        if not user_text and self._chat_history:
            last = self._chat_history[-1]
            user_text = str(getattr(last, "content", str(last)))

        from memory_garden.integrations.adapters._cognitive_brief import build_cognitive_skill_context

        ctx = build_cognitive_skill_context(
            garden=self._garden,
            skill=self._skill,
            providers=self._providers,
            user_message=user_text,
            metadata={"adapter": "llamaindex", "source_role": "user"},
            max_candidates=5,
        )
        if ctx is None:
            ctx = self._skill.before(user_text)

        # Build a LlamaIndex-compatible chat message for the brief
        messages = list(self._chat_history)
        if ctx.brief_text.strip():
            try:
                from llama_index.core.llms import ChatMessage, MessageRole  # type: ignore[import-not-found]
                messages.insert(0, ChatMessage(
                    role=MessageRole.SYSTEM,
                    content=f"[Memory Garden Context]\n{ctx.brief_text}",
                ))
            except ImportError:
                # Fallback: use simple namedtuple-like objects
                class _Msg:
                    def __init__(self, role, content):
                        self.role = role
                        self.content = content
                messages.insert(0, _Msg("system", f"[Memory Garden Context]\n{ctx.brief_text}"))

        return messages

    def get_all(self) -> list[Any]:
        """Return all chat history."""
        return list(self._chat_history)

    def put(self, message: Any) -> None:
        """Add a message to the chat history.

        Called by LlamaIndex after generating a response.
        Observes the assistant reply in the garden.
        """
        self._chat_history.append(message)
        try:
            content = getattr(message, "content", str(message))
            role = getattr(message, "role", "")
            if str(role).lower() in ("assistant", "ai", "bot"):
                user_text = self._last_user_message()
                self._skill.after(user_text or "[LlamaIndex message]", str(content))
                self._skill.close()
                self._is_open = False
        except (AttributeError, TypeError, ValueError):
            # LlamaIndex 消息对象形态较多，解析失败不能影响记忆容器追加。
            pass

    def reset(self) -> None:
        """Clear chat history and close garden session."""
        self._chat_history.clear()
        if self._is_open:
            self._skill.close()
            self._is_open = False

    def set(self, messages: list[Any]) -> None:
        """Replace chat history."""
        self._chat_history = list(messages)

    def _last_user_message(self) -> str:
        for item in reversed(self._chat_history):
            role = str(getattr(item, "role", "")).lower()
            if role in ("user", "human"):
                return str(getattr(item, "content", str(item)))
        return ""
