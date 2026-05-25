# Explanation

Design rationale and architectural decisions behind Memory Garden.

## Why Memory Garden Exists

Most AI agent "memory" is a thin wrapper around a vector database: embed user messages, retrieve similar ones, prepend to the prompt. This works for simple cases but creates problems:

- **No lifecycle**: Everything remembered forever, or forgotten by truncation. No concept of "maybe this shouldn't be a memory."
- **No audit**: Which memories came from which messages? Why was something remembered or forgotten? No trace.
- **No safety boundaries**: Nothing prevents sensitive content from being retrieved and sent to a model.
- **Vendor lock-in**: Tied to a specific embedding model, vector DB, or cloud provider.

Memory Garden takes a different approach: memory as a structured lifecycle with explicit judgment, deterministic harvesting, and auditable traces.

## Design Decisions

- [Why a Garden Metaphor?](garden_metaphor.md)
- [Why Rule-Based, Not LLM-Based?](rule_based.md)
- [Why Local-First?](local_first.md)
- [Why No Vector DB?](no_vector_db.md)
- [Why Pydantic Models?](pydantic_models.md)
- [Why SQLite?](sqlite.md)
- [Why 花花开/花花关?](flower_commands.md)
- [Why Nine Layers?](nine_layers.md)
- [Why a Covenant Layer?](covenant.md)

## Constraints

- [Limitations](limitations.md) — what Memory Garden cannot do
- [Related Work](related_work.md) — how it compares to other approaches
