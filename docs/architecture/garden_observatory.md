# Garden Observatory 架构说明

本文描述 Memory Garden **第四层（Garden Observatory）** 的封版架构：**只读**地把第一层～第三层与第二层 Runtime **已经产生的**结构与结果，转换为 **可序列化、可分级脱敏** 的观测物（`ObservationTrace` / `ObservationView`），便于调试、审计与系统集成时的「可追溯解释」。  
下文能力与非目标均以 **当前仓库实现** 为准；第四层 **不扩展** Seed / Court / Growth / Dream / Harvest / Runtime 的业务语义。

---

## 1. 这一层解决什么问题

Garden 系统在运行时会涉及多条子域：

- **Seed**：对话中析出、尚未扎根的候选单元  
- **Court**：开庭与判决等流程性事件  
- **Growth**：扎根、合并、修剪等记忆生命周期变化  
- **Dream**：梦境类编排结果摘要  
- **Harvest**：第三轮采摘链路（候选 → 简报等）的产物与追溯  
- **Runtime**：第二层会话、控制口令、`before_reply` / `after_reply`、tick 与反馈等回合级结果  

这些对象的 **真实逻辑** 仍由第一层～第三层与第二层 Runtime 各自实现。**Observatory 的职责**是：在 **不调用 Core、不执行 GardenRuntime、不读库** 的前提下，对上述域内已有的 **HarvestTrace、`GardenEvent` 列表、Runtime 回合快照** 做结构化映射，使开发者和上层集成可以回答：

> 「这一轮（或这一条追溯）里，**观测上**呈现了哪些阶段、链接了哪些弱引用 id、在保守视图下能看见什么？」

也就是说：第四层提供的是 **解释的载体**（跨度、事件、链接、视图分节），而不是新的「记忆裁决」或新的「采摘算法」。

---

## 2. 这一层不解决什么问题

以下能力 **不在** 当前第四层实现范围内：

- **Web UI**、浏览器端可视化或与前端框架绑定的展示层  
- **CLI** 作为观测入口（可由上层将来单独做）  
- **外部观测 SDK**（例如 OpenTelemetry exporter、专有 APM 等）的直接接入  
- **LangSmith** 等与 LLM trace 耦合的平台集成  
- **LLM / embedding / reranker / vector / search**  
- **Repository / SQLite 直连**：不在 Observatory 内读持久化存储  
- **文件或数据库落盘**：不把 `ObservationTrace` 写成文件或写入 DB  
- **云同步**：无跨设备或云端备份语义  

如需其中任一项，应在 **外层产品或独立工具**中实现；第四层只提供 **纯内存、可序列化** 的数据结构。

---

## 3. Observatory 总览

三条 **adapter + 门面** 的数据通路如下（均为 **单向、只读** 消费输入对象）：

```text
HarvestTrace
    -> HarvestObservationAdapter
        -> ObservationTrace
        -> ObservationView   (经由 view_from_trace)

list[GardenEvent]
    -> JournalObservationAdapter
        -> ObservationTrace
        -> ObservationView

Runtime 回合入参快照（GardenSession / TurnContext / before·after·tick·feedback·command_result 等）
    -> RuntimeObservationAdapter
        -> ObservationTrace
        -> ObservationView

上述三类场景的统一编排
    -> GardenObserver（薄门面：trace_* 再 view_*，不写业务规则）
```

`GardenObserver` **不发明**第四种观测语义，仅注入默认 adapter 并按域调用：`observe_harvest` / `observe_journal` / `observe_runtime_turn` 与对应的 `trace_*` 对称存在。

---

## 4. 核心对象

实现位于 `memory_garden/observatory/models.py`。简要职责如下：

| 对象 | 说明 |
|------|------|
| **ObservationTrace** | 单次观测会话根：跨度列表、事件列表、`ObservationLink`、`ObservationSourceRef`、以及 adapter 填入的 `metadata`（例如 `harvest` / `journal` / `runtime` 键）。**可能包含仅供内部或对 `INTERNAL` 视图使用的冗余信息。** |
| **ObservationSpan** | 时间上或phase上的节点（含父指针、状态、简短 `attributes`）。 |
| **ObservationEvent** | 离散观测点（名称、类别、时间与短 `attributes`）。 |
| **ObservationLink** | 有向边：`relation` + 可选端点 `ObservationSourceRef`，用于溯源图（如 brief→memory、tick→court）。 |
| **ObservationSourceRef** | 对业务 id 的 **弱引用**（seed / memory / court / dream / harvest_trace / garden_event 等字段组合）；不要求目标实体在存储中真实存在。 |
| **ObservationView** | **面向展示的脱敏视图**：`summary`、`sections`、`redaction_level`、`source_trace_id`；由各 adapter 的 `view_from_trace` **专门构造**，不是 trace 的简单子集拷贝。 |
| **ObservationKind** | 条目语义枚举（trace_root、harvest、runtime、court、growth 等），用于归类 span/event。 |
| **ObservationStatus** | 跨度级状态：`ok`、`skipped`、`unknown` 等。 |
| **RedactionLevel** | 视图档位：`PUBLIC`、`SAFE`、`INTERNAL`；由各 adapter **各自解释**PUBLIC/SAFE 与 INTERNAL 的字段差异，`GardenObserver` 仅 **透传** 该参数给 `view_from_trace`。 |

