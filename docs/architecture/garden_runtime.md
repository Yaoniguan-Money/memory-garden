# Garden Runtime 架构说明

本文档描述 **Memory Garden 第二层（Runtime）** 的职责、对象、模块与关键流程，供后续开发者与开源读者查阅。第二层是 **编排层**：连接第一层 Garden Life Core 与外部对话节奏，**不**替代第一层领域规则，也**不**实现完整产品形态的记忆检索或生成能力。

---

## 1. 这一层解决什么问题

第一层（Garden Life Core）提供种子、记忆卡、法庭、梦境、生长动作、日志与持久化等**领域能力**，但不知道「用户何时算开了一局手账」「何时在回答前做简报、在回答后观察用户话」「何时按阈值触发审判或梦境」「如何一键收尾并给出可序列化反馈」。

第二层 **Garden Runtime** 解决的是：把上述能力**接入真实多轮对话节奏**——通过会话状态、控制口令、编排钩子与策略，在正确时机调用第一层 API，并约束用户可见反馈与记忆写入边界，使外部对话系统可以用**少量 Python API** 驱动同一套 Core，而不必在每个适配层重复拼凑语义。

---

## 2. 这一层不解决什么问题

以下能力**明确不属于**第二层职责范围；若在本仓库其他路径出现，应视为上层或独立组件，而非第二层交付内容：

- **CLI / Web UI**：不提供终端或浏览器界面。
- **真实 Harvester**：不负责从大规模记忆库中检索、排序、抽取「真正采摘」逻辑。
- **复杂 Garden Brief**：不承诺生产级简报生成或长上下文拼装。
- **LLM / 向量检索 / 通用搜索**：不在 Runtime 内调用大模型或向量数据库。
- **云同步 / 多租户 SaaS**：不提供账号体系、跨设备同步或多用户隔离运行时。

第二层默认使用占位 Harvester / BriefWriter，仅保证**编排钩子可替换**，不把占位实现宣传为「开箱即用」的智能采摘。

---

## 3. Runtime 总览

典型编排链路可概括为：

| 步骤 | 行为 |
|------|------|
| **花花开** | 解析为控制口令 → **打开会话**（`open_session`），进入 `OPEN`。 |
| **before_reply** | 若会话 `OPEN`：走 Harvester → BriefWriter，得到 **GardenBrief**；不写入用户话为记忆。 |
| **after_reply** | 若会话 `OPEN`：对 **用户消息** 调用 `Core.observe(user_message)`，再执行 **garden_tick**（按策略与触发器决定是否调用 `open_court` / `dream`）。 |
| **garden_tick** | 仅根据 `RuntimePolicy`、`TriggerEngine` 与当前会话状态，**在阈值与开关满足时**调用第一层的 `open_court()` / `dream()`；不直接执行 plant / compost 等 Growth 动作。 |
| **花花关** | 解析为控制口令 → **关闭会话**（`close_session`），状态经 `CLOSING` 至 `CLOSED`，并产生 **RuntimeFeedback**（收尾反馈从真实元数据与 tick 摘要统计，不调用 LLM）。 |

普通用户消息在**非**控制口令时，不经过「花花开/花花关」短路，而由集成方在判定非口令后调用 `before_reply` / `after_reply`。

---

## 4. 核心对象

| 对象 | 作用 |
|------|------|
| **RuntimeState** | 会话生命周期枚举：`closed` / `open` / `closing`。 |
| **RuntimePolicy** | 开关与阈值：自动开庭/梦境、回合与 pending 种子阈值、反馈模式等；**不**包含业务规则重写。 |
| **GardenSession** | 当前编排会话快照：`session_id`、状态、开闭时间、`turn_count`、`metadata`（含 tick 与收尾反馈可追溯字段）。 |
| **TurnContext** | 单轮编排上下文：会话 id、回合序号、`user_message`，可选 `assistant_reply` 字段用于编排元数据（observe 主文本仍是用户句）。 |
| **GardenBrief** | before_reply 阶段输出的简报结构（占位实现下字段为模板或安全默认值）。 |
| **TriggerDecision** | `TriggerEngine.evaluate` 输出：是否建议开庭/做梦及理由列表。 |
| **GardenTickResult** | 单次 `garden_tick` 的结果摘要：开庭案件 id、梦境记录 id、跳过原因等。 |
| **RuntimeFeedback** | 会话收尾时可序列化的结构化反馈（摘要与要点及计数类 metadata）。 |
| **RuntimeCommandResult** | `handle_command` 对「花花开/花花关」的编排结果：是否处理、命令类型、会话状态、关闭时的 `RuntimeFeedback` 等。 |

---

## 5. 核心模块

