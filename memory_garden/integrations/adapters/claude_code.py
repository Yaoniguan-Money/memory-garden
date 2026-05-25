"""Claude Code adapter — Memory Garden as Claude Code hooks.

Hooks into Claude Code via ``UserPromptSubmit`` and ``Stop`` events.
Configure in ``.claude/settings.json``::

    {
      "hooks": {
        "UserPromptSubmit": [
          {
            "matcher": "",
            "hooks": [
              {
                "type": "command",
                "command": "python -m memory_garden.integrations.adapters.claude_code before",
                "timeout": 10
              }
            ]
          }
        ],
        "Stop": [
          {
            "matcher": "",
            "hooks": [
              {
                "type": "command",
                "command": "python -m memory_garden.integrations.adapters.claude_code after",
                "timeout": 10
              }
            ]
          }
        ]
      }
    }

Or use programmatically::

    from memory_garden.sdk import MemoryGarden
    from memory_garden.integrations.adapters.claude_code import ClaudeCodeSession

    garden = MemoryGarden.local("./my_garden")
    session = ClaudeCodeSession(garden=garden)
    context = session.before(user_message="...", conversation_history=[...])
    # ... inject context into your Claude Code session ...
    session.after(assistant_reply="...")
    session.close()
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import time
from contextlib import contextmanager
from typing import Any

DEFAULT_GARDEN_PATH = os.path.expanduser("~/.memory_garden")
_STATE_FILE = os.path.join(DEFAULT_GARDEN_PATH, "claude_code_state.json")
_LOCK_FILE = os.path.join(DEFAULT_GARDEN_PATH, "claude_code_state.lock")
_MAX_STDIN_BYTES = 64 * 1024
_MAX_STATE_BYTES = 256 * 1024
_MAX_TRANSCRIPT_BYTES = 2 * 1024 * 1024
_MAX_USER_MESSAGE_CHARS = 12_000
_STALE_LOCK_SECONDS = 30.0
_TRANSCRIPT_SUFFIXES = {".json", ".jsonl"}


@contextmanager
def _state_lock(timeout: float = 5.0):
    os.makedirs(os.path.dirname(_LOCK_FILE), exist_ok=True)
    deadline = time.monotonic() + timeout
    fd: int | None = None
    while fd is None:
        try:
            fd = os.open(_LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                if time.time() - os.path.getmtime(_LOCK_FILE) > _STALE_LOCK_SECONDS:
                    os.unlink(_LOCK_FILE)
                    continue
            except OSError:
                pass
            if time.monotonic() >= deadline:
                raise TimeoutError("Claude Code state lock timed out")
            time.sleep(0.05)
    try:
        yield
    finally:
        os.close(fd)
        try:
            os.unlink(_LOCK_FILE)
        except FileNotFoundError:
            pass


def _load_state() -> dict[str, Any]:
    try:
        with _state_lock():
            if os.path.getsize(_STATE_FILE) > _MAX_STATE_BYTES:
                return {}
            with open(_STATE_FILE, encoding="utf-8") as f:
                return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError, TimeoutError):
        return {}


def _save_state(state: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(_STATE_FILE), exist_ok=True)
    safe_state = dict(state)
    if "last_user_message" in safe_state:
        safe_state["last_user_message"] = _normalize_user_message(safe_state["last_user_message"])
    with _state_lock():
        fd, tmp = tempfile.mkstemp(prefix="claude_code_state.", suffix=".json", dir=os.path.dirname(_STATE_FILE))
        try:
            try:
                os.chmod(tmp, 0o600)
            except OSError:
                pass
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(safe_state, f, ensure_ascii=False, sort_keys=True)
            os.replace(tmp, _STATE_FILE)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)


def _normalize_user_message(value: Any) -> str:
    text = _message_content_to_text(value).strip()
    if len(text) > _MAX_USER_MESSAGE_CHARS:
        text = text[:_MAX_USER_MESSAGE_CHARS]
    return text


def _first_text(*values: Any) -> str:
    for value in values:
        text = _normalize_user_message(value)
        if text:
            return text
    return ""


def _message_content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") in (None, "text"):
                    part = item.get("text")
                    if isinstance(part, str):
                        parts.append(part)
            elif isinstance(item, str):
                parts.append(item)
        return " ".join(parts)
    return ""


def _extract_last_user_message(container: Any) -> str:
    if isinstance(container, dict):
        if container.get("role") == "user":
            text = _normalize_user_message(container.get("content", ""))
            if text:
                return text
        messages = container.get("messages")
        if isinstance(messages, list):
            return _extract_last_user_message(messages)
        message = container.get("message")
        if isinstance(message, dict):
            return _extract_last_user_message(message)
        return ""
    if isinstance(container, list):
        for item in reversed(container):
            text = _extract_last_user_message(item)
            if text:
                return text
    return ""


def _read_transcript_user_message(transcript_path: Any) -> str:
    if not isinstance(transcript_path, str) or not transcript_path.strip():
        return ""
    try:
        path = Path(transcript_path).expanduser().resolve(strict=True)
    except (OSError, RuntimeError):
        return ""
    if path.suffix.casefold() not in _TRANSCRIPT_SUFFIXES:
        return ""
    try:
        stat = path.stat()
    except OSError:
        return ""
    if not path.is_file() or stat.st_size > _MAX_TRANSCRIPT_BYTES:
        return ""
    try:
        if path.suffix.casefold() == ".jsonl":
            last = ""
            with path.open(encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        text = _extract_last_user_message(json.loads(line))
                    except json.JSONDecodeError:
                        continue
                    if text:
                        last = text
            return last
        with path.open(encoding="utf-8") as f:
            return _extract_last_user_message(json.load(f))
    except (OSError, json.JSONDecodeError):
        return ""


class ClaudeCodeSession:
    """Programmatic integration for Claude Code sessions.

    Usage in a custom Claude Code setup::

        garden = MemoryGarden.local("./my_garden")
        cc = ClaudeCodeSession(garden=garden)

        # Before Claude generates a reply
        ctx = cc.before(user_message, conversation_history)

        # After Claude replies
        cc.after(assistant_reply)

        cc.close()
    """

    def __init__(
        self,
        *,
        garden: Any,
        garden_path: str | None = None,
        providers: Any | None = None,
    ) -> None:
        from memory_garden.sdk import MemoryGarden
        from memory_garden.skill import GardenSkill

        self._garden: MemoryGarden = garden
        self._skill: GardenSkill = garden.as_skill()
        self._providers = providers or getattr(garden, "_claude_code_provider_registry", None)
        if self._providers is not None:
            self._skill.configure_providers(self._providers)
        self._garden_path = garden_path or str(garden.home.root)
        self._session_started: bool = False

    @property
    def garden(self) -> Any:
        return self._garden

    @property
    def skill(self) -> Any:
        return self._skill

    def _ensure_open(self) -> None:
        """Open a garden session if not already opened by this instance."""
        if not self._session_started:
            self._skill.open()
            self._session_started = True

    def before(
        self,
        user_message: str | None = None,
        *,
        conversation_history: list[dict] | None = None,
    ) -> dict[str, Any]:
        """Prepare garden context before Claude generates a reply.

        Returns a dict with ``brief`` (text to inject) and ``messages``
        (OpenAI-format message list with brief injected).
        """
        self._ensure_open()

        msg = user_message or ""
        if not msg and conversation_history:
            for m in reversed(conversation_history):
                if m.get("role") == "user":
                    msg = str(m.get("content", ""))
                    break

        if not msg:
            msg = "[Claude Code session — no user message extracted]"

        ctx = self._cognitive_before(msg, conversation_history=conversation_history)
        if ctx is None:
            ctx = self._skill.before(msg, messages=conversation_history)
        return {
            "brief": ctx.brief_text,
            "session_id": ctx.session_id,
            "messages": ctx.messages,
            "garden_path": self._garden_path,
        }

    def _cognitive_before(
        self,
        user_message: str,
        *,
        conversation_history: list[dict] | None = None,
    ) -> Any | None:
        from memory_garden.integrations.adapters._cognitive_brief import build_cognitive_skill_context

        return build_cognitive_skill_context(
            garden=self._garden,
            skill=self._skill,
            providers=self._providers,
            user_message=user_message,
            metadata={"adapter": "claude_code", "source_role": "user"},
            messages=conversation_history,
            max_candidates=5,
        )

    def after(self, assistant_reply: str | None = None, *, user_message: str | None = None) -> None:
        """Observe Claude's reply in the garden."""
        self._ensure_open()
        self._skill.after(
            user_message or "[Claude Code reply]",
            assistant_reply or "[Claude Code response]",
        )

    def close(self) -> Any:
        if self._session_started:
            self._session_started = False
            return self._skill.close()
        return None


