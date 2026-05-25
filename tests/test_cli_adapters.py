"""Tests for Claude Code and Codex CLI adapters."""

import json
import os

from memory_garden.core.models import MemoryCard
from memory_garden.providers import ProviderPolicy, ProviderRegistry, TextCompletionResult
from memory_garden.sdk import MemoryGarden


def _make_garden(tmp_path):
    return MemoryGarden.local(tmp_path / "garden")


# ── Claude Code adapter ─────────────────────────────────────────────


def test_claude_code_imports():
    from memory_garden.integrations.adapters.claude_code import ClaudeCodeSession
    assert ClaudeCodeSession is not None


def test_claude_code_session_before(tmp_path):
    from memory_garden.integrations.adapters.claude_code import ClaudeCodeSession

    garden = _make_garden(tmp_path)
    cc = ClaudeCodeSession(garden=garden)
    result = cc.before("I prefer dark mode.")
    assert "session_id" in result
    assert "brief" in result
    assert "messages" in result
    cc.close()
    garden.close()


def test_claude_code_session_with_history(tmp_path):
    from memory_garden.integrations.adapters.claude_code import ClaudeCodeSession

    garden = _make_garden(tmp_path)
    cc = ClaudeCodeSession(garden=garden)
    result = cc.before(
        conversation_history=[
            {"role": "user", "content": "I prefer dark mode."},
            {"role": "assistant", "content": "Got it!"},
            {"role": "user", "content": "Can you apply that?"},
        ],
    )
    assert result["session_id"] is not None
    cc.close()
    garden.close()


class _ClaudeBriefLLM:
    name = "claude-brief-llm"
    is_remote = False

    def complete_text(self, *, system, user, context):
        return TextCompletionResult(
            text="用户偏好简短的中文回复，技术术语保留英文。",
            model=self.name,
        )


def test_claude_code_before_uses_llm_brief_writer_when_provider_available(tmp_path):
    from memory_garden.integrations.adapters.claude_code import ClaudeCodeSession

    garden = _make_garden(tmp_path)
    garden.core.repository.save_memory_card(
        MemoryCard(
            title="回复偏好",
            essence="用户偏好简短的中文回复，技术术语保留英文。",
            fragrance="用户偏好简短的中文回复，技术术语保留英文。",
            thorns="不要过度推断。",
            tags=["回复", "中文"],
        )
    )
    providers = ProviderRegistry(
        policy=ProviderPolicy(allow_raw_user_text=True),
        llm=_ClaudeBriefLLM(),
    )
    cc = ClaudeCodeSession(garden=garden, providers=providers)

    result = cc.before("回复风格")

    assert "[use] 用户偏好简短的中文回复，技术术语保留英文。" in result["brief"]
    assert "参考以下记忆标识" not in result["brief"]
    cc.close()
    garden.close()


def test_claude_code_full_cycle(tmp_path):
    from memory_garden.integrations.adapters.claude_code import ClaudeCodeSession

    garden = _make_garden(tmp_path)
    cc = ClaudeCodeSession(garden=garden)
    cc.before("I prefer dark mode.")
    cc.after("I've applied dark mode to your settings.")
    fb = cc.close()
    assert fb is not None
    garden.close()


def test_claude_code_reads_json_transcript_user_message(tmp_path):
    from memory_garden.integrations.adapters.claude_code import _read_transcript_user_message

    transcript = tmp_path / "transcript.json"
    transcript.write_text(
        json.dumps({
            "messages": [
                {"role": "assistant", "content": "old"},
                {"role": "user", "content": [{"type": "text", "text": "final user"}]},
            ]
        }),
        encoding="utf-8",
    )

    assert _read_transcript_user_message(str(transcript)) == "final user"


def test_claude_code_reads_last_jsonl_transcript_user_message(tmp_path):
    from memory_garden.integrations.adapters.claude_code import _read_transcript_user_message

    transcript = tmp_path / "transcript.jsonl"
    transcript.write_text(
        "\n".join([
            json.dumps({"message": {"role": "user", "content": "first"}}),
            json.dumps({"message": {"role": "assistant", "content": "ignored"}}),
            json.dumps({"message": {"role": "user", "content": "second"}}),
        ]),
        encoding="utf-8",
    )

    assert _read_transcript_user_message(str(transcript)) == "second"


