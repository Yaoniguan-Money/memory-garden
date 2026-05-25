# Troubleshooting

## Import Fails

If `from memory_garden.sdk import MemoryGarden` fails:

- In a repository checkout, run commands from the repository root.
- For installed use, install the package into the active Python environment.
- Do not hard-code another user's source path into `sys.path`.

## No Memories Returned

Check:

- `remember()` returned `ok=True`.
- `memory_ids` is non-empty.
- The query shares words or tags with the stored memory.
- The memory was not forgotten or greenhoused.
- Product memories may still be pending proposals. Check
  `skill.memory_inbox(status="pending")` or `memory-garden inbox`.
- Archived memories are excluded from active retrieval. Use
  `list_memories(MemoryListFilter(include_archived=True))` when auditing.
- Strategy applicability may block the memory. Check
  `skill.assess_memory_applicability(memory_id, query, context=...)` or
  `memory-garden applicability MEMORY_ID "query"`.
- Project, workspace, identity, or session scope may not match the current
  context.

An empty harvest result means "no relevant local memory matched", not "the user
has no preferences".

## Forget Cannot Find a Memory

Prefer exact ids:

```python
skill.forget("ignored", memory_id=memory_id, dry_run=True)
```

If only text is available, use a specific substring from the memory title,
essence, fragrance, thorns, or tags.

For product forget, prefer:

```python
plan = skill.plan_memory_forget(memory_id=memory_id)
executed, proof = skill.execute_memory_forget(plan.id)
```

If `proof.proven` is false, inspect `proof.checks` before claiming deletion.

## Provider Blocked

Remote providers are blocked by default. If the host application intentionally
uses a remote LLM, embedding, or reranker, configure a `ProviderRegistry` with a
matching `ProviderPolicy` opt-in. Do not work around policy blocks by calling
provider SDKs directly from the Skill.

## Proposal Cannot Be Approved

Common causes:

- The proposal was already approved, rejected, or superseded.
- High-sensitivity storage is disabled by policy.
- The proposal requires confirmation and the host workflow is trying to
  auto-approve it.

Use `edit_memory_proposal()` to narrow the content or sensitivity before
approval.

## Conflict Needs Review

`memory_conflict_arbitrations` can return `needs_user_review`. This is expected
when the system detects contradiction but cannot safely choose a winner. Ask the
user which memory is current, then edit, archive, or approve the replacement.

Explicit correction language such as "actually", "instead", or "correction"
usually lets the strategy layer supersede the older memory automatically.

## Memory Feels Stale

Inspect the strategy profile:

```python
profile = skill.get_memory_strategy(memory_id)
```

If `strength` is low or `maturity` is `deprecated`, reinforce it after user
confirmation or let the decay/archive workflow stand. Avoid manually boosting a
memory just because it would make a current answer easier.

## Health Is Degraded

Common degraded states:

- Missing FTS index: rebuild if search is needed.
- Stale FTS entries: run a reindex after incomplete deletes.
- Missing or invalid manifest: reinitialize only after confirming the correct
  garden home path.

Do not silently create a new garden to hide a bad path. Ask for the intended
garden home when data appears missing.

## Session Confusion

Reuse the current `skill` object during a task. Open once with
`open_session()`, then keep using that object. Close only when the user asks to
end the memory session or when a temporary validation script exits.
