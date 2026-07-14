# Memory Garden evidence package

This package evaluates retrieval quality, Hard Forget reliability, and critical-path test sensitivity. It separates synthetic offline evidence from real-provider claims and keeps rejected designs and failure samples.

## Approved results

1. On 100 independent labeled queries, 500 memories, 90% noise, and three insertion-order seeds, Product improved Recall@5 from 70.19% to 73.52% and NDCG@5 from 61.90% to 63.70% versus FTS5. It was much slower and regressed at the 100-memory scale.
2. Hard Forget passed 30/30 observed local cases across content proof, SQLite, FTS, Product retrieval, fake embedding cache, retrieval-event cleanup, and source-trace controls.

Exact approved wording and prohibited expansions are in `resume_metrics_approved.json`.

## Package map

- `experiment-config.json`: top-level experiment classification and commands.
- `dataset-manifest.json`: counts, provenance, and SHA-256 hashes.
- `config/`: fixed seeds and condition definitions.
- `datasets/retrieval_queries.jsonl`: 100 independent labeled query records.
- `raw/retrieval_runs.json`: every accepted query execution and aggregate.
- `raw/hard_forget_runs.json`: every delete case, proof checks, and harness checks.
- `raw/mutation_runs.json`: per-mutant test output.
- `raw/pytest.xml` and `raw/coverage.json`: full-suite test and coverage evidence.
- `raw/environment.json`: interpreter, OS, SQLite, and dependency versions.
- `failures/`: all retrieval misses/negative false positives, the rejected first dataset, embedding incompatibility, and mutation survivor history.
- `reports/`: readable results, limitations, candidate wording, and interview answers.

## Reproduction

PowerShell:

```powershell
.\evidence\reproduce.ps1
```

POSIX shell:

```sh
./evidence/reproduce.sh
```

The main retrieval result intentionally uses `--skip-local-embed`, because the recorded environment cannot initialize the real provider. Running without that option will attempt the provider and record its failure without substituting fake vectors.

## Boundaries

Retrieval data is synthetic and manually labeled, not user traffic. Hard Forget exercises real local persistence and retrieval code, while its fake embedding is cache-only. No metric claims remote deletion, cryptographic erasure, semantic embedding quality, universal Product superiority, or latency improvement.