def test_claude_code_rejects_non_json_transcript_path(tmp_path):
    from memory_garden.integrations.adapters.claude_code import _read_transcript_user_message

    transcript = tmp_path / "secret.txt"
    transcript.write_text(
        json.dumps({"messages": [{"role": "user", "content": "do not read"}]}),
        encoding="utf-8",
    )

    assert _read_transcript_user_message(str(transcript)) == ""


def test_claude_code_rejects_oversized_transcript(tmp_path, monkeypatch):
    import memory_garden.integrations.adapters.claude_code as claude_code

    monkeypatch.setattr(claude_code, "_MAX_TRANSCRIPT_BYTES", 10)
    transcript = tmp_path / "transcript.json"
    transcript.write_text(
        json.dumps({"messages": [{"role": "user", "content": "too large"}]}),
        encoding="utf-8",
    )

    assert claude_code._read_transcript_user_message(str(transcript)) == ""


def test_claude_code_normalizes_user_message_length():
    from memory_garden.integrations.adapters.claude_code import (
        _MAX_USER_MESSAGE_CHARS,
        _normalize_user_message,
    )

    text = "x" * (_MAX_USER_MESSAGE_CHARS + 5)

    assert len(_normalize_user_message(text)) == _MAX_USER_MESSAGE_CHARS


def test_shared_provider_loader_reads_config_without_network(tmp_path, monkeypatch):
    import memory_garden.providers as provider_module
    from memory_garden.integrations.adapters._providers import provider_registry_from_env

    class _LoadedLLM:
        is_remote = True

        def __init__(self, *, api_key):
            self.api_key = api_key

    class _LoadedEmbedding:
        is_remote = True

        def __init__(self, **kwargs):
            self.kwargs = kwargs

    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.setattr(provider_module, "DeepSeekLLMProvider", _LoadedLLM)
    monkeypatch.setattr(provider_module, "OpenAICompatibleEmbeddingProvider", _LoadedEmbedding)

    garden_home = tmp_path / "garden"
    garden_home.mkdir()
    (garden_home / "provider_config.json").write_text(
        json.dumps({
            "deepseek_api_key": "local-deepseek-test-key",
            "dashscope_api_key": "local-dashscope-test-key",
        }),
        encoding="utf-8",
    )

    providers = provider_registry_from_env(str(garden_home), autoload=True)

    assert providers is not None
    assert providers.llm.api_key == "local-deepseek-test-key"
    assert providers.embedding.kwargs["api_key"] == "local-dashscope-test-key"
    assert providers.policy.allow_raw_user_text is True


def test_shared_provider_loader_is_disabled_by_default(tmp_path, monkeypatch):
    from memory_garden.integrations.adapters._providers import provider_registry_from_env

    monkeypatch.delenv("MEMORY_GARDEN_ENABLE_PROVIDER_AUTOLOAD", raising=False)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "env-deepseek-test-key")

    garden_home = tmp_path / "garden"
    garden_home.mkdir()

    assert provider_registry_from_env(str(garden_home)) is None


# ── Codex adapter ───────────────────────────────────────────────────


def test_codex_imports():
    from memory_garden.integrations.adapters.codex import CodexSession
    assert CodexSession is not None


def test_codex_build_system_prompt(tmp_path):
    from memory_garden.integrations.adapters.codex import CodexSession

    garden = _make_garden(tmp_path)
    cs = CodexSession(garden=garden)
    prompt = cs.build_system_prompt("You are a helpful assistant.")
    assert "You are a helpful assistant" in prompt
    assert isinstance(prompt, str)
    cs.close()
    garden.close()


def test_codex_uses_llm_brief_writer_when_provider_available(tmp_path):
    from memory_garden.integrations.adapters.codex import CodexSession

    garden = _make_garden(tmp_path)
    garden.core.repository.save_memory_card(
        MemoryCard(
            title="reply style",
            essence="User prefers short answers with English technical terms.",
            fragrance="User prefers short answers with English technical terms.",
            thorns="Do not over-infer.",
            tags=["reply", "style"],
        )
    )
    providers = ProviderRegistry(
        policy=ProviderPolicy(allow_raw_user_text=True),
        llm=_ClaudeBriefLLM(),
    )
    cs = CodexSession(garden=garden, providers=providers)

    result = cs.before("reply style")

    assert result["brief_text"]
    assert "[use]" in result["brief_text"]
    assert "参考记忆" not in result["brief_text"]
    cs.close()
    garden.close()


