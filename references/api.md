# Memory Garden Skill API

Use these stable imports:

```python
from pathlib import Path
from memory_garden.sdk import MemoryGarden
from memory_garden.skill import SkillConfig, SkillWriteMode
from memory_garden.product import MemoryListFilter, MemoryPatch
from memory_garden.providers import ProviderRegistry
```

## Create a Local Garden

```python
garden = MemoryGarden.local(Path.home() / ".memory-garden")
skill = garden.as_skill()
skill.open_session()
```

Use a temporary path for tests:

```python
from tempfile import TemporaryDirectory

with TemporaryDirectory() as tmp:
    garden = MemoryGarden.local(tmp)
    try:
        skill = garden.as_skill()
        skill.open_session()
    finally:
        garden.close()
```

## Stable Methods

- `open_session(metadata=None)` returns `SkillOperationResult`.
- `close_session()` returns `SkillOperationResult`.
- `before(user_message, messages=None, metadata=None)` returns `SkillContext`.
- `after(user_message, assistant_reply)` observes the completed turn when the
  current implementation supports it.
- `chat(user_message, llm_fn, messages=None)` runs `before`, calls `llm_fn`,
  then runs `after`.
- `remember(text, metadata=None, mode=None)` returns `SkillOperationResult`.
- `forget(target, memory_id=None, reason="skill forget request", dry_run=False, cascade=True)` returns `SkillOperationResult`.
- `harvest(query, limit=5)` returns `SkillHarvestResult`.
- `audit(limit=None)` returns `SkillAuditView`.
- `health` returns the garden health report.
- `summary` returns the observatory summary view.

## Product Memory Methods

These methods are the product-grade surface. They keep the legacy Skill API
compatible while adding proposal review, versioning, relations, explainable
retrieval, and forget proof.

- `product` returns the underlying `ProductMemorySystem`.
- `configure_providers(providers)` attaches caller-owned external providers.
- `propose_memory(text, metadata=None)` returns `list[MemoryProposal]`.
- `memory_inbox(status="pending", limit=100)` lists proposals.
- `approve_memory_proposal(proposal_id, auto=False)` creates a `MemoryCard`.
- `reject_memory_proposal(proposal_id, reason="")` records rejection.
- `edit_memory_proposal(proposal_id, patch)` updates a proposal before approval.
- `remember_memory(text, mode="trusted", metadata=None)` runs the proposal
  pipeline with `manual`, `trusted`, or `auto` write policy.
- `list_memories(filters=None)` returns `list[MemoryView]`.
- `inspect_memory(memory_id)` returns `MemoryInspection`.
- `update_memory(memory_id, patch, reason="skill_update")` versions and patches.
- `retag_memory(memory_id, tags)` replaces tags.
- `set_memory_sensitivity(memory_id, level)` updates sensitivity.
- `archive_memory(memory_id, reason="skill_archive")` removes from active use.
- `restore_memory(memory_id, reason="skill_restore")` restores active use.
- `merge_memories(source_ids, target_id=None)` merges and archives sources.
- `retrieve_memories(query, limit=5, explain=True)` returns
  `MemoryRetrievalResult`.
- `build_memory_brief(query, limit=5)` returns `GardenBrief`.
- `get_memory_strategy(memory_id)` returns `MemoryStrategyProfile`.
- `assess_memory_applicability(memory_id, query, context=None)` returns
  `ApplicabilityDecision`.
- `reinforce_memory_strategy(memory_id, reason="skill_reinforce", amount=0.08)`
  strengthens a memory and may promote maturity.
- `decay_memory_strategies(limit=500)` applies deterministic staleness decay.
- `plan_memory_abstractions(limit=500)` plans stable-memory abstraction
  candidates.
- `plan_memory_forget(target="", memory_id=None, cascade=True)` returns
  `ForgetPlanRecord`.
- `execute_memory_forget(plan_id)` returns `(ForgetPlanRecord, ForgetProofRecord)`.
- `prove_memory_forget(memory_id, plan_id="")` persists forget proof.

Example:

```python
proposals = skill.propose_memory("remember: prefer concise release notes")
card = skill.approve_memory_proposal(proposals[0].id)
skill.update_memory(card.id, MemoryPatch(tags=["release", "style"]))
context = {"project_id": "atlas", "task_type": "writing"}
strategy = skill.get_memory_strategy(card.id)
applicability = skill.assess_memory_applicability(card.id, "release style", context=context)
result = skill.retrieve_memories("release style", limit=5, context=context)
brief = skill.build_memory_brief("release style", context=context)
```

