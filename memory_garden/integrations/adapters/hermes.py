"""Hermes Agent adapter — Memory Garden as a Hermes hook.

Hermes Agent supports hooks that run before/after each turn.
This adapter provides a ``HermesGardenSession`` that bridges
WeChat conversations into the Garden lifecycle.

Usage — programmatic::

    from memory_garden.sdk import MemoryGarden
    from memory_garden.integrations.adapters.hermes import HermesGardenSession

    garden = MemoryGarden.local("./my_garden")
    session = HermesGardenSession(garden=garden)
    session.open()

    # Before Hermes replies to a user message
    ctx = session.before_reply(user_message="你好", source="weixin")

    # After Hermes replies
    session.after_reply(user_message="你好", assistant_reply="你好！")

    session.close()

Usage — CLI hooks (via ``hermes hooks`` config)::

    hooks:
      before_reply:
        - command: python -m memory_garden.integrations.adapters.hermes before
          timeout: 5000
      after_reply:
        - command: python -m memory_garden.integrations.adapters.hermes after
          timeout: 5000
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

DEFAULT_GARDEN_PATH = os.path.expanduser("~/.memory_garden")

# Hermes-specific conversation metadata keys
SOURCE_CLI = "cli"


class HermesGardenSession:
    """Programmatic integration for Hermes Agent sessions.

    Manages a Memory Garden session alongside a Hermes conversation.
    Each user message goes through the full garden lifecycle:

        Seed → Court → Growth → Harvest (before reply) → Brief → LLM → Observe (after reply)

    Usage::

        garden = MemoryGarden.local("./my_garden")
        session = HermesGardenSession(garden=garden)
        ctx = session.before_reply(user_message="I prefer dark mode.")
        # ... inject ctx.brief into Hermes prompt ...
        session.after_reply(user_message="I prefer dark mode.", assistant_reply="Got it.")
        session.close()
    """

    def __init__(
        self,
        *,
        garden: Any = None,
        garden_path: str | None = None,
        providers: Any | None = None,
        auto_open: bool = True,
        source: str = SOURCE_CLI,
    ) -> None:
        if garden is not None:
            from memory_garden.sdk import MemoryGarden

            if not isinstance(garden, MemoryGarden):
                raise TypeError(f"garden must be a MemoryGarden instance, got {type(garden).__name__}")
            self._garden = garden
        elif garden_path:
            from memory_garden.sdk import MemoryGarden

            self._garden = MemoryGarden.local(garden_path)
        else:
            from memory_garden.sdk import MemoryGarden

            self._garden = MemoryGarden.local(DEFAULT_GARDEN_PATH)

        self._skill = self._garden.as_skill()
        from memory_garden.integrations.adapters._cognitive_brief import resolve_provider_registry
        self._providers = resolve_provider_registry(self._garden, providers)
        if self._providers is not None:
            self._skill.configure_providers(self._providers)
        self._source = source
        self._is_open = False
        self._session_id: str | None = None
        self._last_user_message: str = ""

        if auto_open:
            self.open()

    # ── Lifecycle ──────────────────────────────────────────────────

    def open(self) -> str:
        """Open a garden session. Returns the session_id."""
        if self._is_open:
            return self._session_id or ""
        session_id = self._skill.open(metadata={"source": self._source})
        self._session_id = session_id
        self._is_open = True
        return session_id

    def close(self) -> Any:
        """Close the garden session and return feedback."""
        if not self._is_open:
            return None
        result = self._skill.close()
        self._is_open = False
        return result

    # ── Before / After hooks ───────────────────────────────────────

    def before_reply(
        self,
        user_message: str,
        *,
        conversation_history: list[dict[str, str]] | None = None,
        platform: str = SOURCE_CLI,
    ) -> "HermesGardenContext":
        """Called before Hermes replies to a user message.

        Args:
            user_message: The user's message text.
            conversation_history: Optional list of {role, content} dicts
                for richer context extraction.
            platform: Source platform identifier.

        Returns:
            A ``HermesGardenContext`` with the garden brief and metadata.
        """
        if not self._is_open:
            self.open()

        self._last_user_message = user_message

        # Build metadata from Hermes conversation context
        metadata: dict[str, Any] = {
            "source": self._source,
            "platform": platform,
        }
        if conversation_history:
            metadata["history_length"] = len(conversation_history)
            # Only pass the last few turns to avoid flooding
            recent = conversation_history[-6:]
            metadata["recent_turns"] = [
                {"role": m.get("role", ""), "preview": str(m.get("content", ""))[:200]}
                for m in recent
            ]

        from memory_garden.integrations.adapters._cognitive_brief import build_cognitive_skill_context

        ctx = build_cognitive_skill_context(
            garden=self._garden,
            skill=self._skill,
            providers=self._providers,
            user_message=user_message,
            metadata=metadata,
            max_candidates=5,
        )
        if ctx is None:
            ctx = self._skill.before(user_message, metadata=metadata)

        return HermesGardenContext(
            brief_text=ctx.brief_text,
            brief_dict=dict(ctx.brief_dict),
            session_id=self._session_id or "",
        )

    def after_reply(
        self,
        user_message: str | None = None,
        assistant_reply: str = "",
        *,
        error: str | None = None,
    ) -> None:
        """Called after Hermes has replied.

        Feeds both user_message and assistant_reply back to the garden
        for observation (seed extraction), court processing, and growth.

        Args:
            user_message: Override the last user message if needed.
            assistant_reply: Hermes' response text.
            error: If set, logs an error event instead of normal observation.
        """
        if not self._is_open:
            return

        msg = user_message if user_message else self._last_user_message

        if error:
            # Do not treat failed Hermes turns as memory observations.
            return

        # Observe the turn — both user message and assistant reply
        self._skill.after(msg, assistant_reply)

    # ── Context management ──────────────────────────────────────────

    @property
    def session_id(self) -> str | None:
        return self._session_id

    @property
    def is_open(self) -> bool:
        return self._is_open

    def get_stats(self) -> dict[str, Any]:
        """Return garden session stats for debugging."""
        if not self._is_open:
            return {"open": False}
        repo = self._garden.core.repository
        return {
            "open": True,
            "session_id": self._session_id,
            "seed_count": len(repo.list_seeds()),
            "memory_count": len(repo.list_memory_cards(include_greenhouse=True)),
        }


class HermesGardenContext:
    """Structured garden context returned to Hermes before replying.

    Hermes can inject ``brief_text`` into its system prompt or use
    ``brief_dict`` for structured reasoning.
    """

    def __init__(
        self,
        *,
        brief_text: str,
        brief_dict: dict[str, Any],
        session_id: str,
    ) -> None:
        self.brief_text = brief_text
        self.brief_dict = brief_dict
        self.session_id = session_id

    def to_prompt_snippet(self) -> str:
        """Format as a system prompt snippet for Hermes."""
        if not self.brief_text:
            return ""
        return (
            "<memory_garden_brief>\n"
            f"{self.brief_text}\n"
            "</memory_garden_brief>"
        )


# ── CLI entry point (for hermes hooks) ─────────────────────────────


def cli_before() -> None:
    """CLI entry: ``python -m ... before``.

    Reads ``HERMES_GARDEN_PATH``, ``HERMES_USER_MESSAGE`` from env.
    Prints garden context as JSON to stdout.
    """
    garden_path = os.environ.get("HERMES_GARDEN_PATH", DEFAULT_GARDEN_PATH)
    user_message = os.environ.get("HERMES_USER_MESSAGE", "")
    source = os.environ.get("HERMES_GARDEN_SOURCE", SOURCE_CLI)

    from memory_garden.integrations.adapters._providers import provider_registry_from_env
    from memory_garden.sdk import MemoryGarden

    garden = MemoryGarden.local(garden_path)
    providers = provider_registry_from_env(garden_path)
    session = HermesGardenSession(garden=garden, source=source, providers=providers)
    try:
        ctx = session.before_reply(user_message)
        output = {
            "session_id": ctx.session_id,
            "brief": ctx.brief_dict,
            "brief_text": ctx.brief_text,
        }
        print(json.dumps(output, ensure_ascii=False))
    finally:
        session.close()


def cli_after() -> None:
    """CLI entry: ``python -m ... after``.

    Reads env vars for user message and assistant reply.
    """
    garden_path = os.environ.get("HERMES_GARDEN_PATH", DEFAULT_GARDEN_PATH)
    user_message = os.environ.get("HERMES_USER_MESSAGE", "")
    assistant_reply = os.environ.get("HERMES_ASSISTANT_REPLY", "")
    source = os.environ.get("HERMES_GARDEN_SOURCE", SOURCE_CLI)

    from memory_garden.sdk import MemoryGarden

    garden = MemoryGarden.local(garden_path)
    session = HermesGardenSession(garden=garden, source=source)
    try:
        session.after_reply(user_message=user_message, assistant_reply=assistant_reply)
        print(json.dumps({"ok": True}, ensure_ascii=False))
    finally:
        session.close()


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else ""
    if command == "before":
        cli_before()
    elif command == "after":
        cli_after()
    else:
        print(f"Usage: python -m {__spec__.name} before|after", file=sys.stderr)
        sys.exit(1)
