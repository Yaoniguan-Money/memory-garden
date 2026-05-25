# Harvest Pipeline 架构说明

本文描述 Memory Garden **第三层（Harvest）** 的封版架构：在 **before_reply** 阶段，如何从调用方给定的 `MemoryCard` 列表中筛出少量候选、经规则编排后产出 **短小、可追溯、可注入第二层** 的 `GardenBrief`。  
第三层实现为 **本地规则版基线**；文中能力边界以当前代码为准，不展开产品宣传。

---

## 1. 这一层解决什么问题

- **输入**：一次用户回合的查询语义（经 `HarvestQuery` 或从 `TurnContext` 映射而来），以及 **已有** 的 `MemoryCard[]`（由集成方提供，本层不定义存储来源）。
- **输出**：
  - **编排用简报**：`HarvestGardenBrief`（第三层）经 `to_runtime_brief()` 得到第二层 `GardenBrief`，供回答前阶段注入提示或策略，字段包含 `intent` / `use` / `avoid` / `style` / `safety` / `nudge` / `source_memory_ids`。
  - **可选追溯**：单次采摘的 `HarvestTrace`（含候选、分值、策略决策快照、花束、简报等），用于调试或可观测性；**不作为**第二层运行时简报的载荷。

第三层回答的是：**在不去调用大模型检索、不向数据库直连的前提下**，如何用确定性规则完成「采摘 → 排序 → 槽位 → 短文简报」的一条可测链路，并与 Runtime **HarvesterProtocol** 对齐。

---

## 2. 这一层不解决什么问题

以下能力 **不在当前第三层实现范围内**（若未来要做，应在独立设计中明确数据面与安全面）：

- **LLM**（生成摘要、重写简报、_lens 语义判断等）
- **ML embedding** 与向量索引（本地确定性 n-gram embedding 已可用，见 `memory_garden/harvest/local_embedding.py`）
- **reranker**（交叉编码器等）
- **vector DB** 与广义 **外部 search**
- **GardenRepository / SQLite 直连**（Harvest 管线内部不读取仓库；适配器默认 `memory_provider` 为空列表）
- **CLI / Web UI / 云同步**

---

## 3. Pipeline 总览

数据与控制流自上而下为 **模块化阶段**；端到端再由 **GardenHarvester** 串联，并经 **RuntimeGardenHarvesterAdapter** 对齐第二层。

```text
MemoryCard[]
    -> LocalCandidateCollector          # 产出 MemoryCandidate[]
    -> RuleBasedHarvestScorer           # 产出 HarvestScore[]（与候选对齐）
    -> RuleBasedHarvestRanker           # 产出 HarvestRankOutcome（含 ranked_candidates）
    -> GardenBouquetBuilder             # 产出 GardenBouquet（槽位 + metadata）
    -> HarvestGardenBriefWriter         # 产出 HarvestGardenBrief
```

```text
GardenHarvester
    （内部严格按上述顺序调用各组件）

RuntimeGardenHarvesterAdapter
    TurnContext -> HarvestQuery + memory_provider(turn_context) -> GardenHarvester.harvest -> HarvestGardenBrief.to_runtime_brief()

GardenBrief                           # 第二层 runtime.session.GardenBrief
```

说明：`GardenHarvester` **不替代**单列组件；它是 **同一套组件的内存流水线封装**。适配器只做 **上下文映射 + MemoryCard 来源注入 + Trace 挂载**，不暴露 scoring/ranking 的实现细节。

---

## 4. 核心对象

| 对象 | 职责摘要 |
|------|----------|
| **HarvestQuery** | 单次采摘查询快照：`raw_user_text`、`session_id`、`turn_index`、`metadata`、`lenses` 等；**非**会话存储。 |
| **MemoryLens** | 透镜元数据（名称、facet 等），可被 collector 与用户查询透镜对齐；**非**学习型 Lens。 |
| **MemoryCandidate** | 单层候选：绑定 `memory_id`、节选、匹配原因等；可追溯至第一层 `MemoryCard.id`。 |
| **HarvestScore** | 规则版分项分：`relevance`、`recency`、`policy_boost`、`notes` 等占位结构。 |
| **HarvestRankOutcome** | 排序结果：`ranked_candidates` + 聚合 **`HarvestPolicyDecision`**（准入/拒绝 id、配额原因等）。 |
| **GardenBouquet** | 按槽位编组的 `candidate_id` 列表及 `metadata`（如 `placements`、`excluded`、`memory_ids_ordered`）。 |
| **HarvestGardenBrief** | 第三层简报；含 `token_estimate`、`mode` 等扩展字段；可通过 **`to_runtime_brief()`** 裁剪为第二层 `GardenBrief`。 |
| **HarvestTrace** | 单次采摘快照：`query`、effective `lenses`、`candidates`、`scores`、`policy_decisions`、`bouquet`、`brief`、`model_calls`（规则版可为空）。 |
| **HarvestBudgetPolicy** | 配额与模式占位：`max_candidates`、`token_budget_soft`、`default_lenses`、`default_brief_mode` 等；**具体执行分散在 ranker/builder/writer**。 |

