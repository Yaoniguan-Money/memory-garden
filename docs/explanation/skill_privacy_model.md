# Skill Privacy Model

Memory Garden Skill is local-first. The default configuration does not call
external model providers, does not load API keys, and does not send memory
content over the network.

## Remembering

`remember()` writes only through the rule Court path:

1. Observe user text as candidate Seed.
2. Open RuleCourt.
3. Apply safe rule verdicts when write mode is `court`.
4. Return source ids and event ids for audit.

Preview mode opens Court but skips Growth mutation.

## Forgetting

`forget()` is intentionally separate from provider advice. It resolves a local
MemoryCard and delegates to Soil hard forget. This avoids sending explicit
forget commands to LLM advisors.

## Providers

Provider modes are labels and policy controls:

- `disabled`: no provider.
- `fake`: deterministic local providers for tests.
- `custom`: caller-supplied provider implementation.

Provider output must pass model validation and source id checks at the Cognition
layer before it is accepted.

## Audit

`audit()` returns recent event summaries, memory and seed counts, and Skill
configuration. It is designed for inspection without dumping raw prompts or
secrets.

## Remaining Limits

Hard forget removes MemoryCards and search index entries. Depending on cascade
settings, audit records can remain. Products with stricter erasure requirements
should run forget proof checks after deletion.
