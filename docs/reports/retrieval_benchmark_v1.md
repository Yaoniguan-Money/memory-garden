# Retrieval Benchmark v1 报告

> **免责声明**：本报告描述的是 Memory Garden 开源仓库内的**本地可复现实验基线**，**不是**生产环境 benchmark。数据集为合成 gold + noise 记忆，不代表真实用户数据，也不应与 MTEB / BEIR 等行业基准直接对比。

## 目的

在高噪声记忆库（默认 noise_ratio=0.85）下，对比两条检索路径的 IR 指标：

| Baseline | 实现 | 说明 |
|----------|------|------|
| `fts5` | `memory_garden.soil.search.search_garden()` | SQLite FTS5 关键词检索（需先 `reindex_garden`） |
| `product` | `ProductMemorySystem.retrieve()` | Product 层 rules-only 检索（无 ProviderRegistry / 无 Harvest） |

本阶段**不包含** `GardenHarvester` / Harvest 采摘流水线。

## 数据集

| 项目 | 数量 / 说明 |
|------|-------------|
| Gold 记忆 | 15 条（`benchmarks/retrieval/gold_memories.json`） |
| Noise 模板池 | 100 条（`benchmarks/retrieval/noise_templates.json`） |
| 查询用例 | 20 条（`benchmarks/retrieval/cases.jsonl`） |
| noise_ratio=0.85 时 noise 条数 | `round(15 × 0.85 / 0.15) = 85` |
| 总记忆数 | 100 |

Noise 从模板池**按固定顺序**取前 N 条，无随机 shuffle，保证 pytest 可复现。

语义场景源自 `scripts/calibrate_weights.py` 的标注集，但本 benchmark **走真实 Soil/Product 代码路径**，而非离线玩具打分。

## 指标定义

- **recall@k**：`|relevant ∩ top_k| / |relevant|`（queries 宏平均）
- **precision@k**：`|relevant ∩ top_k| / k`
- **hit@k**：top_k 中是否出现任一 relevant（0/1，queries 宏平均）
- **latency_ms_avg**：单次查询平均耗时（毫秒）

默认 k=5。

## 运行方式

```bash
pip install -e ".[dev]"

# 仅跑 benchmark 测试
python -m pytest tests/test_retrieval_benchmark.py -q

# 跑完整 benchmark 并打印报告
python scripts/run_retrieval_benchmark.py

# JSON 输出（可选，默认不提交 git）
python scripts/run_retrieval_benchmark.py --output json --json-out benchmarks/retrieval/last_run.json
```

可选参数：`--noise-ratio 0.85`、`--k 5` 或 `--k 1,3,5,10`、`--garden-path /path/to/garden`。

## 首次实测结果（2026-05-24，Windows，rules-only）

运行命令：

```bash
python scripts/run_retrieval_benchmark.py
```

输出：

```
=== Retrieval Benchmark v1 (local, not production) ===
noise_ratio=0.85  total_memories=100  total_queries=20

[fts5] k=5
  recall@5=0.0000  precision@5=0.0000  hit@5=0.0000  latency_ms_avg=2.23

[product] k=5
  recall@5=0.2500  precision@5=0.1500  hit@5=0.4500  latency_ms_avg=179.29
```

### 结果解读

1. **FTS5 baseline 全零**：当前 Soil FTS5 使用 `unicode61` 分词器，对中文整句 query 的 `MATCH` 几乎无效；CJK 回退为整句 `LIKE`，而 gold 记忆正文并不包含完整问句，因此在本次中文 query 集上 recall/hit 为 0。这反映的是 **FTS5 路径在当前 tokenizer + 中文整句 query 下的局限**，不是 benchmark 造假。
2. **Product baseline**：rules-only 的 keyword overlap + tag + 本地 embedding 打分，在 85% 噪声、100 条记忆库下 **recall@5=25%**、**hit@5=45%**（即 20 条 query 中约 9 条在 top-5 命中至少一条 gold）。

## 能否支撑简历里的「79% 召回率」？

**不能。** 本 v1 基线在默认配置下的 **hit@5 为 45%**，**recall@5 为 25%**，与「79% 召回率」差距显著，且：

- 数据集为合成 gold/noise，不是生产记忆库；
- 未启用 embedding/reranker provider；
- 指标为 recall@5 / hit@5，与未定义的「79%」统计口径可能不一致；
- FTS5 路径在本 query 形态下几乎无效，不能作为「系统整体召回」的代表。

若简历需写检索能力，建议使用更稳妥表述，例如：

- 「构建本地可复现检索 benchmark（gold/noise 数据集，noise_ratio=0.85），对比 FTS5 与 Product rules-only retrieve，输出 recall@k / hit@k / latency。」
- 「在高噪声合成记忆库（100 条，85% noise）上，Product retrieve hit@5=45%、recall@5=25%（v1 本地基线，非生产数据）。」
- 「提供 pytest 守护的检索实验基线，支持固定数据集与双 baseline 复现。」

**不要**写「召回率达 79%」或类似未在本 benchmark 中实测的数字。

## 架构边界

- **未修改** `memory_garden/` 下任何核心模块。
- 新增代码仅位于 `benchmarks/`、`scripts/`、`docs/reports/`、`tests/`。
- `benchmarks/retrieval/last_run.json` 已加入 `.gitignore`，临时输出不提交。

## 后续可改进方向（非本阶段范围）

- 为 FTS5 baseline 增加英文 query 子集或关键词化 query，使 FTS5 对比更公平；
- 增加 `--provider fake` 可选路径，评测 embedding/reranker 对 recall 的提升（仍不用真实云端 LLM）；
- 扩大 gold 集或引入真实脱敏标注集（需单独隐私审查）。