---

## 5. 核心模块

| 模块 | 文件 | 职责 |
|------|------|------|
| 模型定义 | `models.py` | 上述 Trace/View/SourceRef 等 Pydantic 模型与枚举。 |
| Harvest | `harvest.py` | `HarvestObservationAdapter`：`trace_from_harvest`、`view_from_trace`；简报与候选在 PUBLIC 视图下收敛为 id、计数、长度等。 |
| Journal | `journal.py` | `JournalObservationAdapter`：`trace_from_events`、`view_from_trace`；按 bucket 拆分 span，从 `GardenEvent` 推导链接与预览。 |
| Runtime | `runtime.py` | `RuntimeObservationAdapter`：`trace_from_turn`、`view_from_trace`；编排 runtime 子跨度与事件，`feedback_id` 等仅进 attributes/metadata，不冒充 ref 类型字段。 |
| 门面 | `observer.py` | `GardenObserver`：构造默认或可注入的三个 adapter，`observe_* = trace + view` 两步编排。 |

`memory_garden/observatory/__init__.py` 对上述类型与门面做导出，便于上层 `from memory_garden.observatory import ...`。

---

## 6. 关键流程

### 6.1 HarvestTrace 观察

1. 调用方持有第三层 **`HarvestTrace`**（已完成采摘管线，非 Observatory 触发）。  
2. `HarvestObservationAdapter.trace_from_harvest` 构建根 span「harvest_pipeline」及子步骤 span、事件、links、`source_refs`，并把摘要信息压入 `metadata["harvest"]`。  
3. `view_from_trace` 读取该 metadata，拼装 `ObservationView` 的 `sections`（pipeline、candidates、bouquet、brief、safety 等）；**PUBLIC/SAFE** 与 **INTERNAL** 分支由本模块实现。

### 6.2 GardenEvent / Journal 观察

1. 调用方提供 **内存中的** `GardenEvent` 列表（不要求经过 `GardenJournal.recent_events` 或仓储 API；Observatory **不读取**Journal 存储）。  
2. `JournalObservationAdapter.trace_from_events` 按事件类型归入 bucket span，写入事件、refs、links 与 journal 专属 `metadata`。  
3. `view_from_trace` 生成 timeline 与分桶统计；PUBLIC/SAFE 时间线不包含完整 summary 正文。

### 6.3 Runtime turn 观察

1. 调用方传入第二层 **数据类/Pydantic 快照**（`GardenSession`、`TurnContext`、`RuntimeBeforeReplyResult`、`RuntimeAfterReplyResult`、`GardenTickResult`、`RuntimeFeedback`、`RuntimeCommandResult` 等可为 `None`）。  
2. `RuntimeObservationAdapter.trace_from_turn` 生成根 span「runtime_turn」及 `command_check`、`before_reply`、`harvest_brief`、`after_reply`、`garden_tick`、`closing_feedback` 等；按实际提供的对象打点事件；简报 `source_memory_ids` 与 tick 的 court/dream id 写入 links/refs。  
3. `view_from_trace` 按 `metadata["runtime"]` 填充分节视图；全文对话仅允许在 INTERNAL 中以 **截断 excerpt** 出现。

### 6.4 GardenObserver 统一入口

- **`observe_*`**：内部顺序固定为：`对应 adapter.trace_from_*` → `同一 adapter.view_from_trace(..., redaction_level=…)`。  
- **`trace_*`**：仅返回 `ObservationTrace`，供需要自行二次处理 trace 但不立刻出视图的场景。  
- 门面 **无状态**：不缓存历史列表、不写 `last_trace` 等（当前实现不包含默认持久字段）。

### 6.5 ObservationTrace 到 ObservationView 的转换

