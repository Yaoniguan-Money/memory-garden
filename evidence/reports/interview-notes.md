# Interview follow-up answers

## Why compare at two scales?

The Product ranker has more candidate and feature work than FTS5. The experiment shows it regressed at 100 memories but improved ranking quality at 500 memories. Reporting both prevents a scale-specific win from being presented as a universal one.

## Are the 100 queries independent?

Yes at the query-record level: all 100 IDs and texts are unique, and each asks a distinct direct, scenario, cross-memory, boundary, conflict, edge, application, or no-answer question. They were manually labeled from the fixed catalog. The rejected earlier dataset used five wording variants of 20 intents and is explicitly excluded.

## Why is seed variance zero?

Seeds only change memory insertion order. Retrieval is deterministic and relevant-set membership in top five did not change across seeds. This supports ordering stability under insertion order; it does not measure model sampling variance.

## What is the major retrieval weakness?

Both baselines returned results for 9 of 10 no-answer queries. Product also had roughly 76 times the P50 latency of FTS5 at 500 memories. The evidence supports a modest quality improvement at scale with a substantial latency and abstention tradeoff.

## Why is there no embedding result?

The installed package set is incompatible: Transformers 5.9.0 imports a distributed Torch module absent from Torch 2.4.1. The provider therefore failed before a real embedding experiment could start. A fake embedding appears only in Hard Forget to exercise cache cleanup and is never reported as retrieval quality.

## What does 30/30 Hard Forget prove?

It proves the observed local cases completed the intended Product/SQLite/FTS/cache/event workflow and content-level proof checks. It does not prove cryptographic erasure, deletion from remote providers, or universal 100% production reliability.
