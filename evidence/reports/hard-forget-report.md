# Hard Forget reliability evidence

## Hypothetical resume sentence

在 3 个固定种子、30 条唯一记忆的离线删除实验中，Hard Forget 30/30 完成内容级删除证明，并通过 SQLite、FTS、Product 检索、embedding 缓存与检索事件清理验证。

## Design and result

Each case creates a uniquely marked memory through the Product write path, verifies source-seed and proposal traceability, warms a deterministic fake embedding cache, performs a mutating retrieval to create a retrieval event, then executes Product Hard Forget.

All 30 cases passed every harness assertion. The built-in proof covered these surfaces:

- `db_memory_card_row` and `db_content_scan`
- `fts_index_entry` and `fts_content_search`
- `search_content_probe` and `product_content_scan`
- bundle manifest, garden manifest, snapshot, and bundle content scans
- audit content scan and proof-redaction self-check

The harness separately verified post-delete absence from the repository, FTS search, Product retrieval, fake embedding cache, and retrieval events. Before deletion, each target was retrievable and had its expected trace and cache/event controls.

## Limits

The observed rate is 30/30, not a population guarantee. The fake embedding provider is used only to create a deterministic cache record; it is not a semantic-quality experiment. Remote replicas, third-party providers, external backups, and storage outside the garden directory are out of scope.