- **必须由各 adapter 的 `view_from_trace`** 完成；语义（哪些键进入 `sections`、如何截断）**不集中**在 `GardenObserver`。  
- 转换是 **不可逆的信息折叠**：视图故意丢掉或收缩 trace 中的部分内部字段；**不要**假定 `ObservationView` 可无损还原 `ObservationTrace`。

---

## 7. Redaction 与安全语义

第四层采用的是 **适配器内置、确定性** 的规则（白名单字段 + 长度截断），**不是**通用「字段级脱敏引擎」。约定要点：

- **PUBLIC / SAFE**：不向外展示 **长正文**：如用户完整消息、助手完整回复、`source_memory` 类大对象、`GardenEvent.summary` 全文等在对应视图中应被省略或仅存统计与短信息（具体字段以各 adapter 实现为准）。  
- **INTERNAL**：允许 **更长或更细的 preview**，仍以 **截断 excerpt** 为主；**不等于**可以随意输出整条 Harvest 对象或整条对话 transcript。  
- **user_message / assistant_reply**：Runtime 适配器不得在 PUBLIC/SAFE 视图中填入完整正文；INTERNAL 仅用短 excerpt。  
- **source_memory**：Harvest 视图不拼接 `MemoryCandidate` 内含的完整底层记忆正文快照。  
- **feedback_id**：仅作为 attributes 或视图元信息中的短 id / 计数相关字段，**不**写入 `ObservationSourceRef` 的 `memory_id` 或 `event_id` 以冒充溯源类型。  
- **compost_record / greenhouse_record / pruning_record**：在 Journal 的类型映射中 **不** 强定为 `memory_id`；若无对应专有 ref 字段则 **不产生**伪造的 memory 引用。  
- **ObservationView**：定位为 **默认可对外解释的、偏安全的一侧**构造物。  
- **ObservationTrace**：可能携带 **更完整** 的结构化 metadata，体积与敏感度可能高于 View；**不应默认**对终端用户或公网 API 直接暴露 trace，除非另有导出策略与合规审查。

---

## 8. 边界与只读原则

- **不调用** `MemoryGardenCore` 或等价业务入口来「执行一步花园逻辑」。  
- **不调用** `GardenRuntime` 的 `before_reply` / `after_reply` / `handle_command` 等 **执行业务** 的路径；Observatory 只接受 **已算好的** 结果对象。  
- **不读** Repository、**不连** SQLite。  
- **不写** 文件、**不写** 数据库。  
- **不接** 外部观测 SDK。  
- **只消费** 调用方传入的已有对象；**不改变** 第一层～第三层与第二层 Runtime 的既有行为；若发现观测映射 **语义错误**，修复范围应限制在 **第四层 adapter** 内，避免扩张成新功能。

---

## 9. 当前测试覆盖

全量测试用于验证模型、三 adapter 与 `GardenObserver` 的行为与 JSON 可序列化等。封版时建议基线命令：

```bash
python -m pytest tests -q
```

记录结果（以本地环境为准）：

```text
419 passed
```

测试 **不能** 替代安全审计；通过测试只说明 **当前断言集合**下行为符合预期。

---

## 10. 当前限制

- **没有 UI**：不提供任何开箱即用的可视化或导出页面。  
- **没有持久化 trace**：不承担 trace 的版本化、归档或回放存储。  
- **没有复杂的字段级脱敏引擎**：不同 adapter 各自维护 PUBLIC/SAFE/INTERNAL 规则，粒度有限。  
- **Journal metadata 语义依赖上游**：若事件 `metadata` 中键值含义错误（例如误把非 memory id 写入 `memory_id`），观测层会 **忠实映射**，不会自动纠错。  
- **若将来要对外公开 trace**：需要单独定义 **导出策略**（裁剪字段、分级 API、留存周期等），不能把 `ObservationTrace` 默认可等价于 **`ObservationView` 的安全性**。

---

## 11. 下一层预期（非承诺）

可能出现的增量方向包括但不限于：

- 独立 **examples / SDK 文档**，展示如何从应用侧调用 `GardenObserver` 并仅对外返回 `ObservationView`。  
- 轻量 **CLI** 只做 stdin/stdout JSON，仍不耦合 Web。  
- 可视化导出（HTML/SVG/PDF）由 **外层**工具消费 `ObservationView` 完成。  
- 更强的 **`RedactionPolicy`** 或可配置字段表，仍以 **不读写业务存储** 为前提。

**短期建议**：将第四层视为 **语义冻结的稳定基线**；除非发现 observability **映射错误或脱敏遗漏**，不在本层堆砌产品功能。新增能力优先落在 **上层应用或独立二进制工具**。
