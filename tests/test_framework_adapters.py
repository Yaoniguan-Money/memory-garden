"""Tests for Anthropic, LlamaIndex, FastAPI, and LangGraph adapters."""

import os

from memory_garden.core.models import MemoryCard
from memory_garden.providers import ProviderPolicy, ProviderRegistry, TextCompletionResult
from memory_garden.sdk import MemoryGarden


def _g(tmp_path):
    return MemoryGarden.local(tmp_path / "garden")


def _save_reply_style_memory(garden):
    garden.core.repository.save_memory_card(
        MemoryCard(
            title="reply style",
            essence="User prefers short answers with English technical terms.",
            fragrance="User prefers short answers with English technical terms.",
            thorns="Do not over-infer.",
            tags=["reply", "style"],
        )
    )


# ── Anthropic ───────────────────────────────────────────────────────


def test_anthropic_imports():
    from memory_garden.integrations.adapters.anthropic import GardenAnthropic, GardenAnthropicMessages
    assert GardenAnthropic is not None
    assert GardenAnthropicMessages is not None


def test_anthropic_wraps_client(tmp_path):
    from memory_garden.integrations.adapters.anthropic import GardenAnthropic

    class _MockMessages:
        @staticmethod
        def create(*, messages, model, system="", **kwargs):
            class _Block:
                text = "[mock anthropic reply]"
            class _Resp:
                content = [_Block()]
            return _Resp()

    class _MockClient:
        messages = _MockMessages()

    garden = _g(tmp_path)
    wrapped = GardenAnthropic(client=_MockClient(), garden=garden)
    wrapped.skill.open()
    response = wrapped.messages.create(
        messages=[{"role": "user", "content": "Hello"}],
        model="claude-mock",
        max_tokens=100,
    )
    assert response.content[0].text == "[mock anthropic reply]"
    wrapped.skill.close()
    garden.close()


# ── LlamaIndex ──────────────────────────────────────────────────────


def test_llamaindex_imports():
    from memory_garden.integrations.adapters.llamaindex import GardenLlamaIndexMemory
    assert GardenLlamaIndexMemory is not None


def test_llamaindex_memory_interface(tmp_path):
    from memory_garden.integrations.adapters.llamaindex import GardenLlamaIndexMemory

    garden = _g(tmp_path)
    memory = GardenLlamaIndexMemory(garden=garden)

    messages = memory.get(input="I prefer dark mode.")
    assert isinstance(messages, list)
    assert memory.token_limit == 3000

    class _MockMsg:
        def __init__(self, role, content):
            self.role = role
            self.content = content

    memory.put(_MockMsg("assistant", "Got it!"))
    memory.put(_MockMsg("user", "What did I say?"))

    all_msgs = memory.get_all()
    assert len(all_msgs) == 2

    memory.reset()
    assert len(memory.get_all()) == 0
    garden.close()


# ── FastAPI ─────────────────────────────────────────────────────────


def test_fastapi_imports():
    from memory_garden.integrations.adapters.fastapi import GardenFastAPI
    assert GardenFastAPI is not None


def test_fastapi_before_after_cycle(tmp_path):
    from memory_garden.integrations.adapters.fastapi import GardenFastAPI

    garden = _g(tmp_path)
    gf = GardenFastAPI(garden=garden)

    ctx = gf.before_request(request={"message": "I prefer dark mode."})
    assert "brief" in ctx
    assert "session_id" in ctx
    assert ctx["user_message"] == "I prefer dark mode."

    gf.after_request(ctx, "Dark mode applied!")
    fb = gf.close_session()
    assert fb is not None
    garden.close()


def test_fastapi_open_close(tmp_path):
    from memory_garden.integrations.adapters.fastapi import GardenFastAPI

    garden = _g(tmp_path)
    gf = GardenFastAPI(garden=garden)
    sid = gf.open_session()
    assert sid is not None
    fb = gf.close_session()
    assert fb is not None
    garden.close()


# ── Hermes ──────────────────────────────────────────────────────────


class _HermesBriefLLM:
    name = "hermes-brief-llm"
    is_remote = False

    def complete_text(self, *, system, user, context):
        return TextCompletionResult(
            text="User prefers short answers with English technical terms.",
            model=self.name,
        )


def test_anthropic_uses_llm_brief_writer_when_provider_available(tmp_path):
    from memory_garden.integrations.adapters.anthropic import GardenAnthropic

    class _MockMessages:
        seen_system = ""

        @staticmethod
        def create(*, messages, model, system="", **kwargs):
            _MockMessages.seen_system = system

            class _Block:
                text = "[mock anthropic reply]"

            class _Resp:
                content = [_Block()]

            return _Resp()

    class _MockClient:
        messages = _MockMessages()

    garden = _g(tmp_path)
    _save_reply_style_memory(garden)
    providers = ProviderRegistry(
        policy=ProviderPolicy(allow_raw_user_text=True),
        llm=_HermesBriefLLM(),
    )
    wrapped = GardenAnthropic(client=_MockClient(), garden=garden, providers=providers)
    wrapped.skill.open()

    wrapped.messages.create(
        messages=[{"role": "user", "content": "reply style"}],
        model="claude-mock",
        max_tokens=100,
    )

    assert "User prefers short answers with English technical terms." in _MockMessages.seen_system
    wrapped.skill.close()
    garden.close()


