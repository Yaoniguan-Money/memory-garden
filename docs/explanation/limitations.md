# Limitations

Memory Garden has deliberate constraints. This document lists what the project cannot do, so you can decide if it fits your use case.

## No LLM Integration

The baseline does not call any language model API. Court judgment (27 rules), Harvest retrieval, and Dream cycles are rule-based. Provider interfaces (`LLMProvider`, `EmbeddingProvider`, `RelevanceProvider`) are defined but no concrete implementations are bundled. This means:

- Semantic understanding relies on keyword/pattern matching + local n-gram embedding
- No LLM summarization, rephrasing, or generation of memory content
- No cross-lingual semantic matching
- Harvest recall combines FTS5 keyword search with local embedding fallback, but does not use ML models

## Local Embedding Only (No Neural/ML Embeddings)

Memory Garden includes a deterministic, zero-dependency local embedding (`memory_garden/harvest/local_embedding.py`) based on character n-gram hashing. This enables hybrid search with embedding fallback when FTS5 returns no results. However, this is NOT a neural embedding model — it provides approximate matching but does not offer the semantic understanding of ML embeddings. Real ML embedding providers (e.g. sentence-transformers) can be plugged in via the `EmbeddingProvider` interface.

## No Cloud or Multi-Device Sync

All data lives in a local SQLite file or in-memory store. There is no server, no sync protocol, no multi-device merging. If you need cloud backup or cross-device memory, you must build it yourself.

## Minimal CLI Only (No Web UI)

There is no web interface or desktop app. A minimal CLI is available (`memory-garden demo/init/health/search`) but it is not a full CLI product. The project is primarily a Python library that you integrate into your own agent or application.

## No Multi-User or Multi-Tenant

The data model assumes a single user's memory garden. There are no user accounts, access control lists, or tenant isolation.

## Hard Forget Cascade is Opt-In

The `execute_hard_forget()` function deletes the MemoryCard row and FTS index entry by default. Full cascade deletion of related Seeds, CourtCases, and GardenEvents requires the opt-in `cascade=True` parameter. Without cascade, a determined auditor could reconstruct that a memory once existed from remaining audit records. Forget Proof (`prove_forget()`) can verify that all 6 garden surfaces are clean after a forget.

## Snapshot Regression, Not End-to-End Testing

The Lab layer evaluates hand-crafted dict snapshots, not live system output. It verifies that contracts are written correctly, not that the running system always satisfies them. End-to-end integration testing is still needed.

## Chinese-First Control Commands

Session control uses Chinese commands (花花开, 花花关) with English aliases. This reflects the project's origin but may be unfamiliar to non-Chinese-speaking users.

## Not Production-Ready

This project is experimental. APIs may change between versions. The rule-based engines have known accuracy limitations. Do not rely on Memory Garden for clinical, legal, financial, or safety-critical applications without thorough review.
