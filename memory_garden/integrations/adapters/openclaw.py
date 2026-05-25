"""OpenClaw adapter — Memory Garden as an OpenClaw session wrapper.

OpenClaw (``openclaw``) is an open-source terminal coding agent.
This adapter provides two patterns:

1. **Session wrapper**: ``OpenClawSession`` wraps every OpenClaw CLI
   invocation with ``before()`` / ``after()`` calls.

2. **System prompt injection**: ``build_system_prompt()`` augments the
   OpenClaw system prompt with the Garden Brief.

Usage (programmatic)::

    from memory_garden.sdk import MemoryGarden
    from memory_garden.integrations.adapters.openclaw import OpenClawSession

    garden = MemoryGarden.local("./my_garden")
    oc = OpenClawSession(garden=garden)

    # Before an OpenClaw session
    prompt = oc.build_system_prompt("You are a helpful coding assistant.")
    # $ openclaw --system-prompt-file /tmp/prompt.txt

    # Or use the hook pattern
    ctx = oc.before("Fix the auth bug in login.py")
    # ... run OpenClaw with ctx brief ...
    oc.after("Fixed the auth bug by updating the session token logic.")

Usage — CLI hooks::

    hooks:
      before_reply:
        - command: python -m memory_garden.integrations.adapters.openclaw before
          timeout: 5000
      after_reply:
        - command: python -m memory_garden.integrations.adapters.openclaw after
          timeout: 5000

This module has **zero hard dependency** on the OpenClaw CLI.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

DEFAULT_GARDEN_PATH = os.path.expanduser("~/.memory_garden")
_STATE_FILE = os.path.join(DEFAULT_GARDEN_PATH, "openclaw_state.json")


class OpenClawSession:
    """Memory Garden integration for OpenClaw CLI sessions.

    Usage::

        garden = MemoryGarden.local("./my_garden")
        oc = OpenClawSession(garden=garden)

        prompt = oc.build_system_prompt("You are a coding assistant.")
        # $ openclaw --system-prompt-file /tmp/prompt.txt
    """

    def __init__(
        self,
        *,
        garden: Any,
        garden_path: str | None = None,
        providers: Any | None = None,
    ) -> None:
        from memory_garden.integrations.adapters._cognitive_brief import resolve_provider_registry
        from memory_garden.sdk import MemoryGarden
        from memory_garden.skill import GardenSkill

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

    # ── Lifecycle ──────────────────────────────────────────────────

    def open(self) -> None:
        if not self._is_open:
            self._skill.open()
            self._is_open = True

    def close(self) -> Any:
        if self._is_open:
            self._is_open = False
            return self._skill.close()
        return None

    # ── Before / After hooks ───────────────────────────────────────

    def before(self, user_message: str | None = None) -> dict[str, Any]:
        """Prepare garden context before an OpenClaw session.

        Returns a dict with ``brief_text`` and ``session_id``.
        """
        if not self._is_open:
            self.open()

        ctx = self._before_context(user_message or "[OpenClaw session]")
        return {"brief_text": ctx.brief_text, "session_id": ctx.session_id}

    def _before_context(self, user_message: str) -> Any:
        from memory_garden.integrations.adapters._cognitive_brief import build_cognitive_skill_context

        ctx = build_cognitive_skill_context(
            garden=self._garden,
            skill=self._skill,
            providers=self._providers,
            user_message=user_message,
            metadata={"adapter": "openclaw", "source_role": "user"},
            max_candidates=5,
        )
        if ctx is not None:
            return ctx
        return self._skill.before(user_message)

    def after(
        self,
        assistant_reply: str | None = None,
        *,
        user_message: str | None = None,
    ) -> None:
        """Observe the OpenClaw session outcome."""
        if not self._is_open:
            self.open()
        self._skill.after(
            user_message or "[OpenClaw session]",
            assistant_reply or "[OpenClaw session completed]",
        )

    # ── System prompt injection ────────────────────────────────────

    def build_system_prompt(
        self,
        base_system_prompt: str = "",
        *,
        user_message: str | None = None,
    ) -> str:
        """Augment the OpenClaw system prompt with the Garden Brief."""
        if not self._is_open:
            self.open()

        ctx = self._before_context(user_message or "[OpenClaw session]")

        parts = [base_system_prompt] if base_system_prompt else []
        if ctx.brief_text.strip():
            parts.append("\n## Memory Garden Context\n")
            parts.append("The following is context from the user's memory garden.")
            parts.append("Use it to personalize your responses:\n")
            parts.append(ctx.brief_text)

        return "\n".join(parts)


# ── CLI entry point for OpenClaw hooks ─────────────────────────────


def _load_state() -> dict[str, Any]:
    try:
        if os.path.isfile(_STATE_FILE):
            with open(_STATE_FILE, encoding="utf-8") as f:
                return json.load(f)
    except (json.JSONDecodeError, OSError):
        pass
    return {}


def _save_state(state: dict[str, Any]) -> None:
    try:
        os.makedirs(os.path.dirname(_STATE_FILE), exist_ok=True)
        tmp = os.path.join(os.path.dirname(_STATE_FILE), ".openclaw_state.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False)
        os.replace(tmp, _STATE_FILE)
    except OSError:
        try:
            if "tmp" in locals() and os.path.exists(tmp):
                os.unlink(tmp)
        except OSError:
            pass


def _cmd_hook_before() -> None:
    """OpenClaw before_reply hook: harvest garden memories, inject brief.

    Reads ``OPENCLAW_USER_MESSAGE`` from env.
    Prints garden context as JSON to stdout.
    """
    from memory_garden.integrations.adapters._providers import provider_registry_from_env
    from memory_garden.sdk import MemoryGarden

    garden_path = os.environ.get("MEMORY_GARDEN_PATH", DEFAULT_GARDEN_PATH)
    user_message = os.environ.get("OPENCLAW_USER_MESSAGE", "")
    garden = MemoryGarden.local(garden_path)
    providers = provider_registry_from_env(garden_path)

    session = OpenClawSession(garden=garden, providers=providers)
    ctx = session.before(user_message)

    state = _load_state()
    if user_message:
        state["last_user_message"] = user_message
        _save_state(state)

    output = {
        "session_id": ctx["session_id"],
        "brief": ctx["brief_text"],
    }
    print(json.dumps(output, ensure_ascii=False))
    session.close()
    garden.close()


def _cmd_hook_after() -> None:
    """OpenClaw after_reply hook: observe the completed turn.

    Reads ``OPENCLAW_ASSISTANT_REPLY`` and last user message from state.
    """
    from memory_garden.integrations.adapters._providers import provider_registry_from_env
    from memory_garden.sdk import MemoryGarden

    garden_path = os.environ.get("MEMORY_GARDEN_PATH", DEFAULT_GARDEN_PATH)
    assistant_reply = os.environ.get("OPENCLAW_ASSISTANT_REPLY", "")

    state = _load_state()
    user_message = state.get("last_user_message", "") or os.environ.get("OPENCLAW_USER_MESSAGE", "")
    garden = MemoryGarden.local(garden_path)
    providers = provider_registry_from_env(garden_path)

    session = OpenClawSession(garden=garden, providers=providers)
    session.after(assistant_reply, user_message=user_message)

    session.close()
    garden.close()

    print(json.dumps({"ok": True}, ensure_ascii=False))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "before"
    if cmd == "before":
        _cmd_hook_before()
    elif cmd == "after":
        _cmd_hook_after()
    else:
        print(f"Usage: python -m memory_garden.integrations.adapters.openclaw before|after", file=sys.stderr)
        sys.exit(1)
