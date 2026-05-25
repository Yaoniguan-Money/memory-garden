# Integration Layer 架构说明

本文描述 Memory Garden **第五层（SDK / Examples / Integration Layer）** 的封版架构：在 **第一层～第四层** 已冻结的前提下，为 **外部宿主**（自研 Agent、企业内部 chat loop 等）提供 **协议化的接入面**，在不改写 Core / Runtime 语义的情况下，串联 **口令短路、简报、宿主回复、`after_reply` 观察** 与 **结构化返回**。  
下文能力与非目标均以 **当前仓库实现** 为准。

---

## 1. 这一层解决什么问题

前四层描述了「花园本体」：**Core、Runtime、Harvest、Observatory** 在 Python 项目中可单独使用。但绝大多数集成场景需要：**把同一套语义嵌进宿主对话循环**，并避免每个调用方自己去拼 `handle_command` → `before_reply` → `after_reply` 的顺序与边界。

第五层回答的是：**外部开发者如何通过稳定契约**，把 **`GardenRuntime` 与自建 Chat Agent** 接在一起，并得到 **可序列化、可预测的** `IntegrationResult`，而不是仅能 import 底层模块手写编排。

要点包括：

- **协议化宿主 Agent**：同步 **`ChatAgentProtocol`**、异步 **`AsyncChatAgentProtocol`**，不绑定具体模型厂商。
- **薄适配器**：**`SyncGardenChatAdapter`** / **`AsyncGardenChatAdapter`** 只做编排，**不** 充当新的 Runtime。
- **配置与简报注入**：**`GardenAdapterConfig`** + **`BriefInjectionMode`**，控制简报如何进入 `extra_context`。
- **可重复学习的入口**：**`examples/sync_chat_agent.py`** 与 **`docs/integration_quickstart.md`**。

---

## 2. 这一层不解决什么问题

以下能力 **不在当前第五层实现范围内**：

- **CLI 产品**、**FastAPI / Web** 或可对外暴露的 HTTP 服务  
- **真实 LLM provider** 接入、或与 OpenAI / Anthropic / DeepSeek 等耦合的 SDK 封装  
- **API key 管理**、密钥轮转、配额治理  
- **embedding**、**reranker**、**向量索引**、广义 **外部 search**  
- **新增 Repository API**、**SQLite schema 变更**、集成层直连数据库做业务  
- **云同步**、跨设备会话漂移管理  
- **新的 Runtime 语义**（不改变「谁observe、谁先短路」等第二层既定规则）

若需要上述能力，应在 **应用层** 或 **独立仓库/工具** 中实现。

---

## 3. Integration Layer 总览

组件关系可按「契约 → 适配器 → 输出」阅读：

```text
ChatAgentProtocol 或 AsyncChatAgentProtocol   （宿主实现）
           +
GardenRuntime                                （第二层，由集成方构造）
           +
GardenAdapterConfig（可选）
           │
           ▼
SyncGardenChatAdapter.reply(...)   或   await AsyncGardenChatAdapter.reply(...)
           │
           ▼
IntegrationResult（+ 可选 IntegrationDebugInfo）
```

- **学习与文档**：  
  - **`examples/sync_chat_agent.py`**：`RuleBasedDemoAgent` + 最小 Runtime 栈，**不按 import 自动跑**。  
  - **`docs/integration_quickstart.md`**：边界、顺序、简报模式、异步说明。

---

## 4. 核心对象

实现主要位于 **`memory_garden/integrations/`**。

| 对象 | 职责 |
|------|------|
| **GardenAdapterConfig** | **无 API key 字段**；默认 **local-first**（如 `prefer_local_runtime=True`、`enable_remote_model_provider=False`）；`debug` 默认 **False**。 |
| **BriefInjectionMode** | 简报进入 **`extra_context`** 的方式：**`none`**、**`context_argument`**、**`system_prefix`**、**`developer_message`**、**`metadata`**。 |
| **AgentReplyResult** | 宿主可选用：正文 **`content`** + 可 JSON 化的 **`metadata`**。 |
| **IntegrationResult** | 单轮对外结果：**`reply`**、可选 **`garden_brief`**、**`feedback`**、**`trace_id`**、**`session_id`**、**`debug`**、**`events`**。 |
| **IntegrationDebugInfo** | **`debug=True`** 时的短诊断块；不含长正文与 trace 大对象。 |
| **IntegrationError** | 集成层异常基类。 |
| **IntegrationAgentError** | 宿主 **agent** 抛错时的包装类型。 |
| **IntegrationRuntimeError** | **GardenRuntime / Hooks** 调用失败时的包装类型。 |

其余错误分类（如 **`AgentProtocolError`**、**`BriefInjectionError`**、**`AdapterRuntimeError`**）见包内 **`errors.py`**，供扩展使用。

---

## 5. 同步接入流程

**`SyncGardenChatAdapter.reply(user_message, session_id=..., metadata=...)`** 顺序如下：

1. **`runtime.handle_command(user_message, session_id=...)`**  
   - 若 **命中花花开/花花关**：直接组装 **`IntegrationResult`**（见第 7 节），**结束**。  