---

## 5. 核心模块

| 模块路径 | 说明 |
|-----------|------|
| `memory_garden/harvest/collector.py` | **LocalCandidateCollector**：基于用户文本分词与用户/记忆标签交集等 **轻量规则** 收集候选；可配合 `metadata`（如允许温室卡片进入候选集合）由上层注入。 |
| `memory_garden/harvest/scoring.py` | **RuleBasedHarvestScorer**：对候选逐项产出 **HarvestScore**（无外部模型）。 |
| `memory_garden/harvest/ranking.py` | **RuleBasedHarvestRanker**：按 `relevance` 主序、`policy_boost` 辅序 **稳定排序**；受 **HarvestBudgetPolicy.max_candidates** 等约束。 |
| `memory_garden/harvest/bouquet.py` | **GardenBouquetBuilder**：将排序结果分入 **PRIMARY / CORROBORATION / GUARDRAIL**（及预算、软 token 占位），写出 placements / excluded 等 metadata。 |
| `memory_garden/harvest/brief.py` | **HarvestGardenBriefWriter**：根据花束与用户查询写 **短文简报**；区分积极引用与 GUARDRAIL；**不写**长篇记忆正文拼接。 |
| `memory_garden/harvest/harvester.py` | **GardenHarvester**：依赖注入组装上述组件，`harvest(HarvestQuery, MemoryCard[], policy?) -> HarvestTrace`；内含 **effective_query**（合并 `query.lenses` 与 `policy.default_lenses` 去重，避免追溯链与 collector 透镜不一致）。 |
| `memory_garden/harvest/runtime_adapter.py` | **RuntimeGardenHarvesterAdapter**：实现第二层 **HarvesterProtocol**；`memory_provider(TurnContext) -> MemoryCard[]`；维护 **last_trace**、可选 **trace_sink**；返回 **GardenBrief**。 |

模型与枚举定义集中在 **`memory_garden/harvest/models.py`**，策略数据类在 **`memory_garden/harvest/policy.py`**。

---

## 6. 关键流程

### 6.1 候选收集（LocalCandidateCollector）

- 从 `HarvestQuery.raw_user_text` 与 `metadata.tags`、`query.lenses` 等与 `MemoryCard` 字段做 **字面/标签层**匹配。
- 默认可丢弃 **温室（greenhouse）** 卡片（除非查询 `metadata` 显式放开）；产出带 `metadata.source_memory` 等可追溯字段的 **MemoryCandidate**。
- **不**做向量检索、**不**改写入参 `MemoryCard`（Harvest 链路约定由调用方保证只读使用）。

### 6.2 规则打分（RuleBasedHarvestScorer）

- 对 **每个候选** 输出一条 **HarvestScore**，与候选列表对齐；分数用于后续排序与花束风险提示，**不**作为 LLM token 侧的「置信度」对外承诺。

### 6.3 稳定排序（RuleBasedHarvestRanker）

- 稳定排序键保证同分同 boost 下 **原始顺序确定性**。
- 应用 **max_candidates** 等配额，并在 **HarvestPolicyDecision** 中记录 cap、缺失分数、重复 score 跳过等可追溯原因。

### 6.4 花束构建（GardenBouquetBuilder）

- 综合考虑 **相关性阈值、lifecycle/风险注解、thorn 长度** 等因素，把候选放入 **核心 / 佐证 / 护栏** 槽位；超出预算者进入 **excluded** metadata。
- 产出 placements，供简报写作按顺序解读。

### 6.5 简报写作（HarvestGardenBriefWriter）

