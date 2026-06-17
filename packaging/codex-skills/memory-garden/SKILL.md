---
name: memory-garden
description: Product-grade local-first agent memory with Memory Garden. Use when Codex needs to create reviewable memory proposals, persist approved memories, retrieve relevant local memories, prepare a source-id-preserving brief before an LLM call, manage memory versions and relations, hard-forget memories with proof, audit the local garden, or check garden health. External LLM, embedding, reranker, and secret providers are caller-owned and opt-in only.
---

# Memory Garden

Use this skill as a local, auditable memory layer. It wraps the Python package
`memory_garden` through the stable `MemoryGarden` and `GardenSkill` APIs.

## Operating Rules

- Keep operations local by default. Do not call external model providers,
  embedding services, vector stores, or network APIs unless the host application
  supplies a `ProviderRegistry` and policy explicitly permits that provider.
- Prefer the product proposal workflow for durable writes. Use
  `propose_memory()` plus `approve_memory_proposal()` when human review is
  expected; use `remember_memory(..., mode="trusted")` only when the host policy
  permits safe auto-approval.
- Never store secrets, credentials, legal identifiers, medical details, or other
  sensitive personal data unless the user explicitly asks and the host policy
  allows it.
- Use `forget(..., dry_run=True)` before destructive forget operations unless
  the user already supplied an exact memory id and clearly requested deletion.
- Do not expose full garden dumps to a model. Return compact summaries, ids,
  counts, and short snippets. Use `audit()` with bounded limits.
- Reuse an existing `skill` object in the current session when one exists.
  Create a new garden only when no garden has been initialized for the task.

## Initialize

Use the installed package when available. Do not insert a hard-coded repository
path into `sys.path`.

```python
from pathlib import Path
from memory_garden.sdk import MemoryGarden

garden_home = Path.home() / ".memory-garden"
garden = MemoryGarden.local(garden_home)
skill = garden.as_skill()
opened = skill.open_session()
```

If the user or host application provides a garden home, use that path instead
of the default. For temporary validation, use a temporary directory and close
the garden afterward.

## Common Tasks

```python
# Legacy explicit write, mediated by rule Court.
result = skill.remember("User prefers dark mode for interface examples.")

# Non-mutating preview of what the Court would decide.
preview = skill.remember("User prefers concise answers.", mode="preview")

# Rule-only local retrieval.
harvest = skill.harvest("dark mode", limit=5)

# Safe destructive flow.
plan = skill.forget("dark mode", reason="user request", dry_run=True)
deleted = skill.forget("dark mode", reason="user request", cascade=True)

# Compact observability.
audit = skill.audit(limit=25)
health = skill.health
summary = skill.summary
```

Product-grade workflows expose proposal review, memory strategy profiles,
versioning, relations, retrieval explanations, and forget proof:

```python
# Reviewable extraction.
proposals = skill.propose_memory("remember: prefer compact release notes")
card = skill.approve_memory_proposal(proposals[0].id)

# Product write policy: manual, trusted, or auto.
result = skill.remember_memory(
    "remember: prefer dark mode dashboards",
    mode="trusted",
)

# Management and inspection.
memories = skill.list_memories()
inspection = skill.inspect_memory(card.id)
updated = skill.update_memory(card.id, MemoryPatch(tags=["release", "style"]))

# Strategy-aware retrieval and model context.
strategy = skill.get_memory_strategy(card.id)
applicability = skill.assess_memory_applicability(
    card.id,
    "release note style",
    context={"project_id": "atlas", "task_type": "writing"},
)
retrieval = skill.retrieve_memories(
    "release note style",
    limit=5,
    context={"project_id": "atlas", "task_type": "writing"},
)
brief = skill.build_memory_brief(
    "release note style",
    limit=5,
    context={"project_id": "atlas", "task_type": "writing"},
)

# Strategy maintenance.
skill.reinforce_memory_strategy(card.id, reason="user_confirmed_still_true")
decay_plans = skill.decay_memory_strategies()
abstraction_plans = skill.plan_memory_abstractions()

# Auditable destructive flow.
plan = skill.plan_memory_forget(memory_id=card.id)
executed, proof = skill.execute_memory_forget(plan.id)
```

If the application owns external providers, register them explicitly:

```python
from memory_garden.providers import ProviderRegistry

skill.configure_providers(
    ProviderRegistry(
        llm=my_llm_provider,
        embedding=my_embedding_provider,
        reranker=my_reranker_provider,
        secrets=my_secret_provider,
    )
)
```

For framework-style chat integration, call `before()` immediately before the
LLM call and `after()` immediately after the assistant reply:

```python
ctx = skill.before(
    user_message,
    messages=[{"role": "user", "content": user_message}],
)
messages_for_model = ctx.messages
skill.after(user_message, assistant_reply)
```

## Output Expectations

- For `remember()`, report `ok`, `verdicts`, `memory_ids`, and any skipped
  reasons. Do not claim a memory was saved unless `memory_ids` is non-empty or
  the returned metadata proves the write.
- For product proposals, report proposal ids, status, whether confirmation is
  required, duplicate/conflict ids, and created memory ids after approval.
- For product retrieval, report `hits`, `score`, `why_used`, `provider_used`,
  `applicability_score`, `applicability_reasons`, and `source_memory_ids` from
  the brief when context will be injected.
- For strategy profiles, report layer, scope, maturity, strength, evidence
  count, use count, and any evolution or conflict records.
- For product forget, report the plan id, affected entities, execution status,
  and `proof.proven`.
- For `harvest()`, report the brief and `source_memory_ids`. Treat an empty
  result as "no matching local memory", not as evidence that the user has no
  preference.
- For `forget()`, report whether it was a dry run, the resolved `memory_ids`,
  and any issues from metadata. Do not hide partial or failed status.
- For `audit()`, keep limits small and avoid dumping complete payloads.

## References

Read only the reference needed for the task:

- `references/api.md`: stable methods, return models, and code patterns.
- `references/privacy-and-safety.md`: write gates, redaction, and forget policy.
- `references/storage-and-health.md`: local files, SQLite, FTS, and health checks.
- `references/troubleshooting.md`: common failures and recovery steps.

## Validation

Run the deterministic smoke check after changing this skill or the Skill API:

```bash
python scripts/memory_garden_skill_smoke.py
```

For repository validation, also run:

```bash
python -m pytest tests/test_skill_contract.py tests/test_product_skill_api.py tests/test_product_memory_system.py -q
```
