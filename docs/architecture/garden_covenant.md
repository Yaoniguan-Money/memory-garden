# Garden Covenant Architecture

Garden Covenant is the eighth Memory Garden layer: the Memory Policy & Trust Layer. It centralizes rules that were previously implicit across Core, Runtime, Harvest, Observatory, Integration, and Lab.

The Covenant does not plant, harvest, dream, export, render, or answer. It only answers policy questions and returns auditable `PolicyDecision` objects.

## Why It Exists

Memory Garden cannot rely on good intentions scattered across many modules. A garden that remembers must also know what it is never allowed to remember, display, export, or send to a model.

Garden Covenant provides:

- a readable `GardenCovenant` configuration model
- default local-first safety policy
- non-overridable `HardBaselines`
- validation that rejects unsafe configurations
- a `PolicyEngine` that returns structured decisions
- YAML / dict / env loading through explicit calls
- in-memory audit helpers and stable covenant hashes
- Lab snapshot assertions generated from hard baselines

## Design Sources

The layer borrows design patterns, not code:

- Constitutional AI: explicit principles constrain behavior.
- OpenAI Model Spec: hard rules override lower-priority configuration.
- Agents guardrails and ADK callbacks: policy checks should sit at lifecycle checkpoints.
- NeMo Guardrails and Guardrails AI: policy validation should be programmable and testable.
- OWASP LLM risks: sensitive information disclosure and excessive agency must be handled as first-class risks.
- GDPR Privacy by Design: default behavior should minimize exposure.
- MemGPT: external model context should be selected, not the full garden.

## Main Modules

| Module | Role |
|---|---|
| `memory_garden/covenant/models.py` | Pydantic policy models for consent, admission, emotional safety, sensitive memory, model calls, harvest, visibility, portability, hard baselines, and audit. |
| `memory_garden/covenant/defaults.py` | Default local-first covenant. |
| `memory_garden/covenant/validator.py` | Rejects unsafe covenant configuration and disabled hard baselines. |
| `memory_garden/covenant/decisions.py` | `PolicyDecision` and severity model. |
| `memory_garden/covenant/engine.py` | Read-only policy engine. |
| `memory_garden/covenant/loader.py` | Explicit dict / YAML / env loader. |
| `memory_garden/covenant/audit.py` | In-memory decision audit and stable covenant hash. |
| `memory_garden/covenant/status.py` | Status payload for future SDK / CLI display. |
| `memory_garden/covenant/lab.py` | Lab snapshot assertions generated from hard baselines. |

## Hard Baselines

Hard baselines cannot be disabled:

- hard forgotten text is never visible
- control commands are never memorized
- unsupported user preference instructions never enter Garden Brief
- hard forget overrides compost
- AI self-memory requires user adoption
- external models never receive the full garden by default
- API keys are never exported

The validator raises `CovenantValidationError` instead of silently repairing unsafe settings.

## Boundaries

Garden Covenant does not:

- call Core, Runtime, Harvest, Observatory, or Integration flows
- mutate Memory Garden objects
- create `.memory_garden` or `garden.db`
- modify Repository or SQLite schema
- call LLMs, embeddings, rerankers, vector stores, or network services
- implement CLI, Web UI, or FastAPI

Earlier layers can later consult the Covenant, but this layer does not change their current default behavior.