# ── CLI entry point for Claude Code hooks ──────────────────────────


def _provider_registry_from_env():
    from memory_garden.integrations.adapters._providers import provider_registry_from_env

    return provider_registry_from_env(DEFAULT_GARDEN_PATH)


def _load_garden():
    from memory_garden.sdk import MemoryGarden

    providers = _provider_registry_from_env()
    garden = MemoryGarden.local(DEFAULT_GARDEN_PATH)
    if providers is not None:
        garden._claude_code_provider_registry = providers
        garden.as_skill().configure_providers(providers)
    return garden


def _read_stdin_json() -> dict[str, Any]:
    try:
        raw = sys.stdin.buffer.read1(_MAX_STDIN_BYTES)
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, EOFError, UnicodeDecodeError, AttributeError):
        return {}


def _cmd_hook_before():
    """UserPromptSubmit hook: harvest garden memories, inject brief into context.

    Reads the user prompt from stdin JSON (Claude Code passes
    ``{"prompt": "...", "session_id": "...", ...}``).
    Outputs JSON with ``hookSpecificOutput.additionalContext`` so the
    garden brief is injected into Claude's system prompt.
    """
    data = _read_stdin_json()
    user_message = _first_text(
        data.get("prompt"),
        data.get("text"),
        data.get("message"),
        data.get("content"),
        data.get("user_message"),
        os.environ.get("CLAUDE_PROMPT"),
        os.environ.get("MEMORY_GARDEN_MSG"),
    )
    history_raw = data.get("messages", data.get("history", []))
    history = history_raw if isinstance(history_raw, list) else []
    session_id = data.get("session_id", data.get("conversation_id", "") or
                         os.environ.get("CLAUDE_SESSION_ID", ""))

    garden = _load_garden()
    cc = ClaudeCodeSession(garden=garden)
    result = cc.before(user_message, conversation_history=history)

    # 保存到 state 文件供 after hook 使用
    if user_message:
        _save_state({"last_user_message": user_message, "last_session_id": session_id})
    garden.close()

    additional_context = ""
    if result["brief"]:
        additional_context = f"[Memory Garden Brief]\n{result['brief']}\n"

    output: dict[str, Any] = {
        "continue": True,
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": additional_context,
        },
    }
    print(json.dumps(output))
    garden.close()


