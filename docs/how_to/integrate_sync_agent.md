# How to Integrate with a Sync Agent

This guide shows how to connect your own synchronous chat agent to Memory Garden.

## Prerequisites

- Memory Garden installed (`pip install -e .`)
- Your agent implements a method matching `ChatAgentProtocol`

## 1. Implement ChatAgentProtocol

Your agent must have this method:

```python
def generate_assistant_reply(
    self,
    *,
    user_message: str,
    session_id: str,
    extra_context: str | None = None,
) -> str:
    ...
```

The method receives:
- `user_message` — the user's latest message (never a control command)
- `session_id` — the current garden session ID
- `extra_context` — the Garden Brief (if `BriefInjectionMode` is not `none`)

It returns the assistant's reply as a string.

## 2. Build the Runtime

```python
from memory_garden.core import MemoryGardenCore
from memory_garden.runtime import (
    GardenSessionManager,
    NullHarvester,
    RuntimeHooks,
    TemplateBriefWriter,
)
from memory_garden.runtime.runtime import GardenRuntime

core = MemoryGardenCore()
manager = GardenSessionManager()
hooks = RuntimeHooks(manager, NullHarvester(), TemplateBriefWriter(), core)
runtime = GardenRuntime(core, manager, hooks)
```

## 3. Configure and Create the Adapter

```python
from memory_garden.integrations.config import BriefInjectionMode, GardenAdapterConfig
from memory_garden.integrations.sync import SyncGardenChatAdapter

config = GardenAdapterConfig(
    brief_injection_mode=BriefInjectionMode.context_argument,
    debug=False,
)
adapter = SyncGardenChatAdapter(
    agent=your_agent,
    runtime=runtime,
    config=config,
)
```

## 4. Drive the Conversation

```python
# Open session
r = adapter.reply("花花开")
session_id = r.session_id

# Chat loop
while True:
    user_input = input("You: ")
    if user_input == "花花关":
        r = adapter.reply("花花关", session_id=session_id)
        print(f"Agent: {r.reply}")
        if r.feedback:
            print(f"Session feedback: {r.feedback.summary}")
        break
    r = adapter.reply(user_input, session_id=session_id)
    print(f"Agent: {r.reply}")
```

## What Happens Under the Hood

For each non-command message, the adapter:

1. Calls `runtime.before_reply()` — runs the Harvest pipeline, produces a Garden Brief
2. Injects the brief into `extra_context` (per `BriefInjectionMode`)
3. Calls `your_agent.generate_assistant_reply()`
4. Calls `runtime.after_reply()` — observes the user message, runs garden_tick

Control commands ("花花开", "花花关") short-circuit: they never reach your agent and are never stored as memories.

## Next

- [Control Brief Injection](control_brief_injection.md)
- [Integrate with an Async Agent](integrate_async_agent.md)
