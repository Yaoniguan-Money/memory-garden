"""OpenAI Codex CLI adapter — Memory Garden as a Codex CLI session wrapper.

Codex CLI (``codex``) is OpenAI's terminal coding agent, similar to
Claude Code.  It supports custom system prompts and can be wrapped
with a middleware that injects memory context.

Two patterns:

1. **System prompt injection**: modify the Codex system prompt to
   include the Garden Brief before each session.

2. **Session wrapper**: wrap every Codex CLI invocation with
   ``before()`` / ``after()`` calls.

Usage (programmatic)::

    from memory_garden.sdk import MemoryGarden
    from memory_garden.integrations.adapters.codex import CodexSession

    garden = MemoryGarden.local("./my_garden")
    codex = CodexSession(garden=garden)

    # Before a Codex session
    system_prompt = codex.build_system_prompt(
        base_system_prompt="You are a helpful coding assistant."
    )

    # Start Codex with the modified system prompt
    # $ codex --system-prompt-file /tmp/prompt.txt

    # After the session
    codex.after("Codex session completed")

This module has **zero hard dependency** on the Codex CLI or OpenAI SDK.
"""

from __future__ import annotations

from typing import Any


class CodexSession:
    """Memory Garden integration for OpenAI Codex CLI sessions."""

    def __init__(self, *, garden: Any, garden_path: str | None = None, providers: Any | None = None) -> None:
        from memory_garden.sdk import MemoryGarden
        from memory_garden.skill import GardenSkill
        from memory_garden.integrations.adapters._cognitive_brief import resolve_provider_registry

        self._garden: MemoryGarden = garden
        self._skill: GardenSkill = garden.as_skill()
        self._providers = resolve_provider_registry(garden, providers)
        if self._providers is not None:
            self._skill.configure_providers(self._providers)
        self._garden_path = garden_path or str(garden.home.root)
        self._is_open = False

    @property
    def garden(self) -> Any:
        return self._garden

    @property
    def skill(self) -> Any:
        return self._skill

    def build_system_prompt(
        self,
        base_system_prompt: str = "",
        *,
        user_message: str | None = None,
    ) -> str:
        """Return a system prompt augmented with the Garden Brief.

        Use this as the Codex system prompt::

            codex = CodexSession(garden=garden)
            prompt = codex.build_system_prompt("You are a helpful assistant.")
            with open("/tmp/codex_prompt.txt", "w") as f:
                f.write(prompt)
            # $ codex --system-prompt-file /tmp/codex_prompt.txt
        """
        if not self._is_open:
            self._skill.open()
            self._is_open = True

        msg = user_message or "[Codex CLI session]"
        ctx = self._before_context(msg)

        parts = [base_system_prompt] if base_system_prompt else []
        if ctx.brief_text.strip():
            parts.append("\n## Memory Garden Context\n")
            parts.append("The following is context from the user's memory garden.")
            parts.append("Use it to personalize your responses:\n")
            parts.append(ctx.brief_text)

        return "\n".join(parts)

    def before(self, user_message: str | None = None) -> dict[str, Any]:
        """Prepare garden context before a Codex session.

        Returns a dict with ``brief_text`` and ``session_id``.
        """
        if not self._is_open:
            self._skill.open()
            self._is_open = True

        ctx = self._before_context(user_message or "[Codex CLI session]")
        return {"brief_text": ctx.brief_text, "session_id": ctx.session_id}

    def _before_context(self, user_message: str) -> Any:
        from memory_garden.integrations.adapters._cognitive_brief import build_cognitive_skill_context

        ctx = build_cognitive_skill_context(
            garden=self._garden,
            skill=self._skill,
            providers=self._providers,
            user_message=user_message,
            metadata={"adapter": "codex", "source_role": "user"},
            max_candidates=5,
        )
        if ctx is not None:
            return ctx
        return self._skill.before(user_message)

    def after(self, assistant_reply: str | None = None) -> None:
        """Observe the Codex session outcome in the garden."""
        if self._is_open:
            self._skill.after(
                "[Codex CLI session]",
                assistant_reply or "[Codex session completed]",
            )

    def close(self) -> Any:
        if self._is_open:
            self._is_open = False
            return self._skill.close()
        return None


# ── Convenience: memory-garden codex CLI subcommand ─────────────────


def codex_system_prompt_cmd(garden_path: str = "./.memory_garden") -> int:
    """Generate a Codex-compatible system prompt file.

    Usage::

        python -c "from memory_garden.integrations.adapters.codex import codex_system_prompt_cmd; codex_system_prompt_cmd()"
    """
    from memory_garden.integrations.adapters._providers import provider_registry_from_env
    from memory_garden.sdk import MemoryGarden

    garden = MemoryGarden.local(garden_path)
    providers = provider_registry_from_env(garden_path)
    session = CodexSession(garden=garden, providers=providers)
    prompt = session.build_system_prompt("You are a helpful coding assistant.")
    print(prompt)
    session.close()
    garden.close()
    return 0
