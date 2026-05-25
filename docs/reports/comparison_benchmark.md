| 系统 | Recall@5 | NDCG@5 | P50 | P95 | 内存(MB) | 依赖数 | 网络调用 | CO₂(g) | 嵌入模型 |
|------|----------|--------|-----|-----|----------|--------|---------|--------|----------|
| Memory Garden FTS5 | 40.0% | 0.415 | 3.1ms | 3.8ms | 432 | 2 | 0 | 0.00 | none (FTS5 CJK ngram) |
| Memory Garden Product | 43.3% | 0.454 | 175.8ms | 190.2ms | 434 | 2 | 0 | 0.00 | rules-only |
| ChromaDB | 33.3% | 0.372 | 176.8ms | 184.5ms | 506 | 134 | 0 | 0.00 | all-MiniLM-L6-v2 |
| FAISS Flat | 28.3% | 0.340 | 6.9ms | 7.4ms | 663 | 134 | 0 | 0.00 | BAAI/bge-small-zh-v1.5 |