def test_fastapi_uses_llm_brief_writer_when_provider_available(tmp_path):
    from memory_garden.integrations.adapters.fastapi import GardenFastAPI

    garden = _g(tmp_path)
    _save_reply_style_memory(garden)
    providers = ProviderRegistry(
        policy=ProviderPolicy(allow_raw_user_text=True),
        llm=_HermesBriefLLM(),
    )
    api = GardenFastAPI(garden=garden, providers=providers)

    ctx = api.before_request(user_message="reply style")

    assert "[use] User prefers short answers with English technical terms." in ctx["brief"]
    api.close_session()
    garden.close()


def test_langchain_uses_llm_brief_writer_when_provider_available(tmp_path):
    from memory_garden.integrations.adapters.langchain import GardenLangChainMemory

    garden = _g(tmp_path)
    _save_reply_style_memory(garden)
    providers = ProviderRegistry(
        policy=ProviderPolicy(allow_raw_user_text=True),
        llm=_HermesBriefLLM(),
    )
    memory = GardenLangChainMemory(garden=garden, providers=providers)

    variables = memory.load_memory_variables({"input": "reply style"})

    assert "[use] User prefers short answers with English technical terms." in variables["garden_context"]
    memory.clear()
    garden.close()


def test_llamaindex_uses_llm_brief_writer_when_provider_available(tmp_path):
    from memory_garden.integrations.adapters.llamaindex import GardenLlamaIndexMemory

    garden = _g(tmp_path)
    _save_reply_style_memory(garden)
    providers = ProviderRegistry(
        policy=ProviderPolicy(allow_raw_user_text=True),
        llm=_HermesBriefLLM(),
    )
    memory = GardenLlamaIndexMemory(garden=garden, providers=providers)

    messages = memory.get(input="reply style")

    assert "User prefers short answers with English technical terms." in messages[0].content
    memory.reset()
    garden.close()


def test_langgraph_uses_llm_brief_writer_when_provider_available(tmp_path):
    from memory_garden.integrations.adapters.langgraph import GardenLangGraphMemory

    garden = _g(tmp_path)
    _save_reply_style_memory(garden)
    providers = ProviderRegistry(
        policy=ProviderPolicy(allow_raw_user_text=True),
        llm=_HermesBriefLLM(),
    )
    memory = GardenLangGraphMemory(garden=garden, providers=providers)
    state = {"messages": [type("Msg", (), {"role": "user", "content": "reply style"})()]}

    result = memory.inject(state)

    assert "[use] User prefers short answers with English technical terms." in result["garden_context"]
    memory.close()
    garden.close()


def test_hermes_before_reply_uses_llm_brief_writer_when_provider_available(tmp_path):
    from memory_garden.integrations.adapters.hermes import HermesGardenSession

    garden = _g(tmp_path)
    _save_reply_style_memory(garden)
    providers = ProviderRegistry(
        policy=ProviderPolicy(allow_raw_user_text=True),
        llm=_HermesBriefLLM(),
    )
    session = HermesGardenSession(garden=garden, providers=providers)

    ctx = session.before_reply("reply style")

    assert "[use] User prefers short answers with English technical terms." in ctx.brief_text
    assert ctx.brief_dict["source_memory_ids"]
    session.after_reply("reply style", "OK")
    session.close()
    garden.close()


def test_hermes_error_turn_does_not_raise(tmp_path):
    from memory_garden.integrations.adapters.hermes import HermesGardenSession

    garden = _g(tmp_path)
    session = HermesGardenSession(garden=garden)

    session.after_reply(user_message="hello", assistant_reply="", error="failed")

    session.close()
    garden.close()


# ── LangGraph ───────────────────────────────────────────────────────


def test_langgraph_imports():
    from memory_garden.integrations.adapters.langgraph import (
        garden_memory_node,
        GardenLangGraphMemory,
    )
    assert garden_memory_node is not None
    assert GardenLangGraphMemory is not None


def test_langgraph_node_injects_context(tmp_path):
    from memory_garden.integrations.adapters.langgraph import garden_memory_node

    garden = _g(tmp_path)
    state = {"messages": [type("Msg", (), {"role": "user", "content": "I prefer dark mode."})()]}
    result = garden_memory_node(state, garden=garden)
    assert "garden_context" in result
    assert "garden_session_id" in result
    garden.close()


def test_langgraph_memory_full_cycle(tmp_path):
    from memory_garden.integrations.adapters.langgraph import GardenLangGraphMemory

    garden = _g(tmp_path)
    memory = GardenLangGraphMemory(garden=garden)
    state = {"messages": [type("Msg", (), {"role": "user", "content": "Hello"})()]}
    result = memory.inject(state)
    assert "garden_context" in result

    memory.observe({"output": "Hi there!", "messages": state["messages"]})
    fb = memory.close()
    assert fb is not None
    garden.close()


# ── No side effects ────────────────────────────────────────────────


def test_all_adapters_no_memory_garden_created(tmp_path):
    cwd_mg = os.path.join(os.getcwd(), ".memory_garden")
    existed_before = os.path.exists(cwd_mg)

    from memory_garden.integrations.adapters.anthropic import GardenAnthropic
    from memory_garden.integrations.adapters.fastapi import GardenFastAPI
    from memory_garden.integrations.adapters.llamaindex import GardenLlamaIndexMemory
    from memory_garden.integrations.adapters.langgraph import GardenLangGraphMemory

    for _ in range(2):
        path = tmp_path / f"garden_{_}"
        g = _g(path)
        GardenAnthropic(client=type("C", (), {"messages": type("M", (), {"create": lambda *a, **kw: type("R", (), {"content": [type("B", (), {"text": "ok"})()]})()})()})(), garden=g)
        GardenLlamaIndexMemory(garden=g)
        GardenFastAPI(garden=g)
        GardenLangGraphMemory(garden=g)
        g.close()

    if not existed_before:
        assert not os.path.exists(cwd_mg)
