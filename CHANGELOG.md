# Changelog

All notable changes to 记忆花园 Memory Garden are documented in this file.

## [Unreleased]

### Performance
- Product retrieval pipeline latency reduced from 553ms to 164ms P50 (-70%) through candidate truncation, pre-tokenization, NumPy batch scoring, and write-time retrieval index.
- Local embedding overhead reduced from 838ms to 118ms (164→282ms P50, -76%) via fts_with_vector_rescore strategy and binary BLOB vector storage.
- CJK FTS search recall from 0% to 40% via ngram token path before default unicode61 MATCH; P95 latency 2.7ms, 297 QPS on 500-memory library.
- FTS index rebuild uses executemany with configurable batch size instead of per-row INSERT.

### Retrieval
- Industry comparison benchmark against ChromaDB and FAISS Flat on identical data: Memory Garden Product achieves 43.3% Recall@5 vs ChromaDB 33.3% and FAISS 28.3%, with only 2 runtime dependencies.
- Rebuilt retrieval benchmark stack: NDCG/MRR/MAP/R-Precision, latency P50/P95/P99, layered datasets (tiny through xlarge), JSON/Markdown reports.
- Write-time retrieval index eliminates per-query tokenization and n-gram embedding overhead; bulk-read from memory_retrieval_index table with auto-index on card creation and reindex_retrieval_scores() for rule updates.
- Configurable retrieval strategy: fts_only / fts_with_vector_rescore (default) / full_hybrid via GardenRuntimeConfig.retrieval.strategy.
- Product retrieval coarse recall is FTS-primary with bounded in-memory fallback.

### Embedding
- Optional local embedding provider (memory-garden[embeddings], sentence-transformers) with bge-small-zh-v1.5 (24MB, CPU-only, no GPU/API key/network).
- Binary BLOB vector storage (struct.pack) replacing JSON TEXT columns; 10-15x faster deserialization.
- Embedding cache warm-up with content-hash deduplication.

### Configuration
- GardenRuntimeConfig tree: HarvestScoreWeights, RecencyDecayConfig, AnnIndexConfig, ConflictDetectionConfig, RetrievalConfig (scan_limit, coarse_top_m, score_top_n, strategy, vector_top_n), RetrievalFusionWeights, ReindexConfig, CjkScriptConfig, LocalEmbeddingConfig.
- Contradiction pairs loaded from JSON file (64 Chinese-English antonym pairs), configurable via ConflictDetectionConfig.
- All weights, thresholds, and limits injected from config tree; no hardcoded magic numbers in call sites.

### Architecture
- Transaction boundary fix: ProductMemoryStore write methods accept optional sqlite3.Connection; WriteWorkflowService.approve() writes all entities in a single shared-connection transaction.
- TOCTOU fix: save_memory_card relies on PRIMARY KEY + IntegrityError instead of application-level _exists() pre-check.
- Cross-layer dependency fix: _card_text and _tokens moved to core/text_utils.py.
- Code deduplication: coarse_scoring.py shared module, conflict.py public API, cosine_similarity unified to local_embedding, CJK _bigram_tokens helper.
- RetrievalFeatureVector + batch scoring with NumPy dot-product (fallback to per-card loop when numpy unavailable).
- SQLite pagination determinism: ORDER BY created_at DESC, id ASC.

### Security & Hardening
- ProviderPolicy defaults block remote LLM, embedding, and reranker unless explicitly opted in.
- Pre-release security audit: zero API keys in tracked files, zero leaked databases, .gitignore covers .benchmark_*/, cursor_*.md, codex_*.md.
- OPEN_SOURCE_GUIDE.md personal paths redacted to generic ~/.memory_garden/.
- CI runs pytest with coverage (fail-under 70%); README shows 93% coverage badge.

### Documentation
- Dual-language README sync: benchmark table, ablation waterfall diagram, industry comparison matrix, session commands (花花开/花花关), integration code examples, development section.
- Pre-release checklist at docs/release/pre_release_checklist.md covering security, files, README accuracy, documentation consistency, and release steps.
- CITATION.cff added for academic references.

## [1.4.0] - 2026-05-17

### Added

- Product memory workflow with proposals, approval, retrieval, versioning, strategy profiles, and hard forget proof.
- Optional DeepSeek/OpenAI-compatible provider integration through explicit `ProviderRegistry` configuration.
- LLM-written harvest briefs that keep natural-language `[use]` text while preserving internal `source_memory_ids`.
- Claude Code, Codex, Hermes, OpenAI, Anthropic, LangChain, LangGraph, FastAPI, and LlamaIndex adapters.
- Local-first release safety files: README, `README_中文.md`, SECURITY, CONTRIBUTING, Code of Conduct, MIT license, CI, and secret scanning baseline.

### Changed

- Default rules-only behavior remains unchanged when no provider is configured.
- Hook and framework adapter brief generation share the same traceable cognition helper.
- Open-source safety documentation now calls out ignored local data, SQL allowlists, and git history auditing.

### Verified

- The full pytest suite passes locally.
- `detect-secrets scan --all-files --baseline .secrets.baseline` passes locally.

## [1.0.0] - 2026-05-11

### Added

- Initial public Memory Garden lifecycle: Seed, Court, Growth, Dream, Harvest, Brief.
- Local SQLite persistence, FTS search, garden health checks, and hard forget proof.
- SDK facade, CLI demo, local deterministic retrieval, and core integration tests.
