# Memory Garden Agent Instructions

Memory Garden is a local-first, auditable memory layer for AI agents.

## Project Context

- Version target: v1.4.0
- Runtime dependencies: Pydantic and PyYAML
- Test baseline: the full test suite must pass before release
- Default behavior: rules-only and no network calls

## Core Architecture

- `memory_garden/core/` - Garden lifecycle: Seed, Court, Growth, Dream, Harvest, Brief
- `memory_garden/covenant/` - Policy and trust layer
- `memory_garden/harvest/` - Local retrieval and source-preserving brief pipeline
- `memory_garden/cognition/` - Optional LLM enhancement for Harvest-time ranking and brief writing
- `memory_garden/product/` - Product-grade proposals, review, retrieval, versioning, and hard forget proof
- `memory_garden/integrations/` - Provider and framework adapters

## Constraints

1. Default rules-only behavior must remain unchanged.
2. Unit tests must not make real LLM or embedding calls.
3. LLM output must pass Pydantic validation.
4. LLM output must carry traceable `source_ids`, `memory_ids`, or `seed_ids`.
5. Non-traceable content cannot enter long-term memory.
6. Do not modify Dream, Court, or Soil behavior for Harvest-only work.
7. Use deterministic fake providers in tests.
8. Run the full test suite after behavior changes.
9. Do not commit `.memory_garden/`, SQLite databases, state files, provider configs, `.env` files, or API keys.
