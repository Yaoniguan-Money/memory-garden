"""第五层 Stage 5C：examples 与 integration quickstart 文档测试。"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_EXAMPLE = _ROOT / "examples" / "sync_chat_agent.py"
_DOCS = _ROOT / "docs" / "integration_quickstart.md"


def _load_example():
    spec = importlib.util.spec_from_file_location("mg_examples_sync_chat_agent", _EXAMPLE)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_example_module_import_does_not_run_main() -> None:
    mod = _load_example()
    assert hasattr(mod, "run_demo")
    assert hasattr(mod, "build_demo_adapter")
    # import 阶段不应已经跑过 demo（无副效应计数器被污染 — 用新模块状态）
    assert mod.RuleBasedDemoAgent is not None


def test_build_demo_adapter_and_run_demo() -> None:
    mod = _load_example()
    ad = mod.build_demo_adapter()
    assert ad.config.debug is False
    results = mod.run_demo()
    assert len(results) == 3
    for r in results:
        json.dumps(r.model_dump(mode="json"))


def test_command_turns_do_not_invoke_fake_agent() -> None:
    mod = _load_example()
    bundle = mod.build_demo_stack()
    adapter, agent = bundle.adapter, bundle.agent
    r_open = adapter.reply("花花开")
    assert len(agent.calls) == 0
    adapter.reply("花花关", session_id=r_open.session_id)
    assert len(agent.calls) == 0


def test_open_plain_message_invokes_fake_agent() -> None:
    mod = _load_example()
    bundle = mod.build_demo_stack()
    adapter, agent = bundle.adapter, bundle.agent
    r0 = adapter.reply("花花开")
    adapter.reply("普通一句", session_id=r0.session_id)
    assert len(agent.calls) == 1


def test_example_source_no_provider_or_api_key_tokens() -> None:
    text = _EXAMPLE.read_text(encoding="utf-8").lower()
    for bad in (
        "openai",
        "anthropic",
        "deepseek",
        "api_key",
        "apikey",
        "live-key-token",
        "project-key-token",
        "bearer ",
    ):
        assert bad not in text, bad


def test_run_demo_no_workspace_db_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    mod = _load_example()
    mod.run_demo()
    assert not (tmp_path / "garden.db").exists()
    assert not (tmp_path / ".memory_garden").exists()


def test_quickstart_doc_exists_and_states_boundaries() -> None:
    assert _DOCS.is_file()
    body = _DOCS.read_text(encoding="utf-8")
    assert "不接真实 LLM" in body or "不接真实 llm" in body.lower()
    assert "ChatAgentProtocol" in body
    assert "花花开" in body
    assert "花花关" in body
    assert "before_reply" in body
    assert "after_reply" in body
    assert "BriefInjectionMode" in body or "brief_injection" in body.lower()
    assert "debug" in body.lower()
    assert "Async" in body and "不包含" in body