The product `remember_memory()` helper returns a dictionary with:

- `proposals`
- `approved_memory_ids`
- `pending_proposal_ids`
- `mode`

## Memory Strategy Model

Each approved memory has a `MemoryStrategyProfile` stored separately from the
`MemoryCard`:

- `layer`: `episodic`, `semantic`, `preference`, `procedural`,
  `project_state`, `identity`, or `safety_boundary`.
- `scope`: `global_user`, `project`, `workspace`, `session`, or `identity`.
- `scope_id`: project/workspace/session/user identifier when scoped.
- `maturity`: `candidate`, `observed`, `stable`, `canonical`, or `deprecated`.
- `strength`: current confidence/usefulness after reinforcement and decay.
- `evidence_count`, `mention_count`, `use_count`, `contradiction_count`,
  `correction_count`: lifecycle counters.

Retrieval uses this profile before ranking. A memory can match text but still be
blocked when the project scope, sensitivity, maturity, or task layer does not
fit. Retrieval returns `applicability_score`, `applicability_reasons`, and
`risk_flags` per hit.

Use `ApplicabilityContext` or an equivalent dict to avoid cross-project and
cross-identity leakage:

```python
context = {
    "project_id": "atlas",
    "workspace_id": "engineering",
    "task_type": "coding",
}
hits = skill.retrieve_memories("release checklist", context=context)
```

Conflict arbitration is persisted in `memory_conflict_arbitrations`. Explicit
corrections supersede older memories when evidence is strong; otherwise the
system records `needs_user_review` instead of silently overwriting.

## Write Modes

Use `mode="preview"` or `SkillWriteMode.PREVIEW` to inspect the Court result
without applying growth actions:

```python
preview = skill.remember("User prefers compact examples.", mode="preview")
```

Use `mode="court"` or the default write mode to let rule Court decide whether a
memory should be planted, composted, greenhoused, merged, or skipped:

```python
result = skill.remember("User prefers compact examples.", mode="court")
```

## Return Models

`SkillOperationResult` includes:

- `ok`
- `operation`
- `mode`
- `session_id`
- `seed_ids`
- `court_case_ids`
- `memory_ids`
- `event_ids`
- `verdicts`
- `preview`
- `skipped_reasons`
- `metadata`
- `error`

`SkillHarvestResult` includes:

- `ok`
- `query`
- `brief`
- `source_memory_ids`
- `candidate_memory_ids`
- `mode`
- `metadata`
- `error`

`SkillAuditView` includes:

- `event_count`
- `events`
- `memory_count`
- `seed_count`
- `config`

## Exact Id Forget

Prefer exact ids when available:

```python
plan = skill.forget(
    "ignored when memory_id is set",
    memory_id="mem-123",
    reason="user request",
    dry_run=True,
)
```

If no id is available, `forget(target=...)` resolves by local substring match
against memory title, essence, fragrance, thorns, and tags.

## Product CLI

The package exposes scriptable product commands:

```bash
memory-garden remember "remember: prefer dark mode" --mode trusted
memory-garden propose "remember: prefer compact lists"
memory-garden inbox --status pending
memory-garden approve PROP_ID
memory-garden memories --tag ui
memory-garden inspect MEMORY_ID
memory-garden update-memory MEMORY_ID --title "Compact lists" --tags ui,lists
memory-garden retrieve "dark mode" --limit 5
memory-garden brief "release style"
memory-garden strategy MEMORY_ID
memory-garden applicability MEMORY_ID "release style" --project-id atlas
memory-garden reinforce-memory MEMORY_ID
memory-garden decay-memories
memory-garden plan-abstractions
memory-garden forget-plan --memory-id MEMORY_ID
memory-garden forget-exec PLAN_ID
```

CLI product commands output JSON for automation.

## External Providers

Memory Garden does not ship remote provider credentials. Applications provide
their own implementations of:

- `LLMProvider`
- `EmbeddingProvider`
- `RerankerProvider`
- `SecretProvider`

Attach them through `ProviderRegistry`. Remote providers are blocked by default
unless `ProviderPolicy` explicitly opts in to the matching provider type.
