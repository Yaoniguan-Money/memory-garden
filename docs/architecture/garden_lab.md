# Garden Lab 架构说明

本文描述 Memory Garden **第六层：Garden Lab / Evaluation & Regression Layer**。它是基于快照的语义评估与回归层，不包含真实业务执行，不替代集成测试，不依赖外部服务。

---

## 1. 这一层解决什么问题

前五层（Core、Runtime、Harvest、Observatory、Integration）定义了花园的生命周期、编排节奏、采摘观测与被集成方式。但每一层的后续修改都可能**无意中改变**前层已建立的行为契约——Runtime 调整命令短路顺序、Harvest 修改 brief 截断策略、Observatory 变更脱敏字段白名单——这些变更若没有回归检查，行为退化可能长期不被发现。

第六层 Garden Lab 解决的是：**把前五层的核心语义承诺变成可回归的、确定性的断言检查**。

具体来说，Lab 提供：

- 一套 Pydantic 模型（`LabCase`、`LabSuite`、`LabRun` 等）用于描述"测什么"和"结果是什么"。
- 十种确定性断言运算符（equals、contains、is_true、count_at_most 等），对 dict 快照做布尔判断。
- 五套手写 fixture 套件，覆盖 Seed 偏好提取、Runtime 命令短路、Court 判决、Harvest brief 约束、Observatory 脱敏等关键语义。
- 一个纯快照运行器（`SnapshotLabRunner`），对给定 suite 与 dict 快照做评估，不调用任何真实系统。
- 一个报告层（`LabRunSummary` / `format_lab_run_report`），将运行结果转成结构化摘要与短文本。

---

## 2. 这一层不解决什么问题

以下能力**明确不在第六层范围**：

| 不包含 |
|--------|
| 真实端到端 Runtime 执行 |
| CLI（命令行入口） |
| Web UI / API |
| LLM judge（用 LLM 对输出打分或做语义相似度判断） |
| embedding / vector 检索 / reranker / semantic search |
| Repository / SQLite 读写 |
| `.memory_garden` 或 `garden.db` 的文件创建 |
| 文件导出（JSON / HTML / Markdown 报告落盘） |
| 从真实 Runtime / Harvest / Observatory 采集快照的自动化管线 |

第六层是**消费端**：只消费 Pydantic 模型与手写 dict 快照，不触发任何业务副作用。

---

## 3. Garden Lab 总览

第六层的组件从数据到运行到报告形成一条纯内存链路：

```
LabCase / LabSuite ──→ SnapshotLabRunner ──→ LabRun ──→ LabRunSummary / report
       │                      │
       ▼                      ▼
  LabAssertion          evaluate_case
  (手写 expected)       (dict 快照断言)
       │
       ▼
  fixture suites
  (5 套 11 个用例，含 example_actual)
```

| 组件 | 文件 | 职责 |
|------|------|------|
| Lab models | `memory_garden/lab/models.py` | 11 个 Pydantic 模型：用例定义、断言、结果、运行记录 |
| Snapshot assertions | `memory_garden/lab/assertions.py` | 10 种确定性断言运算符，对 dict 快照执行布尔判断 |
| Fixture suites | `memory_garden/lab/fixtures.py` | 5 套手写套件，覆盖关键语义场景，含 example_actual 快照 |
| SnapshotLabRunner | `memory_garden/lab/runner.py` | 纯快照运行器：接收 suite + actual_data，输出 LabRun |
| Lab report | `memory_garden/lab/report.py` | `LabRunSummary` 结构化摘要 + `format_lab_run_report` 短文本 + `lab_run_passed` 判定 |

---

## 4. 核心对象

| 对象 | 作用 |
|------|------|
| **LabAssertion** | 单条断言：断言类型（equals / contains / is_true 等）、靶域（seed / runtime / court 等）、字段路径、期望值 |
| **LabAssertionType** | 断言运算符枚举：`equals`、`not_equals`、`contains`、`not_contains`、`is_true`、`is_false`、`count_equals`、`count_at_most`、`field_present`、`field_absent` |
| **LabTarget** | 断言所指子域枚举：`seed`、`court`、`growth`、`dream`、`harvest`、`runtime`、`observatory` |
| **LabCase** | 单个实验用例定义：`case_id`、名称、描述、断言列表、元数据（含 `lab_fixture_example_actual` 手写快照） |
| **LabSuite** | 用例套件：`suite_id`、名称、用例列表、元数据 |
| **LabCaseResult** | 单用例在某次运行下的结果：`case_id`、状态（passed / failed / skipped / errored）、失败列表、指标列表 |
| **LabFailure** | 断言未满足时的可读失败记录：`case_id`、靶域、字段路径、期望值、实际值、消息、断言类型、严重程度 |
| **LabMetricResult** | 浅层指标快照：名称、值、单位（如 `passed_cases=10`、`pass_rate=0.95`） |
| **LabRun** | 一次套件运行记录：`run_id`、`suite_id`、状态、`case_results` 列表、开始/结束时间、元数据 |
| **LabRunSummary** | 一次运行的摘要：`run_id`、`suite_ids`、全量/通过/失败/跳过计数、`pass_rate`、`failed_case_ids`、`top_failure_messages`（最多 5 条，每条 ≤160 字）、`generated_at` |

