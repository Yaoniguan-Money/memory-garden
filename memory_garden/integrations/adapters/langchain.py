"""LangChain memory adapter — use Memory Garden as a LangChain `BaseMemory`.

Usage::

    from memory_garden.sdk import MemoryGarden
    from memory_garden.integrations.adapters.langchain import GardenLangChainMemory

    garden = MemoryGarden.local("./my_garden")
    memory = GardenLangChainMemory(garden=garden)

    # Use in a chain
    from langchain.chains import ConversationChain
    from langchain.llms import YourLLM

    chain = ConversationChain(llm=YourLLM(), memory=memory)
    chain.predict(input="I prefer dark mode.")

This module has **zero hard dependency** on LangChain.  It uses duck-typing
to implement the ``BaseMemory`` interface.  If LangChain is not installed,
the class still imports but won't be usable with LangChain chains.
"""

from __future__ import annotations

from typing import Any


class GardenLangChainMemory:
    """Duck-typed LangChain ``BaseMemory`` — no import-time langchain dependency.

    Implements the standard LangChain memory interface:
    ``load_memory_variables``, ``save_context``, ``clear``, ``memory_variables``.
    """

    def __init__(
        self,
        *,
        garden: Any,
        input_key: str = "input",
        output_key: str = "output",
        providers: Any | None = None,
    ) -> None:
        self._garden = garden
        from memory_garden.integrations.adapters._cognitive_brief import resolve_provider_registry
        from memory_garden.skill import GardenSkill

        self._skill: GardenSkill = garden.as_skill()
        self._providers = resolve_provider_registry(garden, providers)
        if self._providers is not None:
            self._skill.configure_providers(self._providers)
        self._input_key = input_key
        self._output_key = output_key
        self._is_open = False

    @property
    def memory_variables(self) -> list[str]:
        return ["garden_context"]

    @property
    def skill(self) -> Any:
        return self._skill

    @property
    def garden(self) -> Any:
        return self._garden

    def load_memory_variables(self, inputs: dict[str, Any]) -> dict[str, str]:
        """Called by LangChain before every chain step.

        Extracts the user input from *inputs*, runs ``skill.before()``,
        and returns the context as a memory variable.
        """
        if not self._is_open:
            self._skill.open()
            self._is_open = True

        user_text = str(inputs.get(self._input_key, ""))
        ctx = self._before_context(user_text)
        return {"garden_context": ctx.brief_text or ""}

    def _before_context(self, user_text: str) -> Any:
        from memory_garden.integrations.adapters._cognitive_brief import build_cognitive_skill_context

        ctx = build_cognitive_skill_context(
            garden=self._garden,
            skill=self._skill,
            providers=self._providers,
            user_message=user_text,
            metadata={"adapter": "langchain", "source_role": "user"},
            max_candidates=5,
        )
        if ctx is not None:
            return ctx
        return self._skill.before(user_text)

    def save_context(self, inputs: dict[str, Any], outputs: dict[str, Any]) -> None:
        """Called by LangChain after every chain step.

        Observes the assistant reply in the garden.
        """
        user_text = str(inputs.get(self._input_key, ""))
        reply = str(outputs.get(self._output_key, next(iter(outputs.values()), "")))
        self._skill.after(user_text, reply)

    def clear(self) -> None:
        """Close the garden session."""
        if self._is_open:
            self._skill.close()
            self._is_open = False


class GardenLangChainRunnable:
    """Lightweight LangChain ``RunnableLambda``-style integration.

    Usage with LCEL::

        from langchain_core.runnables import RunnableLambda

        garden_memory = GardenLangChainRunnable(garden=garden)
        chain = garden_memory.as_runnable() | prompt | llm | output_parser
    """

    def __init__(self, *, garden: Any, providers: Any | None = None) -> None:
        self._garden = garden
        from memory_garden.integrations.adapters._cognitive_brief import resolve_provider_registry
        from memory_garden.skill import GardenSkill

        self._skill: GardenSkill = garden.as_skill()
        self._providers = resolve_provider_registry(garden, providers)
        if self._providers is not None:
            self._skill.configure_providers(self._providers)

    @property
    def skill(self) -> Any:
        return self._skill

    def as_runnable(self) -> Any:
        """Return a RunnableLambda that injects garden context.

        Requires ``langchain_core`` to be installed.
        """
        try:
            from langchain_core.runnables import RunnableLambda  # type: ignore[import-not-found]
        except ImportError:
            raise ImportError(
                "langchain_core is required for GardenLangChainRunnable.as_runnable(). "
                "Install it with: pip install langchain-core"
            )

        skill = self._skill
        garden = self._garden
        providers = self._providers

        def _inject(inputs: dict) -> dict:
            user_text = str(inputs.get("input", ""))
            if not skill.is_open:
                skill.open()
            from memory_garden.integrations.adapters._cognitive_brief import build_cognitive_skill_context

            ctx = build_cognitive_skill_context(
                garden=garden,
                skill=skill,
                providers=providers,
                user_message=user_text,
                metadata={"adapter": "langchain_runnable", "source_role": "user"},
                max_candidates=5,
            )
            if ctx is None:
                ctx = skill.before(user_text)
            if "garden_context" not in inputs:
                inputs["garden_context"] = ctx.brief_text or ""
            return inputs

        return RunnableLambda(_inject)
