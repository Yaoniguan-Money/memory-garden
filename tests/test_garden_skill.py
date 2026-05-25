"""Tests for universal GardenSkill and framework adapters."""

import os

from memory_garden.core.models import MemoryCard
from memory_garden.providers import ProviderPolicy, ProviderRegistry, TextCompletionResult
from memory_garden.sdk import MemoryGarden
from memory_garden.skill import GardenSkill, SkillContext


def _make_skill(tmp_path) -> GardenSkill:
    garden = MemoryGarden.local(tmp_path / "garden")
    return garden.as_skill()


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


class _AdapterBriefLLM:
    name = "adapter-brief-llm"
    is_remote = False

    def complete_text(self, *, system, user, context):
        return TextCompletionResult(
            text="User prefers short answers with English technical terms.",
            model=self.name,
        )


# ── GardenSkill core ────────────────────────────────────────────────


def test_skill_open_returns_session_id(tmp_path):
    skill = _make_skill(tmp_path)
    sid = skill.open()
    assert sid is not None
    assert skill.is_open
    skill.close()


def test_skill_before_returns_context(tmp_path):
    skill = _make_skill(tmp_path)
    skill.open()
    ctx = skill.before("I prefer dark mode.")
    assert isinstance(ctx, SkillContext)
    assert ctx.session_id is not None
    skill.close()


def test_skill_before_injects_into_messages(tmp_path):
    skill = _make_skill(tmp_path)
    skill.open()
    ctx = skill.before("I prefer dark mode.",
                       messages=[{"role": "user", "content": "I prefer dark mode."}])
    assert len(ctx.messages) >= 1
    skill.close()


def test_skill_chat_full_cycle(tmp_path):
    skill = _make_skill(tmp_path)
    skill.open()

    def fake_llm(ctx, msg):
        return f"[LLM reply to: {msg[:30]}]"

    reply, ctx = skill.chat("I prefer dark mode.", fake_llm)
    assert reply is not None
    assert isinstance(ctx, SkillContext)

    reply2, ctx2 = skill.chat("I work best in the morning.", fake_llm)
    assert reply2 is not None

    fb = skill.close()
    assert fb is not None


def test_skill_auto_opens_on_before(tmp_path):
    skill = _make_skill(tmp_path)
    # Don't call open() — before() should auto-open
    skill.before("hello")
    assert skill.is_open
    skill.close()


def test_skill_context_to_system_prefix(tmp_path):
    skill = _make_skill(tmp_path)
    skill.open()
    ctx = skill.before("I prefer dark mode.")
    prefix = ctx.to_system_prefix()
    assert isinstance(prefix, str)

    sys_msg = ctx.to_openai_system_message()
    if sys_msg:
        assert sys_msg["role"] == "system"

    skill.close()


def test_skill_no_memory_garden_created(tmp_path):
    cwd_mg = os.path.join(os.getcwd(), ".memory_garden")
    existed_before = os.path.exists(cwd_mg)

    skill = _make_skill(tmp_path)
    skill.open()
    skill.before("test")
    skill.close()

    if not existed_before:
        assert not os.path.exists(cwd_mg)


def test_skill_health_and_summary(tmp_path):
    skill = _make_skill(tmp_path)
    skill.open()
    skill.before("test")
    assert skill.health is not None
    assert skill.summary is not None
    skill.close()


def test_skill_as_skill_method(tmp_path):
    garden = MemoryGarden.local(tmp_path / "garden")
    skill = garden.as_skill()
    assert isinstance(skill, GardenSkill)
    assert skill.garden is garden


# ── OpenAI adapter ──────────────────────────────────────────────────


def test_openai_adapter_imports():
    from memory_garden.integrations.adapters.openai import GardenOpenAI, GardenChatCompletions
    assert GardenOpenAI is not None
    assert GardenChatCompletions is not None


def test_openai_adapter_wraps_client(tmp_path):
    from memory_garden.integrations.adapters.openai import GardenOpenAI

    # Minimal mock client
    class _MockChat:
        class completions:
            @staticmethod
            def create(*, messages, model, **kwargs):
                class _Choice:
                    class _Msg:
                        content = "[mock reply]"
                    message = _Msg()
                class _Resp:
                    choices = [_Choice()]
                return _Resp()

    class _MockClient:
        chat = _MockChat()

    garden = MemoryGarden.local(tmp_path / "garden")
    wrapped = GardenOpenAI(client=_MockClient(), garden=garden)
    wrapped.skill.open()
    response = wrapped.chat.create(
        messages=[{"role": "user", "content": "Hello"}],
        model="mock-model",
    )
    assert response.choices[0].message.content == "[mock reply]"
    wrapped.skill.close()


def test_openai_adapter_uses_llm_brief_writer_when_provider_available(tmp_path):
    from memory_garden.integrations.adapters.openai import GardenOpenAI

    class _MockChat:
        class completions:
            seen_messages = []

            @staticmethod
            def create(*, messages, model, **kwargs):
                _MockChat.completions.seen_messages = messages

                class _Choice:
                    class _Msg:
                        content = "[mock reply]"
                    message = _Msg()

                class _Resp:
                    choices = [_Choice()]

                return _Resp()

    class _MockClient:
        chat = _MockChat()

    garden = MemoryGarden.local(tmp_path / "garden")
    _save_reply_style_memory(garden)
    providers = ProviderRegistry(
        policy=ProviderPolicy(allow_raw_user_text=True),
        llm=_AdapterBriefLLM(),
    )
    wrapped = GardenOpenAI(client=_MockClient(), garden=garden, providers=providers)
    wrapped.skill.open()

    wrapped.chat.create(
        messages=[{"role": "user", "content": "reply style"}],
        model="mock-model",
    )

    assert any(
        "User prefers short answers with English technical terms." in str(message.get("content", ""))
        for message in _MockChat.completions.seen_messages
    )
    wrapped.skill.close()


# ── LangChain adapter ───────────────────────────────────────────────


def test_langchain_memory_interface(tmp_path):
    from memory_garden.integrations.adapters.langchain import GardenLangChainMemory

    garden = MemoryGarden.local(tmp_path / "garden")
    memory = GardenLangChainMemory(garden=garden)

    # Standard BaseMemory interface
    assert memory.memory_variables == ["garden_context"]

    vars_ = memory.load_memory_variables({"input": "I prefer dark mode."})
    assert "garden_context" in vars_

    memory.save_context({"input": "I prefer dark mode."}, {"output": "Got it!"})
    memory.clear()


def test_langchain_runnable_imports():
    from memory_garden.integrations.adapters.langchain import GardenLangChainRunnable
    assert GardenLangChainRunnable is not None