---

## 5. 断言层

`memory_garden/lab/assertions.py` 提供三个纯函数：

```python
evaluate_assertion(assertion, case_id, actual_data) -> LabFailure | None
evaluate_case(lab_case, actual_data) -> LabCaseResult
evaluate_suite_cases(cases, actual_per_case) -> list[LabCaseResult]
```

核心特性：

- **仅处理 dict actual_data 快照**。断言以 `assertion.target.value`（如 `"runtime"`）为 key 从 `actual_data` 取值作为根对象，再沿 `assertion.field_path`（如 `"nested.k"`）点分路径取值。
- **所有运算符返回确定性布尔结果**。不存在模糊匹配、相似度阈值、LLM 打分等非确定性路径。
- **路径缺失时返回失败而非抛异常**。`field_present` / `field_absent` 专门处理字段存在性断言。
- `evaluate_case` 对用例内全部断言逐一执行，一旦任一断言失败即标记用例 `failed`。
- `evaluate_suite_cases` 按 `case_id` 映射各用例的 actual_data 批量评估。

---

## 6. Fixture 样例库

`memory_garden/lab/fixtures.py` 提供五套手写 fixture 套件，通过 `default_lab_suites()` 返回稳定排序的列表：

| 套件 | 函数 | 用例数 | 覆盖语义 |
|------|------|--------|----------|
| Seed 提取 | `seed_extraction_fixture_suite()` | 2 | 偏好表达生成 pending 信号；控制口令不产生偏好 seed 捕获 |
| Runtime 命令短路 | `runtime_command_fixture_suite()` | 2 | 花花开命中时短路 after/agent；普通 OPEN 句不短路 |
| Court 判决 | `court_verdict_fixture_suite()` | 2 | 负面自评不晋升为长期身份记忆；敏感信息走 greenhouse 加固路径 |
| Harvest Brief | `harvest_brief_fixture_suite()` | 2 | 简报不嵌入完整 MemoryCard 正文；溯源以 id/短语为主而非全文 |
| Observatory 脱敏 | `observatory_redaction_fixture_suite()` | 2 | PUBLIC 视图不暴露完整 user_message / assistant_reply；使用截断占位 |

每个用例的 `metadata.lab_fixture_example_actual` 中存储**人工编写**的 dict 快照，可通过 `fixture_example_actual_from_case(lab_case)` 读取。快照描绘的是"理想行为"而非从真实系统 dump 的数据。

---

## 7. SnapshotLabRunner

`memory_garden/lab/runner.py` 提供 `SnapshotLabRunner` 类：

```python
runner = SnapshotLabRunner()

# 单用例
runner.run_case(case, actual_data) -> LabCaseResult

# 单套件
runner.run_suite(suite, actual_data_by_case_id) -> LabRun

# 多套件
runner.run_suites(suites, actual_data_by_case_id) -> LabRun
```

关键行为：

- **只运行传入的 suite 与 actual_data**，不自动加载 `default_lab_suites()`，不调用真实系统。
- actual_data 支持三种模式：（1）`{case_id: {...}}` 按用例映射；（2）`{case_id: ..., ...}` 部分命中时缺失用例标记失败；（3）keys 非 case_id 时作为共享快照分发给所有用例。
- 套件内对每个用例逐一调用 `evaluate_case`，断言异常被隔离为失败而不中断套件。
- `run_suite` / `run_suites` 自动汇总指标（`total_cases`、`passed_cases`、`failed_cases`、`total_failures`、`pass_rate`）并聚合状态（全部 passed → passed；任一 failed → failed；零用例 → skipped）。
- Runner 不修改输入（不可变性由测试验证）。

---

## 8. Lab Report

`memory_garden/lab/report.py` 提供四个公开接口：

| 函数 | 签名 | 说明 |
|------|------|------|
| `summarize_lab_run` | `(run: LabRun) -> LabRunSummary` | 从 LabRun 纯读取生成摘要，不重新执行断言 |
| `format_lab_run_summary` | `(summary: LabRunSummary) -> str` | 将摘要格式化为短文本，适合终端或 PR 评论 |
| `format_lab_run_report` | `(run: LabRun) -> str` | 便利函数：内部先 summary 再 format |
| `lab_run_passed` | `(run: LabRun) -> bool` | 仅当 `run.status == LabStatus.passed` 时返回 True |

