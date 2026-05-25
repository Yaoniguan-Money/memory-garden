# Privacy and Safety Policy

Memory Garden is local-first, but local storage still needs explicit policy.

## Write Gates

Use `propose_memory()` when the system needs reviewable capture. Use
`approve_memory_proposal()` only after user or host policy approval. Use
`remember_memory(..., mode="trusted")` or `mode="auto"` only when one of these
is true:

- The user explicitly asks to remember something.
- The current host application has a clear memory policy that allows the write.
- The user is using a command or workflow whose purpose is memory capture.

Do not infer permission from casual conversation alone.

`mode="manual"` creates proposals only. `mode="trusted"` auto-approves local
low-risk proposals. `mode="auto"` approves all proposals that pass policy gates.

## Sensitive Data

Do not store these by default:

- Passwords, tokens, API keys, recovery phrases, or credentials.
- Government identifiers, financial account numbers, or payment details.
- Medical, legal, immigration, employment, or education records.
- Precise location history or private contact details.
- Third-party secrets or private facts about people who did not consent.

If the user explicitly asks to store sensitive information and policy allows it,
summarize narrowly and avoid storing raw secrets.

High-sensitivity proposals require explicit confirmation by default. If
`allow_sensitive_storage=False`, the product layer blocks approval.

## External Provider Boundary

External providers are caller-owned. The product default is no remote calls.

- Remote LLM, embedding, and reranker providers are blocked unless
  `ProviderPolicy` enables the matching provider type.
- Raw user text and sensitive text are blocked from provider use by default.
- Provider call records are stored for audit, but secrets are not stored by
  Memory Garden.
- Secret resolution belongs in a caller-owned `SecretProvider`; do not hard-code
  keys into Skill files, examples, tests, or garden data.

## Retrieval and Briefing

Harvested context is guidance, not ground truth. When returning memory context:

- Prefer short summaries and `source_memory_ids`.
- Do not dump raw `MemoryCard` payloads unless the user is explicitly auditing.
- Do not inject memory into unrelated model calls.
- If matches are weak or empty, say there is no relevant local memory.

Product retrieval must pass an applicability check before ranking. Provide
`project_id`, `workspace_id`, `user_id`, `session_id`, and `task_type` whenever
the host application knows them. This prevents a memory that is textually
similar but scoped to another project or identity from being injected.

Use `allow_sensitive=True` only for explicit audit or user-approved sensitive
workflows. Otherwise medium/high sensitivity memories are blocked from model
briefing.

## Maturity and Evolution

Do not treat every stored memory as equally authoritative:

- `observed` memories are usable but weaker.
- `stable` memories have repeated evidence or successful use.
- `canonical` memories are durable user/project facts.
- `deprecated` memories should not influence normal answers.

Retrieval reinforces used memories. Periodic `decay_memory_strategies()` lowers
stale memory strength and can plan archival. `plan_memory_abstractions()` finds
stable related memories that should be summarized into a higher-level memory
instead of repeatedly injecting fragments.

## Forget Policy

Hard forget is destructive. Use this flow:

1. Resolve the target memory id when possible.
2. Run `forget(..., dry_run=True)` unless the user supplied an exact id and a
   clear deletion request.
3. Explain what will be removed if the user needs confirmation.
4. For product workflows, create a plan with `plan_memory_forget(...)`.
5. Execute with `execute_memory_forget(plan.id)` and report `proof.proven`.
6. Run cascade deletion for user-facing forget requests unless the user
   explicitly wants audit records preserved.
7. Report any partial or failed status from the returned metadata.

`cascade=False` can preserve related audit traces. Use it only when audit
retention is intentional.

## Audit Output

Keep audit limits small. Return counts, event ids, event types, object ids, and
short summaries. Avoid exporting full garden data unless the user explicitly
requests a data export and policy permits it.
