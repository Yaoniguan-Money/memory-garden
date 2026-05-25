# stage_resume_polish 执行总结

> 更新：2026-05-25

---

## 一、已完成

### 1. 配置与工程

| 项 | 说明 |
|----|------|
| `pyproject.toml` 增加 `[bench]` 可选依赖 | `chromadb`, `faiss-cpu`, `matplotlib`, `psutil` |
| License classifier 冲突 | 计划中要求删除的 MIT classifier 行，当前文件已无冲突项 |
| 全量单元测试 | **1451 passed，8 skipped**（无回归） |

### 2. 任务 1：行业对比 Benchmark（部分）

| 项 | 说明 |
|----|------|
| 脚本 `benchmarks/comparison/run_comparison.py` | 支持 MG FTS5、MG Product、ChromaDB、FAISS；缺依赖时优雅降级为 N/A |
| CLI `python -m benchmarks.comparison` | 可输出 JSON + Markdown 表 |
| **本机已跑通** Memory Garden 两行 | 结果见 `docs/reports/comparison_benchmark.json` |
| README 行业对比表 | 已填入 MG 实测数据；Chroma/FAISS 标为 N/A |

### 3. 任务 2：PyPI 发布（部分）

| 项 | 说明 |
|----|------|
| `python -m build` | 生成 `dist/memory_garden-1.4.0-py3-none-any.whl` 与 `.tar.gz` |
| `twine check dist/*` | wheel 与 sdist **均为 PASSED** |
| README PyPI 徽章 | **未加**（按计划：先发布成功再加） |

### 4. 任务 3：可视化

| 项 | 说明 |
|----|------|
| `benchmarks/visualization/charts.py` | 从 `benchmark_v2.json` 生成图表 |
| Ablations 瀑布图 | README 内嵌 Mermaid；源文件 `docs/reports/ablations_waterfall.mmd` |
| 延迟分布 PNG | `docs/reports/latency_distribution.png`（Product vs Product+Embed） |

### 5. 任务 4：真实数据集

| 项 | 说明 |
|----|------|
| `benchmarks/retrieval/real_queries.jsonl` | 12 条中文改写/同义查询（模拟真实场景） |
| `run_on_real_dataset()` | 已加入 `benchmarks/retrieval/runners.py` |
| 对比结果 | `docs/reports/real_dataset_comparison.json` |

### 6. 文档

| 项 | 说明 |
|----|------|
| README 检索章节 | Ablations、延迟图、行业对比、运行命令 |
| 本总结文档 | 即本文件 |

---

## 二、未完成

| 计划任务 | 当前状态 | 原因 / 依赖 |
|----------|----------|-------------|
| ChromaDB 同条件对比 | 未跑出数据（JSON 为 `na`） | `.venv` 未安装 `chromadb` |
| FAISS Flat 同条件对比 | 未跑出数据（JSON 为 `na`） | `.venv` 未安装 `faiss-cpu`（对比还需 `sentence-transformers`） |
| `comparison_benchmark.md` | 未生成 | 对比脚本曾因控制台编码报错；可重跑 `--markdown` 补全 |
| `twine upload`（实际上传 PyPI） | 未执行 | 需要你的 PyPI API Token，不能代传 |
| README PyPI / Python 版本徽章 | 未添加 | 计划要求发布成功后再加 |
| 任务 5：GitHub Pages `mkdocs gh-deploy` | 未执行 | 计划标注为可选 |
| 更新 `pyproject.toml` Documentation URL 为 GitHub Pages | 未改 | 依赖 Pages 先部署 |

---

## 三、遇到的问题

### 问题 1：`pip install chromadb / faiss-cpu` 多次被中断