2. **非命令**：**`runtime.before_reply(session_id, user_message, metadata=...)`**，得到 **`GardenBrief` 或 None** 与跳过信息。  
3. **Brief injection**：按 **`GardenAdapterConfig.brief_injection_mode`** 生成 **`extra_context`**（与异步版共用实现）。  
4. **`agent.generate_assistant_reply(...)`**（同步），返回 **`str | AgentReplyResult`**，归一为正文 + 可选 **metadata→events**。  
5. **`runtime.after_reply(session_id, user_message, assistant_reply, metadata=...)`**。  
6. 组装 **`IntegrationResult`**。

**Runtime** 保持 **第二层既有语义**：**不以 assistant 句单独作主 observe 输入**（见第 11 节）。

---

## 6. 异步接入流程

**`AsyncGardenChatAdapter.reply(...)`** 与同步版 **控制流一致**：同样先 **`handle_command`**，非命令再走 **`before_reply` → brief → agent → `after_reply`**。

唯一差异：**`await agent.generate_assistant_reply(...)`**。  
**不** 为迁就 async 而修改 **`GardenRuntime`**：在协程内 **同步调用** **`handle_command` / `before_reply` / `after_reply`**；第一版 **不** 使用 **`asyncio.to_thread`** 等线程隔离。

---

## 7. 命令短路语义

- **花花开 / 花花关** 命中时：仅 **`handle_command`** 生效。  
- **不调用**宿主 **agent**（同步或异步均未进入 `generate_assistant_reply`）。  
- **不调用** **`before_reply`**、**不调用** **`after_reply`**。  
- **不进入 Seed**：与第二层「口令路径不占 observe」的既定行为一致。

---

## 8. GardenBrief 注入语义

简报来自 **`runtime.before_reply`** 产出的 **`GardenBrief`**（或 **None**）。

| 模式 | 行为概要 |
|------|-----------|
| **none** | **不注入**：`extra_context` 视为 **无简报**（即使存在 brief）。 |
| **context_argument** | 将简报字段压成 **短文本块**（有长度裁剪）。 |
| **system_prefix / developer_message** | 同上文本块外加 **前缀标签**，便于宿主区分通道；仍通过 **`extra_context`** 传递。 |
| **metadata** | 仅 **溯源 id / 字段长度等 JSON**，不把简报全文伪装成向量检索载荷。 |

**不注入**：**HarvestTrace**、**ObservationTrace** 整场结构，以及 **MemoryCard 正文级** 快照。简报字段本身为第二层编排用短字段，不等于记忆库全文导入。

---

## 9. Debug 与错误处理

- **`GardenAdapterConfig.debug`** 默认为 **False**：**`IntegrationResult.debug`** 通常为 **`None`**。  
- **`debug=True`**：仅填充 **短键值式** **`IntegrationDebugInfo.notes`** 等（如是否命令处理、简报溯源数量、会话状态）；**不包含** 完整 **`user_message` / assistant 回复**；**不包含** Harvest/Observation **大对象**。  
- **Agent 异常** → **`IntegrationAgentError`**；**Runtime 异常** → **`IntegrationRuntimeError`**。  
- **空字符串助手回复**：在归一化阶段视为错误，**不** 伪装成功。

---

## 10. Quickstart 示例

- **`examples/sync_chat_agent.py`** 使用 **`RuleBasedDemoAgent`**：**不接**真实模型，**不要求** API key，**不涉及**网络。  
- **`MemoryGardenCore()`** 默认 **`SQLiteGardenRepository(":memory:")`**，正常示例路径 **不写**工作区 **`garden.db`**。  
- 仅 **`if __name__ == "__main__": main()`** 时打印短摘要；**import 模块不会自动执行**主流程。

---

## 11. 边界与安全语义

- **`assistant_reply`**：**不单独**作为 **`Core.observe`** 的主输入语义由 **第二层 `RuntimeHooks.after_reply`** 保证；集成层 **不改写**该行文。  
- **`IntegrationResult.events`**：可能合并宿主 **`AgentReplyResult.metadata`** 中的键值（有数量裁剪）；若宿主填入 **大二进制或巨型 JSON**，可能影响体积与合规——**应由宿主约束 payload**。  
- **Async wrapper**：当前 **不做线程隔离**，长耗时同步 Runtime 调用会占用 **同一事件循环**；重负载场景需在 **外层**拆分或未来将 Runtime 分段异步化（**非本层当前承诺**）。  
- **`metadata` 参数**：集成层 **不刻意修改**传入 dict 引用；若需防御性浅拷贝 **hardening**，可作为后续小改进，不改变业务语义。

---

## 12. 当前测试覆盖

建议基线：

```bash
python -m pytest tests -q
```

封版时记录：

```text
471 passed in 1.14s
```

（耗时因机器而异；**471** 表示与 Integration 相关的契约、同步、异步与示例文档测试均在该基线下通过。）

---

## 13. 当前限制

- **无** 独立 CLI / Web 产品形态。  
- **无** 内置真实模型 Provider 或密钥管理。  
- **无** 外部向量检索编排。  
- **无** 跨进程 / 分布式会话一致性协议。  
- **无** 可插拔 「provider 插件系统」——仅有 **协议接口**供宿主自备实现。

---

## 14. 下一层预期（非承诺）

可能出现的增量方向包括但不限于：更完整的 **examples**、实验性 **Garden Lab**、**可选**薄 CLI（仅stdin/stdout JSON）、或 **独立于核心包** 的 provider 样例。**建议**将第五层本身视为 **语义冻结的基线**：除非发现 Integration 编排 **映射错误**或与 Runtime **不一致**，否则避免在 **`memory_garden.integrations`** 内堆叠产品功能。
