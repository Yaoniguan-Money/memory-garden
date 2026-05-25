# Memory Garden 集成 Quickstart（同步 Chat）

本文说明如何用 **`SyncGardenChatAdapter`** 把第二层 **`GardenRuntime`** 与自有 **同步 Chat Agent** 串成单轮 **`IntegrationResult`**。配套代码见仓库根目录 **`examples/sync_chat_agent.py`**。

## 重要边界（请先读）

- **不接真实 LLM**：示例使用 **`RuleBasedDemoAgent`**，仅做规则回显；**不包含** OpenAI / Anthropic / DeepSeek 等调用，也**不需要** API key。
- **当前第五层范围**：内置 **同步**（`SyncGardenChatAdapter`）与 **异步**（`AsyncGardenChatAdapter`，见下文）两种包装器；**仍不包含** CLI 产品、FastAPI / Web、外部观测 SDK、embedding / reranker / 向量检索。
- **debug 默认关闭**：`GardenAdapterConfig.debug` 默认为 `False`，`IntegrationResult.debug` 通常为 `None`。
- **数据与文件**：示例使用 `MemoryGardenCore()` 默认的 **内存** 仓储（`:memory:`），**不会**在仓库里创建 `.memory_garden` 或 `garden.db` 等工作目录文件（除非你自行传入落盘 `GardenRepository`）。

## 最小对象怎么搭

与测试一致的最小栈一般为：

1. **`MemoryGardenCore()`** — 进程内核心（默认内存库）。
2. **`GardenSessionManager()`** + **`RuntimeHooks(..., NullHarvester(), TemplateBriefWriter(), core)`**。
3. **`GardenRuntime(core, manager, hooks)`**。
4. 实现 **`ChatAgentProtocol`** 的类（示例为 **`RuleBasedDemoAgent`**）。
5. **`SyncGardenChatAdapter(agent=..., runtime=..., config=...)`**。

快捷函数：**`build_demo_adapter()`** 或 **`build_demo_stack()`**（后者同时返回假 Agent，便于测试/学习）。

## 接入自己的 Agent

实现 **`ChatAgentProtocol`**：提供同步方法

```text
def generate_assistant_reply(
    self,
    *,
    user_message: str,
    session_id: str,
    extra_context: str | None = None,
) -> str | AgentReplyResult
```

- 返回 **`str`** 或 **`AgentReplyResult`** 均可；包装器会统一归一化。
- **不要**在本方法里直连本项目的 **Repository / SQLite**（除非你明确清楚边界）；记忆观察由 Runtime 的 **`after_reply`** 按第二层语义完成。

## 花花开 / 花花关（命令短路）

- 用户整句命中 **花花开 / 花花关** 时：走 **`handle_command`**，**不**调用 **`before_reply`**、**不**调用宿主 **agent**、**不**调用 **`after_reply`**。
- **花花开**：打开会话；**花花关**：关闭并可能附带 **`RuntimeFeedback`**。
- 普通聊天句须先 **花花开** 进入 **OPEN**，否则 **`before_reply`** 按第二层语义多为 no-op（无简报 / 不 observe）。

## before_reply / after_reply 顺序（非命令路径）

对**非**控制口令的一轮，顺序固定为：

1. **`before_reply(session_id, user_message, metadata=...)`** — 可能得到 **`GardenBrief`**（OPEN + Harvester 路径）。
2. 按配置把简报注入 **`extra_context`**，调用 **`generate_assistant_reply`**。
3. **`after_reply(session_id, user_message, assistant_reply, metadata=...)`** — **只以用户句为主观察对象**；助手答句不单独作为 observe 主文本（与第二层文档一致）。

## GardenBrief 注入模式

由 **`GardenAdapterConfig.brief_injection_mode`**（**`BriefInjectionMode`**）控制，例如：

- **`none`**：不注入。
- **`context_argument`**：简报压缩块进入 **`extra_context`**。
- **`system_prefix` / `developer_message`**：在 `extra_context` 中加前缀区分角色通道（仍通过同一参数传递，由你的 Agent 自行解释）。
- **`metadata`**：仅长度与 id 等元信息 JSON，**不**塞 HarvestTrace / ObservationTrace / MemoryCard 全文。

## 运行示例

在仓库根目录：

```bash
python examples/sync_chat_agent.py
```

或在代码中：

```python
from examples.sync_chat_agent import run_demo

results = run_demo()
```

## 异步包装器（`AsyncGardenChatAdapter`）

适用于 **`async def`** 宿主模型或 IO 模型的场景。实现 **`AsyncChatAgentProtocol`**（`generate_assistant_reply` 为 **async**，返回 `str | AgentReplyResult`），并构造：

```text
AsyncGardenChatAdapter(agent=..., runtime=..., config=...)
```

在协程内调用 **`await adapter.reply(user_message, session_id=..., metadata=...)`**。

- **语义**与 **`SyncGardenChatAdapter.reply`** 对齐：花花开 / 花花关短路、**`before_reply` → agent → `after_reply`**、简报 **`extra_context`** 使用与同步版相同实现（复用 **`BriefInjectionMode`**）。
- **Runtime** 仍为同步 API：**在 async 方法内直接调用** `handle_command` / `before_reply` / `after_reply`，**不**使用线程池或 **`asyncio.to_thread`**（第一版保持确定性与简单）。

## 与观测层（第四层）的关系

Quickstart **不依赖**你必须启用 Observatory；若需结构化观测，可在集成层之外自行调用 **`GardenObserver`**，本文不展开。

## 下一步（非本仓库承诺）

你可自行增加：HTTP 服务、真实 LLM 适配、持久化仓储与更强 redaction；**当前官方第五层基线**提供同步与异步 Chat 适配器及契约，避免在核心包内绑定外部云厂商。