def test_codex_skips_llm_brief_writer_without_raw_text_opt_in(tmp_path):
    from memory_garden.integrations.adapters.codex import CodexSession

    class _BlockedLLM:
        name = "blocked-llm"
        is_remote = False

        def __init__(self) -> None:
            self.calls = 0

        def complete_text(self, *, system, user, context):
            self.calls += 1
            return TextCompletionResult(text="should not be used", model=self.name)

    garden = _make_garden(tmp_path)
    garden.core.repository.save_memory_card(
        MemoryCard(
            title="reply style",
            essence="User prefers short answers with English technical terms.",
            fragrance="User prefers short answers with English technical terms.",
            thorns="Do not over-infer.",
            tags=["reply", "style"],
        )
    )
    llm = _BlockedLLM()
    providers = ProviderRegistry(
        policy=ProviderPolicy(allow_raw_user_text=False),
        llm=llm,
    )
    cs = CodexSession(garden=garden, providers=providers)

    result = cs.before("reply style")

    assert llm.calls == 0
    assert "should not be used" not in result["brief_text"]
    cs.close()
    garden.close()


def test_codex_full_cycle(tmp_path):
    from memory_garden.integrations.adapters.codex import CodexSession

    garden = _make_garden(tmp_path)
    cs = CodexSession(garden=garden)
    result = cs.before("I prefer dark mode.")
    assert "brief_text" in result
    cs.after("Dark mode applied successfully.")
    fb = cs.close()
    assert fb is not None
    garden.close()


# ── OpenClaw adapter ───────────────────────────────────────────────


def test_openclaw_imports():
    from memory_garden.integrations.adapters.openclaw import OpenClawSession

    assert OpenClawSession is not None


def test_openclaw_cli_before_passes_garden_path_to_provider_loader(tmp_path, monkeypatch, capsys):
    import memory_garden.integrations.adapters._providers as providers_module
    from memory_garden.integrations.adapters import openclaw

    seen_paths: list[str] = []

    def _fake_loader(path: str, *, autoload=None):
        seen_paths.append(path)
        return None

    garden_path = tmp_path / "garden"
    monkeypatch.setattr(providers_module, "provider_registry_from_env", _fake_loader)
    monkeypatch.setenv("MEMORY_GARDEN_PATH", str(garden_path))
    monkeypatch.setenv("OPENCLAW_USER_MESSAGE", "Fix the auth bug")

    openclaw._cmd_hook_before()

    assert seen_paths == [str(garden_path)]
    payload = json.loads(capsys.readouterr().out)
    assert "brief" in payload
    assert "session_id" in payload


def test_openclaw_after_records_turn_when_called_fresh(tmp_path, monkeypatch):
    from memory_garden.integrations.adapters.openclaw import OpenClawSession

    garden = _make_garden(tmp_path)
    session = OpenClawSession(garden=garden)
    seen_messages: list[str] = []

    def _fake_observe(text, metadata):
        seen_messages.append(text)
        return []

    monkeypatch.setattr(garden.core, "observe", _fake_observe)

    session.after("Applied dark mode.", user_message="I prefer dark mode.")

    assert seen_messages == ["I prefer dark mode."]
    session.close()
    garden.close()


def test_codex_system_prompt_cmd(tmp_path):
    from memory_garden.integrations.adapters.codex import codex_system_prompt_cmd
    rc = codex_system_prompt_cmd(str(tmp_path / "garden"))
    assert rc == 0


def test_both_adapters_no_memory_garden_created(tmp_path):
    cwd_mg = os.path.join(os.getcwd(), ".memory_garden")
    existed_before = os.path.exists(cwd_mg)

    from memory_garden.integrations.adapters.claude_code import ClaudeCodeSession
    from memory_garden.integrations.adapters.codex import CodexSession

    g1 = _make_garden(tmp_path)
    cc = ClaudeCodeSession(garden=g1)
    cc.before("test")
    cc.close()
    g1.close()

    g2 = _make_garden(tmp_path)
    cs = CodexSession(garden=g2)
    cs.before("test")
    cs.close()
    g2.close()

    if not existed_before:
        assert not os.path.exists(cwd_mg)
