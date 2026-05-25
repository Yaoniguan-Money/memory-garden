# Real Provider Trial Checklist

Use this checklist before moving Memory Garden from local/fake-provider testing
into a real LLM or embedding-backed business trial.

## Scope

- [ ] Pick one bounded workflow, such as preference memory or release checklist memory.
- [ ] Use a sandbox garden path, not a production garden.
- [ ] Use non-sensitive test data first.
- [ ] Confirm owner, rollback path, and success metrics before any live traffic.

## Provider Configuration

- [ ] Use the canonical `memory_garden.providers` interfaces for new work.
- [ ] Keep API keys in environment variables or a caller-owned secret provider.
- [ ] Enable only the provider types needed for the trial:
  - `allow_remote_llm`
  - `allow_remote_embeddings`
  - `allow_remote_rerank`
- [ ] Enable `allow_raw_user_text` only for the sandbox workload being tested.
- [ ] Keep `allow_sensitive_text` disabled unless the trial explicitly covers sensitive handling.
- [ ] Set `max_chars_per_call` and `max_candidates_per_call` for cost and leakage control.

## Smoke Test

Run the offline smoke first:

```bash
python scripts/real_provider_smoke.py --provider fake --embedding-provider fake --fresh
```

Run a real LLM smoke with a caller-provided model:

```bash
set OPENAI_API_KEY=...
set MEMORY_GARDEN_LLM_MODEL=...
set MEMORY_GARDEN_EMBEDDING_MODEL=...
python scripts/real_provider_smoke.py --provider openai --embedding-provider openai --fresh
```

Run a DeepSeek LLM smoke with local/fake embeddings:

```bash
set DEEPSEEK_API_KEY=...
python scripts/real_provider_smoke.py --provider deepseek --embedding-provider fake --fresh
```

Required smoke outcomes:

- [ ] `propose` returns at least one proposal.
- [ ] `approve` creates a memory id.
- [ ] `retrieve` returns the approved memory for a related query.
- [ ] `brief.source_memory_ids` includes the approved memory id.
- [ ] Provider calls are recorded in product storage.

## Business Trial

- [ ] Run in shadow mode first: generate proposals and briefs without changing business behavior.
- [ ] Sample and review memory proposals before auto-approval.
- [ ] Track false positives, missed memories, incorrect recalls, blocked provider calls, latency, and cost.
- [ ] Verify forget planning, execution, reindex, and proof before any user data trial.
- [ ] Keep a local-only fallback path ready.

## Stop Conditions

- [ ] Provider policy blocks expected safe traffic.
- [ ] Sensitive text is sent unexpectedly.
- [ ] Retrieval regularly surfaces irrelevant or stale memories.
- [ ] Forget proof fails.
- [ ] Latency or cost exceeds the trial budget.
