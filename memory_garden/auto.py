"""AutoMemory — one-line drop-in memory for any Python LLM process.

Intercepts common LLM SDK calls (OpenAI, Anthropic) and injects
Memory Garden context before every call, then observes after.

Usage::

    from memory_garden.auto import AutoMemory

    # One line — starts intercepting immediately
    auto = AutoMemory()
    r = openai_client.chat.completions.create(...)  # auto-injected

    auto.stop()   # explicit stop
    # or: with AutoMemory() as auto: ...

Zero configuration by default.  Works with:
- openai.OpenAI().chat.completions.create()
- anthropic.Anthropic().messages.create()
- Any custom function registered via auto.hook(fn)

No data leaves the machine.  No API keys needed for the memory layer.
"""

from __future__ import annotations

import atexit
import threading
from pathlib import Path
from typing import Any, Callable

from memory_garden.skill import GardenSkill


class _AutoMemoryState:
    """Thread-safe singleton for the active AutoMemory instance."""

    _lock = threading.Lock()
    _active: AutoMemory | None = None

    @classmethod
    def get(cls) -> AutoMemory | None:
        with cls._lock:
            return cls._active

    @classmethod
    def set(cls, instance: AutoMemory | None) -> None:
        with cls._lock:
            cls._active = instance


class AutoMemory:
    """One-line memory layer that auto-intercepts LLM calls.

    Uses monkey-patching at the method level.  All patches are
    reversed on ``stop()`` or ``__exit__()``.
    """

    def __init__(
        self,
        *,
        garden_path: str | Path | None = None,
        open_client: object | None = None,
        anthropic_client: object | None = None,
        auto_discover: bool = True,
    ) -> None:
        path = Path(garden_path) if garden_path else Path.home() / ".memory-garden-auto"
        from memory_garden.sdk import MemoryGarden

        self._garden = MemoryGarden.local(path)
        self._skill: GardenSkill = self._garden.as_skill()
        self._patches: list[tuple[object, str, Callable]] = []
        self._open_client = open_client
        self._anthropic_client = anthropic_client
        self._auto_discover = auto_discover
        self._started = False
        self._patch_status: dict[str, bool] = {"openai": False, "anthropic": False}
        self._patch_errors: list[dict[str, str]] = []

    # ── Lifecycle ─────────────────────────────────────────────────

    @property
    def skill(self) -> GardenSkill:
        if self._started and not self._skill.is_open:
            self._skill.open()
        return self._skill

    @property
    def garden(self) -> Any:
        return self._garden

    @property
    def patch_errors(self) -> list[dict[str, str]]:
        return [dict(item) for item in self._patch_errors]

    @property
    def diagnostics(self) -> dict[str, Any]:
        return {
            "started": self._started,
            "patched": dict(self._patch_status),
            "patch_errors": self.patch_errors,
        }

    def start(self) -> AutoMemory:
        """Begin intercepting LLM calls.  Idempotent.

        Returns self for use in ``auto = AutoMemory().start()``.
        """
        if self._started:
            return self
        self._started = True
        _AutoMemoryState.set(self)
        self._patch_status = {"openai": False, "anthropic": False}
        self._patch_errors = []

        # Open session
        self._skill.open()

        # Try auto-discover clients from common variable names
        if self._auto_discover:
            if self._open_client is None:
                self._open_client = _discover_openai()
            if self._anthropic_client is None:
                self._anthropic_client = _discover_anthropic()

        if self._open_client is not None:
            self._patch_openai(self._open_client)

        if self._anthropic_client is not None:
            self._patch_anthropic(self._anthropic_client)

        atexit.register(self.stop)
        return self

    def stop(self) -> None:
        """Stop intercepting and restore all patches."""
        if not self._started:
            return
        self._started = False
        _AutoMemoryState.set(None)

        # Restore original methods
        for obj, attr, original in reversed(self._patches):
            setattr(obj, attr, original)
        self._patches.clear()

        # Close garden session
        try:
            self._skill.close()
        except Exception:
            pass
        self._garden.close()

        try:
            atexit.unregister(self.stop)
        except Exception:
            pass

    def __enter__(self) -> AutoMemory:
        return self.start()

    def __exit__(self, *args: Any) -> None:
        self.stop()

    # ── Generic hook ─────────────────────────────────────────────

    def hook(
        self,
        fn: Callable,
        *,
        extract_user_msg: Callable[[tuple, dict], str] | None = None,
        extract_reply: Callable[[Any], str] | None = None,
    ) -> Callable:
        """Wrap a custom LLM-calling function with memory injection.

        *extract_user_msg* receives (args, kwargs) and returns the user text.
        *extract_reply* receives the return value and returns the assistant text.
        """
        skill = self._skill
        auto = self

        def _wrapper(*args: Any, **kwargs: Any) -> Any:
            user_text = ""
            if extract_user_msg:
                user_text = extract_user_msg(args, kwargs)

            if user_text:
                ctx = skill.before(user_text)
                if ctx.brief_text.strip():
                    # Inject brief into kwargs if there's a messages key
                    if "messages" in kwargs and ctx.messages:
                        kwargs = dict(kwargs)
                        kwargs["messages"] = ctx.messages

            result = fn(*args, **kwargs)

            if user_text:
                reply = ""
                if extract_reply:
                    reply = extract_reply(result)
                skill.after(user_text, reply)

            return result

        auto._patches.append((fn, "__call__", fn))
        return _wrapper

    # ── Internal patching ────────────────────────────────────────

    def _patch_openai(self, client: object) -> None:
        try:
            chat = client.chat
            completions = chat.completions
            original = completions.create
            skill = self._skill

            def _patched_create(*args: Any, **kwargs: Any) -> Any:
                messages = kwargs.get("messages", args[0] if args else [])
                user_text = ""
                for m in reversed(messages):
                    if isinstance(m, dict) and m.get("role") == "user":
                        user_text = str(m.get("content", ""))
                        break

                if user_text:
                    ctx = skill.before(user_text, messages=list(messages))
                    if ctx.messages:
                        if args:
                            args = (ctx.messages, *args[1:])
                        else:
                            kwargs = dict(kwargs)
                            kwargs["messages"] = ctx.messages

                result = original(*args, **kwargs)

                if user_text:
                    try:
                        reply = result.choices[0].message.content
                        if reply:
                            skill.after(user_text, reply)
                    except (AttributeError, IndexError) as exc:
                        self._record_patch_error("openai", "extract_reply", exc)

                return result

            completions.create = _patched_create
            self._patches.append((completions, "create", original))
            self._patch_status["openai"] = True
        except Exception as exc:
            self._record_patch_error("openai", "patch_create", exc)

    def _patch_anthropic(self, client: object) -> None:
        try:
            messages_obj = client.messages
            original = messages_obj.create
            skill = self._skill

            def _patched_create(*args: Any, **kwargs: Any) -> Any:
                messages = kwargs.get("messages", args[0] if args else [])
                user_text = ""
                for m in reversed(messages):
                    if isinstance(m, dict) and m.get("role") == "user":
                        user_text = str(m.get("content", ""))
                        break

                if user_text:
                    ctx = skill.before(user_text, messages=list(messages))
                    if ctx.messages:
                        if args:
                            args = (ctx.messages, *args[1:])
                        else:
                            kwargs = dict(kwargs)
                            kwargs["messages"] = ctx.messages

                result = original(*args, **kwargs)

                if user_text:
                    try:
                        reply = ""
                        for block in result.content:
                            if hasattr(block, "text"):
                                reply += block.text
                        if reply:
                            skill.after(user_text, reply)
                    except Exception as exc:
                        self._record_patch_error("anthropic", "extract_reply", exc)

                return result

            messages_obj.create = _patched_create
            self._patches.append((messages_obj, "create", original))
            self._patch_status["anthropic"] = True
        except Exception as exc:
            self._record_patch_error("anthropic", "patch_create", exc)

    def _record_patch_error(self, provider: str, stage: str, exc: Exception) -> None:
        self._patch_errors.append(
            {
                "provider": provider,
                "stage": stage,
                "error_type": type(exc).__name__,
                "message": str(exc),
            }
        )


# ── Client discovery ────────────────────────────────────────────────


def _discover_openai() -> object | None:
    """Look for an openai.OpenAI instance in common globals."""
    import sys

    for mod_name in ("__main__",):
        mod = sys.modules.get(mod_name)
        if mod is None:
            continue
        for name in ("client", "openai_client", "llm_client", "openai"):
            obj = getattr(mod, name, None)
            if obj is not None and hasattr(obj, "chat"):
                return obj
    return None


def _discover_anthropic() -> object | None:
    """Look for an anthropic.Anthropic instance in common globals."""
    import sys

    for mod_name in ("__main__",):
        mod = sys.modules.get(mod_name)
        if mod is None:
            continue
        for name in ("client", "anthropic_client", "llm_client", "anthropic"):
            obj = getattr(mod, name, None)
            if obj is not None and hasattr(obj, "messages"):
                return obj
    return None