def _cmd_hook_after():
    """Stop hook: observe the turn and persist the user message for next before hook.

    优先从 stdin 读 transcript_path 提取用户消息，其次从 env var，最后从 state 文件。
    """
    data = _read_stdin_json()
    user_message = _first_text(
        data.get("prompt"),
        data.get("text"),
        data.get("user_message"),
        os.environ.get("MEMORY_GARDEN_MSG"),
    )

    # 从 transcript 文件提取最后一条用户消息（Stop 事件特有）
    if not user_message:
        user_message = _read_transcript_user_message(data.get("transcript_path"))

    if not user_message:
        state = _load_state()
        user_message = _normalize_user_message(state.get("last_user_message", ""))

    # 保存到 state 文件，供下一轮 before hook 检索
    if user_message:
        state = _load_state()
        state["last_user_message"] = user_message
        _save_state(state)

    garden = _load_garden()
    cc = ClaudeCodeSession(garden=garden)
    cc.after(assistant_reply="[Claude Code response]", user_message=user_message or None)

    if user_message:
        try:
            cc.skill.remember_memory(
                user_message,
                mode="trusted",
                metadata={"adapter": "claude_code", "source_role": "user"},
            )
        except Exception:
            try:
                cc.skill.remember(user_message, mode="court")
            except Exception:
                pass

    # 每 8 条消息触发一次梦境周期——合并重复记忆、识别主题聚类
    state = _load_state()
    dream_count = state.get("dream_turn_counter", 0) + 1
    if dream_count >= 8:
        try:
            record = garden.core.dream()
            dream_count = 0
        except Exception:
            pass
    state["dream_turn_counter"] = dream_count
    _save_state(state)

    cc.close()
    garden.close()

    print(json.dumps({"continue": True}))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "before"
    if cmd == "before":
        _cmd_hook_before()
    elif cmd == "after":
        _cmd_hook_after()
    else:
        print(f"Unknown command: {cmd}", file=sys.stderr)
        sys.exit(1)