| 模块 | 职责 |
|------|------|
| **commands.py** | 解析运行时控制口令（如「花花开」「花花关」及限定英文别名）；**整句精确匹配**，子串不算命中；不访问 Core。 |
| **session_manager.py** | `GardenSession` 内存态生命周期：`open_session`、`close_session`、`increment_turn_count`、tick 摘要写入 `metadata` 等；不直接调用 Core。 |
| **harvest.py** | `NullHarvester` / `TemplateBriefWriter` 等**占位**实现，满足协议、无检索与无 LLM。 |
| **hooks.py** | `before_reply` / `after_reply`：OPEN 时 before 做简报，after 做 `observe` 与 `garden_tick`；CLOSED 时短路。 |
| **triggers.py** | `TriggerEngine`：结合 `RuntimePolicy`、会话与 `TurnContext` 产出 `TriggerDecision`（含 pending 阈值、回合阈值、强信号等规则）。 |
| **tick.py** | `garden_tick`：仅在 OPEN 且策略允许时调用 `Core.open_court()` / `Core.dream()`，并回写会话 metadata；不执行 Growth Actions。 |
| **feedback.py** | `RuntimeFeedbackBuilder`：基于会话 metadata、tick 结果与可选事件样本生成 `RuntimeFeedback`；反馈模式由 `RuntimePolicy.feedback_mode` 控制。 |
| **runtime.py** | `GardenRuntime`：对外最小编排 API（如 `handle_command`、`open_session`、`close_session`、`before_reply`、`after_reply`、`current_session`），组合上述模块。 |

---

## 6. 关键流程

### 花花开

对输入做 `parse_runtime_command`；命中 OPEN 口令则调用 `open_session`，**不**调用 `Core.observe`，**不**生成 Seed。集成方应优先于普通 `before_reply` 处理该路径。

### CLOSED 普通消息

`before_reply` 无简报（或带跳过原因）；`after_reply` **不**调用 `observe`，不跑 `garden_tick`；用户可见反馈默认无。

### OPEN before_reply

校验 `session_id` 与当前会话一致；构造 `TurnContext`（ assistant 不参与 observe）；Harvester → BriefWriter → **GardenBrief**。**此阶段不写入记忆。**

### OPEN after_reply

仅将 **user_message** 作为主文本调用 `Core.observe`；`assistant_reply` 仅在采纳/纠正等信号下进入 context；随后 `increment_turn_count` 并 **garden_tick**。

### garden_tick

若会话非 OPEN 则 no-op；否则 `TriggerEngine.evaluate`，按策略决定调用 `open_court` / `dream`；结果 id 与原因写入会话 `metadata`。**不**直接调用 plant、compost、greenhouse、prune、forget、merge。

### 花花关

命中关闭口令则走 `close_session`（含收尾反馈构建与状态迁移），**不**经过 `after_reply`，**不** `observe`。

### closing feedback

通过 `RuntimeFeedbackBuilder.build_closing_feedback` 生成 `RuntimeFeedback`，再交由 `session_manager.close_session` 写入反馈历史等 metadata。默认策略下**普通轮次不产生**用户可见反馈；收尾反馈仅在关闭路径集中给出。

---

## 7. 边界与安全语义

- **命令不进入 Seed**：控制口令只改变会话状态，不把口令文本当作用户偏好写入种子。
- **before_reply 不写记忆**：不在此阶段调用 `observe` 或等价写入路径。
- **after_reply 只以 user_message 为 observe 主文本**：与第一层契约一致。
- **assistant_reply 不自动成为用户记忆**：不得单独作为 observe 输入；仅在明确采纳/纠正等语义下进入种子 context。
- **tick 不直接执行 Growth Actions**：Growth 由第一层在法庭判决等流程内触发；Runtime 只触发开庭/梦境入口API。
- **普通轮次默认不反馈**：默认 `feedback_mode` 下，常规 after_reply 的 `user_visible_feedback` 为 `None`。
- **close_session 才集中返回 RuntimeFeedback**：关闭时生成可序列化收尾反馈；重复关闭幂等，不重复伪造生命周期副作用。

---

## 8. 当前测试覆盖

全量测试命令：

```bash
python -m pytest tests -q
```

当前结果示例：**247 passed**（具体耗时随机器变化）。测试覆盖 Runtime、会话、命令解析、钩子、tick、触发器、反馈与端到端编排等；**不**等同于生产环境审计。

---

## 9. 当前限制

- **NullHarvester / TemplateBriefWriter** 仍为占位，**无真实采摘**能力。
- **无 LLM**、**无 search/vector** pipeline。
- **recent_events** 等仓储级事件样本**不是**严格按 Runtime 会话划界；收尾文案中应避免将其解释为「本会话专属事实」。
- **Runtime 会话状态**为进程内编排模型，**不**承诺跨进程持久化与会话恢复；持久化与会话迁移应由上层或后续层设计。

---

## 10. 下一层预期

后续可以在**独立层或适配模块**中引入：真实 Harvester、更丰富 Garden Brief、可视化、SDK、CLI/Web 等。第二层 **Garden Runtime 建议封版冻结**：以语义清晰与边界稳定为主，**仅在发现编排语义 bug 或契约不一致时做小修复**，避免在第二层堆叠产品特性。

---

*文档版本与仓库第二层实现对齐；若代码变更，请同步更新本节与关键流程描述。*
