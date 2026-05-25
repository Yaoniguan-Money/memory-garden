"""LLM-backed Garden brief writer for the cognition harvest path."""

from __future__ import annotations

from typing import Any

from memory_garden.cognition.models import GardenBriefDraft, HarvestCandidate
from memory_garden.providers import ProviderCallContext
from memory_garden.providers.errors import ProviderPolicyError

_MAX_MEMORY_CHARS = 800


class LLMBriefWriter:
    """Write a short natural-language brief from selected memory candidates."""

    def __init__(self, llm: Any, *, policy: Any | None = None, garden_home: str = "") -> None:
        self._llm = llm
        self._policy = policy
        self._garden_home = garden_home
        self.name = "llm-brief-writer"

    def write_brief(
        self,
        query: str,
        selected_memories: list[HarvestCandidate],
        policy: Any | None = None,
    ) -> GardenBriefDraft:
        source_ids = [m.memory_id for m in selected_memories]
        if not selected_memories:
            return GardenBriefDraft(
                intent=f"Hybrid brief for: {(query or '').strip()[:120]}",
                use="No relevant local memory matched this query.",
                avoid="Do not invent memories or infer beyond the listed source ids.",
                style="Keep the response concise and neutral.",
                safety="Use only traceable local memory.",
                nudge="Ignore this brief if it is not relevant to the current task.",
                source_memory_ids=[],
                token_estimate=32,
            )

        context_lines = []
        for idx, memory in enumerate(selected_memories, start=1):
            body = (memory.text or "").strip().replace("\n", " ")
            if len(body) > _MAX_MEMORY_CHARS:
                body = body[: _MAX_MEMORY_CHARS - 3] + "..."
            tags = ", ".join(memory.tags[:8])
            tag_text = f" tags=[{tags}]" if tags else ""
            context_lines.append(f"{idx}. id={memory.memory_id}{tag_text}: {body}")

        system = (
            "You write Memory Garden briefs. Summarize only the listed memories. "
            "Return one concise Chinese sentence for the [use] field. "
            "Do not include UUIDs, bullets, citations, or unsupported claims."
        )
        user = (
            f"Current query:\n{(query or '').strip()[:1000]}\n\n"
            "Selected traceable memories:\n"
            + "\n".join(context_lines)
            + "\n\nWrite one natural-language summary sentence."
        )
        context = ProviderCallContext(
            purpose="memory_brief_writing",
            provider_kind="llm",
            garden_home=self._garden_home,
            allow_remote=bool(getattr(self._llm, "is_remote", False)),
            metadata={"writer": self.name, "source_memory_ids": list(source_ids)},
        )
        if self._policy is not None:
            from memory_garden.product.policy import MemoryPolicy

            MemoryPolicy(provider_policy=self._policy).assert_provider_call_allowed(context, user)
        elif context.allow_remote:
            raise ProviderPolicyError("Remote LLM brief writer requires an explicit ProviderPolicy opt-in")
        result = self._llm.complete_text(system=system, user=user, context=context)
        summary = str(getattr(result, "text", result) or "").strip()
        summary = " ".join(summary.split())
        if not summary:
            summary = "Local memories are relevant, but no natural-language summary was produced."

        return GardenBriefDraft(
            intent=f"Hybrid LLM brief for: {(query or '').strip()[:120]}",
            use=summary,
            avoid="Do not invent memories or infer beyond the listed source ids.",
            style="Keep the response concise and neutral.",
            safety="Use only traceable local memory.",
            nudge="Ignore this brief if it is not relevant to the current task.",
            source_memory_ids=source_ids,
            token_estimate=max(32, len(summary) // 4 + 24),
        )


__all__ = ["LLMBriefWriter"]
