# Concepts

Memory Garden is built around a garden metaphor. Each concept maps to a concrete Python object with well-defined behavior.

## The Garden Metaphor

A garden is not a database. You don't just INSERT and SELECT. You **plant seeds**, **judge** which ones should grow, **cultivate** the ones that do, **prune** the ones that no longer serve you, and **harvest** what's relevant right now.

Memory Garden applies this metaphor to AI agent memory.

## Core Concepts

### Seed

A **Seed** is a candidate memory extracted from a user message. It has not yet been judged. It carries a signal type (preference, fact, intent, etc.), tags, confidence, and a lifecycle state.

Seeds enter the system through **observation** (`Core.observe`). They never automatically become long-term memories.

### Memory Card

A **MemoryCard** is a long-term memory that has passed through Court judgment and been planted. It contains structured fields: title, essence, context, lifecycle state, source trace IDs, and more.

### Court

The **Memory Court** is a rule-based judgment engine. For each pending Seed, the Court opens a case, weighs evidence (prosecution and defense statements), and issues a **CourtVerdict**. The verdict determines the Seed's fate: plant it, compost it, hold it, send it to the greenhouse, or merge it.

The Court judges; it does not execute. Execution happens through Growth actions.

### Growth

**Growth** encompasses the actions that change a memory's lifecycle:

| Action | Meaning |
|---|---|
| **plant** | Promote a Seed to a MemoryCard |
| **compost** | Discard the narrative but retain the "nutrient" (why it was discarded) |
| **greenhouse** | Isolate a sensitive memory for later review |
| **prune** | Mark a memory as pruned (soft delete) |
| **forget** | Hard delete a MemoryCard |
| **merge** | Merge a Seed into an existing MemoryCard, or merge two cards |

### Dream

The **Dream Cycle** is a batch review process. It looks at pending Seeds and non-greenhouse MemoryCards, applying clustering, composting, and merging rules. Dream is triggered by policy thresholds, not a scheduler.

### Garden Journal

The **Garden Journal** is an append-only event log. Every significant action (seed created, court opened, plant executed, dream cycle completed) writes a `GardenEvent`. The journal is for audit and debugging, not for business logic.

## Runtime Concepts

### Garden Session

A **GardenSession** represents one conversation unit. It has a lifecycle: `closed → open → closing → closed`. Memory observation and harvesting only happen inside an open session.

### 花花开 / 花花关 (Flower Open / Flower Close)

Control commands in Chinese (with English aliases). When a user says exactly "花花开", a session opens. When they say "花花关", it closes. These commands are **never** stored as memories.

### Garden Brief

A **GardenBrief** is a pre-reply summary of relevant memories, prepared by the Harvest pipeline. It tells the agent what the garden knows about the current topic — without dumping full memory card bodies.

### Garden Tick

A **garden_tick** is the per-turn check: should we open Court now? Should we run a Dream cycle? It is governed by `RuntimePolicy` thresholds (turn count, pending seed count, signal strength).

## Harvest Concepts

The **Harvest pipeline** is a deterministic, rule-based retrieval chain: collect candidates → score → rank → build bouquet → write brief. It does not use embeddings, vector search, or LLMs.

## Observatory Concepts

The **Observatory** is a read-only layer that converts internal objects (HarvestTrace, GardenEvent lists, Runtime turn snapshots) into structured `ObservationTrace` and `ObservationView` objects with configurable redaction levels (PUBLIC, SAFE, INTERNAL).

## Lab Concepts

**Garden Lab** is a snapshot-based regression layer. Instead of running the real system, it evaluates deterministic assertions against hand-crafted dict snapshots. It answers: "does the system still satisfy its stated contracts?"

## Covenant Concepts

The **Garden Covenant** is the memory policy and trust layer. It centralizes rules about consent, sensitive data, model calls, harvesting, visibility, and portability. Hard baselines cannot be disabled. The Policy Engine returns structured, auditable decisions.

## What Memory Garden Is Not

- It is **not** a vector database or semantic search engine.
- It is **not** an LLM-based memory service.
- It is **not** a cloud-synced personal knowledge base.
- It is **not** a chatbot or agent framework.
- It is **not** a production-ready SaaS product.

It is a **local-first, auditable memory layer** that you integrate into your own agent.