- 用 **PRIMARY/CORROBORATION** 的 `memory_id` 构造 **可用线索**（`use`）与 **`source_memory_ids`**（仅限进入花束积极侧且无禁止生命周期的条目）。
- **GUARDRAIL** 只影响 **avoid / safety / nudge** 措辞，不计入积极 `source_memory_ids`。
- **token_estimate** 为确定性字符粗估（非真实 tokenizer）。
- **`scores` 文案侧可显式不参与叙述**，以避免虚构分值细节。

### 6.6 纯内存总流程（GardenHarvester）

顺序固定：**collect → score → rank → build bouquet → write brief → 封装 HarvestTrace**。  
规则版 **`model_calls` 为空**，不伪造模型调用记录。

### 6.7 Runtime adapter 接入 before_reply

- **`RuntimeGardenHarvesterAdapter.harvest(TurnContext)`** 构造 **HarvestQuery**（透传 `metadata`，补上 `namespace` 默认等），调用 **memory_provider** 得到 **`MemoryCard[]`**，再走 **GardenHarvester**。
- 第二层 **`RuntimeHooks.before_reply`** 在 **OPEN** 状态下调用 Harvester（可为适配器）；**CLOSED/CLOSING** 不触发采摘。**第二层**仍会经 **BriefWriter** 对用户态 `source_memory_ids` 做规范化；**Harvest 正文**以 Harvester（含适配器）产物为主、与既有契约共存（以实现为准）。

---

## 7. 边界与安全语义

- **温室（greenhouse）**：默认不参与「积极采摘」语义；若在策略上允许进入候选集合，简报仍应避免将其作为 **`source_memory_ids` 积极侧**的稳定依据。
- **pruned / composted**：在槽位侧通常进入 **谨慎/护栏**语义；简报 **不作为**与用户事实等价的正向 `use`**；具体内容以 **`brief.py`** 与 **`bouquet.py`** 的 caution 规则为准。
- **GUARDRAIL**：只进入 **avoid / safety / nudge** 类表述，**不**作为积极事实栏的 `source_memory_ids`。
- **HarvestTrace**：用于调试与解释链；**不**进入 **`GardenBrief.model_dump()`** 的字段集合（第二层简报无 trace 大对象）。
- **Runtime adapter**：**不读库**；仅 **`memory_provider(turnContext)`** 提供卡片列表。
- **after_reply**：语义仍由第二层负责；对用户句 **`Core.observe(user_message)`** 等逻辑 **不因 Harvest 而改变**。
- **assistant_reply**：**不**自动写入长期记忆；采纳类信号等仍按第二层既有规则进入 **context/元数据**，而非 Harvest 层扩大化。

---

## 8. 当前测试覆盖

全量测试（以仓库当前状态为准）：

```bash
python -m pytest tests -q
```

```text
355 passed
```

第三层与适配器相关用例分布于 `tests/test_harvest_*.py`、`tests/test_runtime_harvest_adapter.py` 等；第二层 Runtime 行为仍由其专属测试守卫。

---

## 9. 当前限制

- **召回与排序**：纯规则与简易特征；**语义相关能力有限**，易产生漏召回与排序与用户直觉不符的情况。
- **无向量检索、无 reranker、无 LLM Lens**：当前架构 **未预留**必选的外部服务接口于本层默认值中。
- **Trace 载荷**：候选 `metadata` 可能含 **`source_memory` 快照**（来自 collector）；若未来将 trace 持久化或外传，需在 **产品线**上做 **脱敏、最小化字段、权限与保留周期**审查。
- **memory_provider**：**由集成方**实现与鉴权；本层不负责「该给用户看哪些卡片」的最终产品决策，只做确定性编排。

---

## 10. 下一层预期

后续工作可能包括：**Observability / 可追溯 UI**、**SDK 示例**、**语义检索 Harvester / 学习型 Lens / 外部 reranker** 等与第三层并行或上位的能力。  

**建议将第三层规则管道视为冻结基线**：除 **语义与安全类 bug**、或与第二层契约脱节的小幅修复外，避免在同一模块内堆砌「第二层总管」职责；更强的采摘形态宜以 **新实现满足同一协议边界**的方式演进。

---

文档版本对应仓库第三层 Harvest 封版架构说明；与具体类名、字段以 `memory_garden/harvest/` 下源码为准。
