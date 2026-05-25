"""Garden Skill Demo — Memory Garden as a drop-in memory layer.

This example demonstrates all three integration patterns:

1. **Universal GardenSkill** — works with any LLM, any framework
2. **OpenAI adapter** — wraps ``openai.OpenAI().chat.completions.create()``
3. **LangChain adapter** — implements ``BaseMemory`` for LangChain chains

Usage::

    python examples/garden_skill_demo.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running from the repo root
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from memory_garden.sdk import MemoryGarden


def demo_universal_skill():
    """Pattern 1: Framework-agnostic GardenSkill — works everywhere."""
    print("=" * 60)
    print("  Pattern 1: Universal GardenSkill")
    print("=" * 60)

    garden = MemoryGarden.local("./.memory_garden_demo")
    skill = garden.as_skill()

    # Open a session
    skill.open()
    print("  Session opened")

    # Your LLM function — could be anything
    def my_llm(context, user_message):
        brief = context.brief_text or "(no brief)"
        print(f"  [Brief] {brief[:100]}...")
        return f"[LLM reply to: {user_message[:40]}...]"

    # Chat loop
    for msg in [
        "I prefer dark mode interfaces.",
        "I work best in the morning, please remember that.",
        "What did I tell you about my preferences?",
    ]:
        reply, ctx = skill.chat(msg, my_llm)
        print(f"  [User] {msg}")
        print(f"  [Reply] {reply}")
        print()

    # Close
    fb = skill.close()
    if fb:
        print(f"  [Feedback] {fb.summary}")
    print(f"  [Health] {skill.health.status.value}")
    garden.close()
    print()


def demo_openai_pattern():
    """Pattern 2: OpenAI wrapper — drop-in replacement.

    This demonstrates the API shape.  With a real ``openai`` import,
    the same code works with a real API key.
    """
    print("=" * 60)
    print("  Pattern 2: OpenAI Adapter (API shape demo)")
    print("=" * 60)

    garden = MemoryGarden.local("./.memory_garden_demo2")
    skill = garden.as_skill()

    # When you have openai installed, this becomes:
    #   import openai
    #   client = openai.OpenAI()
    #   from memory_garden.integrations.adapters.openai import GardenOpenAI
    #   wrapped = GardenOpenAI(client=client, garden=garden)
    #   wrapped.skill.open()
    #   response = wrapped.chat.create(
    #       messages=[{"role": "user", "content": "I prefer dark mode."}],
    #       model="gpt-4",
    #   )

    skill.open()
    ctx = skill.before("I prefer dark mode.",
                       messages=[{"role": "user", "content": "I prefer dark mode."}])
    print("  Original messages: 1")
    print(f"  Modified messages: {len(ctx.messages)} (brief injected)")
    if ctx.brief_text:
        print(f"  [Brief] {ctx.brief_text[:80]}...")
    skill.close()
    garden.close()
    print()


def demo_langchain_pattern():
    """Pattern 3: LangChain memory — BaseMemory interface."""
    print("=" * 60)
    print("  Pattern 3: LangChain Adapter (BaseMemory demo)")
    print("=" * 60)

    garden = MemoryGarden.local("./.memory_garden_demo3")

    from memory_garden.integrations.adapters.langchain import GardenLangChainMemory
    memory = GardenLangChainMemory(garden=garden)

    # Standard LangChain memory interface
    vars_ = memory.load_memory_variables({"input": "I prefer dark mode."})
    print(f"  Memory variables: {list(vars_.keys())}")

    memory.save_context(
        {"input": "I prefer dark mode."},
        {"output": "Got it! I'll remember that."},
    )
    print("  Context saved")

    vars2 = memory.load_memory_variables({"input": "What are my preferences?"})
    print(f"  Context on next turn: {vars2['garden_context'][:80]}...")

    memory.clear()
    garden.close()
    print()


def demo_skill_composition():
    """Pattern 4: Skill + Covenant + Mock Providers — the full picture."""
    print("=" * 60)
    print("  Pattern 4: Full Composition (Skill + Covenant + Providers)")
    print("=" * 60)

    from memory_garden.covenant.defaults import default_garden_covenant
    from memory_garden.integrations.mock_providers import (
        MockLLMProvider,
        MockEmbeddingProvider,
        MockRelevanceProvider,
    )
    from memory_garden.integrations.providers import ProviderRegistry  # 旧版，已废弃

    # Create garden with Covenant enforcement
    garden = MemoryGarden.local(
        "./.memory_garden_demo4",
        covenant=default_garden_covenant(),
    )
    skill = garden.as_skill()

    # ★ 生产环境推荐用法（一行接入）：
    # export DEEPSEEK_API_KEY="..."
    # skill.with_deepseek()           # 或 skill.with_openai()
    #
    # 以下使用旧版 Mock Provider 演示完整拼装：

    providers = ProviderRegistry(
        llm=MockLLMProvider(),
        embedding=MockEmbeddingProvider(),
        relevance=MockRelevanceProvider(),
    )

    # Verify Covenant enforcement is active
    assert garden.enforcer is not None
    print(f"  Enforcer: active ({len(dir(garden.enforcer))} checkpoint methods)")
    print(f"  Providers: LLM={providers.has_llm}, Embedding={providers.has_embedding}, Relevance={providers.has_relevance}")

    skill.open()
    skill.before("I prefer dark mode.")
    skill.close()

    health = skill.health
    print(f"  Health: {health.status.value}")
    garden.close()
    print()


if __name__ == "__main__":
    demo_universal_skill()
    demo_openai_pattern()
    demo_langchain_pattern()
    demo_skill_composition()
    print("All demos complete.")
