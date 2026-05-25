# Memory Garden 检索 Benchmark

## 实验设置

- 数据集：`medium`
- 记忆条数：500
- 查询条数：20
- 噪声比：0.9
- 日期：2026-05-25
- 环境：Intel64 Family 6 Model 151 Stepping 2, GenuineIntel / Windows / Python 3.11.9

## 核心结果

| baseline | k | Recall@k | NDCG@k | MRR | Hit@k | P50(ms) | P95(ms) | QPS |
|----------|---|----------|--------|-----|-------|---------|---------|-----|
| fts5 | 5 | 38.33% | 0.434 | 0.787 | 85.00% | 2 | 3 | 421.0 |
| product | 5 | 38.33% | 0.434 | 0.787 | 85.00% | 140 | 173 | 7.5 |