- **现象**：安装命令运行 6～26 分钟，终端显示 `interrupted by the user`，依赖未装全。
- **影响**：行业对比里 ChromaDB、FAISS 两行只能 N/A，无法填 README 完整矩阵。
- **原因**：Windows 下 bench 依赖链重（grpc、onnx 等），耗时长；会话/终端中途结束。
- **处理**：脚本已做优雅降级；需本机一次性跑完：
  ```powershell
  .venv\Scripts\pip install "memory-garden[bench,embeddings]"
  .venv\Scripts\python -m benchmarks.comparison --dataset medium --output docs/reports/comparison_benchmark.json --markdown docs/reports/comparison_benchmark.md
  ```

### 问题 2：对比脚本控制台 `UnicodeEncodeError`（GBK）

- **现象**：`print` 对比表时报 `'gbk' codec can't encode character '\u2082'`（CO₂ 下标）。
- **影响**：仅终端输出失败；**JSON 已正常写入** `comparison_benchmark.json`。
- **处理**：已在 `run_comparison.py` 对 `print` 做编码降级。

### 问题 3：matplotlib 中文标签方框（字体）

- **现象**：生成 PNG 时大量 `Glyph ... missing from font(s) DejaVu Sans` 警告。
- **影响**：图中中文可能显示为方框；数值与柱状结构仍正确。
- **处理**：可选后续为 charts 配置中文字体；不阻塞数据与文件生成。

### 问题 4：PyPI 构建时 pip 网络超时

- **现象**：安装 `build` 时出现 `ReadTimeoutError`（files.pythonhosted.org），随后重试成功。
- **影响**：构建总耗时约 4 分钟，最终 **build + twine check 均成功**。
- **处理**：上传前若网络不稳可重试或使用镜像源。

### 问题 5：PyPI 上传无法代劳

- **现象**：`twine upload` 需账号 Token。
- **影响**：包已构建并通过 check，但 **PyPI 上尚无新版本**。
- **处理**：本地配置 Token 后执行 `twine upload dist/*`。

---

## 四、本机已产出的关键数据

### 行业对比（Memory Garden，medium）

| 系统 | Recall@5 | NDCG@5 | P50 | P95 |
|------|----------|--------|-----|-----|
| Memory Garden FTS5 | 40.0% | 0.415 | 3.5ms | 5.3ms |
| Memory Garden Product | 43.3% | 0.454 | 189ms | 205ms |
| ChromaDB | — | — | — | 未安装依赖 |
| FAISS Flat | — | — | — | 未安装依赖 |

### 真实改写 vs 合成查询（12 条）

| baseline | 合成 Recall@5 | 真实 Recall@5 | 差值 |
|----------|---------------|---------------|------|
| fts5 | 40.0% | 22.2% | -17.8pp |
| product | 43.3% | 33.3% | -10.0pp |

---

## 五、产出文件一览

| 路径 | 用途 |
|------|------|
| `docs/reports/stage_resume_polish_execution_report.md` | **本总结（完成/未完成/问题）** |
| `docs/reports/comparison_benchmark.json` | 行业对比 JSON |
| `docs/reports/real_dataset_comparison.json` | 真实 vs 合成 recall |
| `docs/reports/latency_distribution.png` | 延迟分布图 |
| `docs/reports/ablations_waterfall.mmd` | Ablations Mermaid 源 |
| `dist/memory_garden-1.4.0-py3-none-any.whl` | PyPI 构建产物 |
| `dist/memory_garden-1.4.0.tar.gz` | PyPI 构建产物 |
| `benchmarks/comparison/` | 行业对比脚本 |
| `benchmarks/visualization/charts.py` | 可视化脚本 |
| `benchmarks/retrieval/real_queries.jsonl` | 真实（改写）查询集 |

---

## 六、建议你本地补做的两步

1. **补全 Chroma/FAISS 对比**（终端勿中断，约 10–30 分钟）  
   `pip install "memory-garden[bench,embeddings]"` → 重跑 `python -m benchmarks.comparison ...`

2. **发布 PyPI**（需 Token）  
   `twine upload dist/*` → 成功后给 README 加 PyPI 徽章
