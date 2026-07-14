# Memory Garden retrieval evidence

## Hypothetical resume sentence

在 100 条独立标注查询、500 条记忆且 90% 噪声、3 个固定种子的离线实验中，相比 FTS5，Product 检索将 Recall@5 从 70.19% 提升到 73.52%（+3.33pp），NDCG@5 从 61.90% 提升到 63.70%（+1.80pp）。

## Design

- Dataset: 100 unique, manually curated queries; 90 positive/boundary/conflict and 10 no-answer negative cases.
- Memory scales: 100 memories at 85% noise and 500 memories at 90% noise.
- Seeds: 104729, 130363, 155921. A seed shuffles insertion order; the query set and memory content stay fixed.
- Baselines: SQLite FTS5 and Product retrieval without an LLM.
- Metrics: positive-query Recall@5 and NDCG@5; negative false-positive rate; P50/P95 query latency.
- Every run and every top-5 result is present in `raw/retrieval_runs.json`; misses and negative false positives are retained in `failures/retrieval_failures.jsonl`.

## Results

| Memories / noise | Baseline | Recall@5 mean ± seed SD | NDCG@5 mean ± seed SD | Negative FPR | P50 mean | P95 mean |
|---|---:|---:|---:|---:|---:|---:|
| 100 / 85% | FTS5 | 85.74% ± 0.00pp | 77.55% ± 0.00pp | 90.00% | 2.63ms | 3.64ms |
| 100 / 85% | Product | 81.85% ± 0.00pp | 75.82% ± 0.00pp | 90.00% | 102.00ms | 239.45ms |
| 500 / 90% | FTS5 | 70.19% ± 0.00pp | 61.90% ± 0.00pp | 90.00% | 2.56ms | 3.47ms |
| 500 / 90% | Product | 73.52% ± 0.00pp | 63.70% ± 0.00pp | 90.00% | 194.17ms | 240.13ms |

At 500 memories Product improved Recall@5 by 3.33 percentage points and NDCG@5 by 1.80 points. At 100 memories it regressed by 3.89 and 1.73 points respectively. Product also incurred a large latency cost. The result therefore supports only a scale-specific quality tradeoff, not universal superiority.

The zero Recall standard deviation is expected because insertion-order seeds did not change which relevant IDs reached the top five. Product NDCG also remained identical on the independently curated set. This measures ordering stability, not stochastic model variance.

## Rejected first pass

The first run used five surface variants of 20 base intents. Although it contained 100 rows, it did not meet the independent-query admission gate. Its complete raw output is retained as `raw/retrieval_surface_variant_audit.json` and is excluded from approved metrics.

## Embedding gap

`sentence-transformers` 5.5.1 is installed and the BGE model files are cached, but importing its Transformers dependency fails because Torch 2.4.1 does not provide `torch.distributed.tensor.device_mesh`, which Transformers 5.9.0 imports. No embedding numbers were produced or inferred.

## Limits

The memory catalog and queries are synthetic. Medium scale expands variants from 15 base memories. Nine of ten no-answer negatives caused a result in both baselines. The dataset does not represent real user traffic, remote storage, or multilingual semantic retrieval.
