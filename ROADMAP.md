# Roadmap

记忆花园 Memory Garden is experimental software. This roadmap describes likely directions, not commitments.

## Current (v1.4.x)

- [x] Ten-layer architecture with clear boundaries
- [x] Rule-based Court, Dream, Harvest, and Brief pipeline
- [x] Session orchestration with control commands and lifecycle hooks
- [x] Local SQLite garden home, snapshot, health checks, migration helpers, FTS5 search, and forget proof
- [x] Product-grade memory proposals, approval flow, retrieval, strategy profiles, versioning, and hard forget
- [x] Sync and async chat adapters plus Claude Code, Codex, Hermes, OpenAI, Anthropic, LangChain, LangGraph, FastAPI, and LlamaIndex integrations
- [x] Optional provider interfaces for LLM, embedding, reranking, and secret lookup with policy gates
- [x] Observatory views and redaction-aware export renderers
- [x] Snapshot-based Lab regression, suite packs, CI contracts, and coverage checks
- [x] SDK facade (`MemoryGarden.local()`), CLI entry point, and `py.typed` marker
- [x] Comprehensive docs, examples, community health files, and release checklists
- [ ] Persistent session storage across process restarts
- [ ] Field-level configurable redaction policy beyond current adapter and view controls

## Near Term (v1.5.x)

- [ ] Expanded Lab fixture suites (Dream, Hard Forget, E2E adapter)
- [ ] Soil: real SQLite schema migration engine
- [ ] Soil: Chinese tokenizer for FTS5
- [ ] Additional examples with common integration patterns
- [ ] More GitHub Actions and repository automation examples
- [ ] Session replay and recovery helpers for long-running agent workflows

## Medium Term

- [ ] Pluggable Harvester interface with reference implementations
- [ ] Optional embedding-based Harvester (as extras, not default)
- [ ] Configurable redaction policy profiles
- [ ] Session persistence with replay capability
- [ ] Release to PyPI
- [ ] Documentation site (via mkdocs-material or similar)

## Longer Term (no timeline)

- [ ] LLM-based Court engine as optional replacement
- [ ] Multi-session memory continuity (cross-session identity)
- [ ] Memory export and import with Covenant-governed portability
- [ ] Visualization tools consuming Observatory traces
- [ ] RAG-style Harvest with external document ingestion

## Out of Scope

These are explicitly not planned for the core repository:

- Web UI or browser-based interface
- Cloud sync or multi-device support
- Multi-user or multi-tenant SaaS
- Mobile app
- Plugin marketplace
- Real-time collaboration
- Integration with specific LLM providers as hard dependencies

## How to Influence the Roadmap

- Open a [Feature Request](.github/ISSUE_TEMPLATE/feature_request.yml) issue
- Discuss on existing issues
- Submit a PR with a working implementation

The roadmap is a living document and will be updated as the project evolves.