文本报告格式固定，具备确定性（同输入→同输出）。输出包含：

- 运行 ID、状态
- 全量 / 通过 / 失败 / 跳过计数
- 通过率（`pass_rate`，保留 4 位小数）
- 若存在失败：列出 `failed_case_ids` 和最多 5 条失败消息摘要

报告**不输出**完整 `actual_data`、大对象 JSON dump、或超长字段（失败消息截断到 160 字符）。

---

## 9. 边界与安全语义

第六层在设计与实现上遵守以下硬边界：

| 边界 | 约束 |
|------|------|
| 不调用 Core | 全量 grep 命中数 0。`LabTarget` 枚举值（如 `"runtime"`）是靶域标识，非 import 路径 |
| 不调用 Runtime | 同上。Lab 不 import `memory_garden.runtime` 中的任何模块 |
| 不调用 Harvest | 同上。Harvest fixture 中的 `expected/actual` 为手写 dict，不调 `Harvester` |
| 不调用 Observatory | 同上。Observatory fixture 同理 |
| 不访问 Repository / SQLite | Lab 全部在内存中操作 dict 与 Pydantic 模型，不涉及 `memory_garden/storage/` |
| 不写 `.memory_garden` / `garden.db` | 测试中显式验证 `tmp_path` 下不产生这些路径 |
| 不输出完整 actual_data | `format_lab_run_report` 输出 < 2000 字符，不含大对象 JSON |
| 不做 LLM judge | 所有断言是布尔型确定性判断，不存在非确定性评估路径 |
| 不依赖外部服务 | 零新增 pip 依赖；仅使用项目已有的 `pydantic` |

---

## 10. 当前测试覆盖

全量测试基线：

```bash
python -m pytest tests -q
# 538 passed
```

Lab 专项测试：

```bash
python -m pytest tests/test_lab_models.py tests/test_lab_fixtures.py tests/test_lab_runner.py tests/test_lab_report.py -q
# 67 passed
```

测试覆盖的维度：

- 模型 JSON 序列化往返
- 10 种断言运算符的 pass / fail 路径
- 字段路径解析（根级、嵌套、不存在）
- `evaluate_case` / `evaluate_suite_cases` 聚合行为
- SnapshotLabRunner 的 case / suite / suites 三级接口
- actual_data 的三种分发模式（按 case_id / 共享 / 部分缺失）
- 异常隔离（单用例异常不中断套件）
- 指标汇总与状态聚合
- `LabRunSummary` 摘要正确性
- 文本报告格式与确定性
- 失败消息数量限制与长度截断
- 源码无外部 infra token（openai / anthropic / embedding / vector / reranker / search / sqlite / repository）
- 测试文件不 import Core / Runtime / Harvest / Observatory
- 运行时不在文件系统创建 `.memory_garden` / `garden.db`

---

## 11. 当前限制

| 限制 | 说明 |
|------|------|
| 只验证结构化快照 | Lab 的断言对象是 hand-crafted dict，不是从真实系统采集的数据。不能替代端到端集成测试 |
| 不跑真实端到端流程 | 没有"采集→评估→报告"的自动化管线。快照与真实行为之间的差距需后续阶段填补 |
| fixture 需随业务语义维护 | 当 Core/Runtime 的字段结构或行为契约变更时，fixture 中的 `expected` / `example_actual` 需人工同步更新 |
| 断言语言保持克制 | 当前 10 种运算符覆盖等值/包含/计数/真假/字段存在性，不表达"列表中每个元素满足某条件""有序比较""正则匹配""时序约束"等复杂语义 |
| 没有 CLI / 文件导出 / LLM judge | 报告只返回 Python 字符串，不落盘、不上传、不生成文件；不做 LLM 主观打分 |
| 用例数量有限 | 当前 5 套套件共 11 个用例，覆盖关键语义场景但远未穷举边界条件 |

---

## 12. 下一层预期

第六层本身**应先冻结**，只在发现语义 bug 时修复。后续可考虑的方向（不在当前基线承诺内）：

- **Cookbook / Examples**：提供利用 Lab 编写自定义回归套件的最小示例，演示如何在 CI 中集成。
- **轻 CLI**：一个 `python -m memory_garden.lab` 入口，接收 suite 名或 `--all`，运行后打印 report 到 stdout，退出码反映 pass/fail。
- **快照采集适配器**：从真实 Runtime / Harvest / Observatory 的 `metadata` 或返回结构中提取 dict 快照，桥接"真实行为"与"Lab 断言"之间的差距。
- **更完整端到端实验**：将 Lab 嵌入 CI pipeline，在每次 PR 时自动运行默认套件并输出 report。

以上仅为方向列举，不影响当前第六层的封版状态。