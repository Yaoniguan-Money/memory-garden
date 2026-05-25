# Architecture Overview

Memory Garden is organized into ten layers. Each layer is independently testable, has clear boundaries, and can be frozen without affecting the others.

## Layer Stack

```
Layer 10: Garden Soil             ← local-first home, manifest, snapshot, health
Layer 9: Manual & Nursery          ← docs, examples, community
Layer 8: Garden Covenant           ← memory policy and trust layer
Layer 7: Lab Cookbook / CI        ← CI contracts, catalog, coverage
Layer 6: Garden Lab               ← snapshot-based regression
Layer 5: Integration Layer        ← chat adapter protocols
Layer 4: Garden Observatory       ← read-only traces and redaction
Layer 3: Harvest Pipeline         ← deterministic memory retrieval
Layer 2: Garden Runtime           ← session orchestration
Layer 1: Garden Life Core         ← memory lifecycle kernel
```

## Layer 1: Garden Life Core

The memory lifecycle kernel. Defines Seed, MemoryCard, Court, Growth, Dream, and Garden Journal. All operations go through `MemoryGardenCore`, which assembles the repository, journal, observer, court, and dream engine.

**Key rule**: observe → court → verdict → growth. Never skip court.

[Full architecture doc](architecture/garden_life_core.md)

## Layer 2: Garden Runtime

Session orchestration. Connects the Core to conversation rhythm. Handles 花花开/花花关 commands, `before_reply` (brief), `after_reply` (observe + tick), and session lifecycle.

**Key rule**: commands short-circuit; before_reply never writes memory; after_reply only observes user messages.

[Full architecture doc](architecture/garden_runtime.md)

## Layer 3: Harvest Pipeline

Deterministic, rule-based memory retrieval for pre-reply context. Collects candidates by keyword/tag matching, scores, ranks, builds a bouquet (PRIMARY / CORROBORATION / GUARDRAIL slots), and writes a compact brief.

**Key rule**: deterministic pipelines only; local (non-ML) embedding available as fallback; no external LLM calls.

[Full architecture doc](architecture/harvest_pipeline.md)

## Layer 4: Garden Observatory

Read-only trace and redaction layer. Consumes HarvestTrace, GardenEvent lists, and Runtime turn snapshots. Produces `ObservationTrace` and `ObservationView` with PUBLIC / SAFE / INTERNAL redaction levels.

**Key rule**: never calls Core, never reads the database, never writes files.

[Full architecture doc](architecture/garden_observatory.md)

## Layer 5: Integration Layer

Protocol-based chat adapters. Provides `SyncGardenChatAdapter` and `AsyncGardenChatAdapter` that wrap a host agent with the full garden lifecycle. Includes `ChatAgentProtocol` and `AsyncChatAgentProtocol` for host agent implementation.

**Key rule**: thin adapters only; no new Runtime semantics.

[Full architecture doc](architecture/integration_layer.md)

## Layer 6: Garden Lab

Snapshot-based regression. Defines LabCase, LabSuite, 10 deterministic assertion operators, 5 fixture suites (11 cases), a SnapshotLabRunner, and a text report formatter.

**Key rule**: evaluates hand-crafted dict snapshots, never calls the real system.

[Full architecture doc](architecture/garden_lab.md)

## Layer 7: Lab Cookbook / CI Contracts

Developer tooling around the Lab. Provides a catalog, JSON case loader, reusable rule templates, suite packs (smoke/safety/full), CI report contracts, and coverage gap analysis.

**Key rule**: read-only metadata layer; no new execution paths.

[Full architecture doc](architecture/lab_cookbook.md)

## Layer 8: Garden Covenant

Memory policy and trust layer. Centralizes consent, sensitive data, model call, harvest, visibility, and portability rules. Hard baselines cannot be disabled. The Policy Engine returns structured `PolicyDecision` objects.

**Key rule**: only answers policy questions; never mutates garden objects.

[Full architecture doc](architecture/garden_covenant.md)

## Layer 9: Manual & Nursery

Documentation, examples, and community infrastructure. Makes the project understandable and contributable.

## Layer 10: Garden Soil

Local-first persistence, manifest, snapshot, and health layer. Provides the garden's physical home on the filesystem without automatic directory creation. Includes `resolve_garden_home()`, `initialize_garden_home()`, `load_manifest()`/`save_manifest()`, `create_garden_snapshot()`, and `check_garden_health()`.

[Full architecture doc](architecture/garden_soil.md)

## Cross-Cutting Constraints

Every layer obeys these constraints:

- **No external API calls** — no LLM providers, no vector DBs, no cloud services.
- **No heavy dependencies** — Pydantic and PyYAML only.
- **Local-first** — all data lives in a local SQLite file or in-memory.
- **Deterministic where possible** — rule-based engines, no non-deterministic evaluation.
- **Auditable** — structured traces, journal events, and policy decisions.

