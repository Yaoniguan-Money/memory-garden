# How to Integrate with an Async Agent

This guide covers async/await integration patterns.

## Prerequisites

- Memory Garden installed (`pip install -e .`)
- Your agent works with `async def`

## 1. Implement AsyncChatAgentProtocol

```python
class MyAsyncAgent:
    async def generate_assistant_reply(
        self,
        *,
        user_message: str,
        session_id: str,
        extra_context: str | None = None,
    ) -> str:
        # Your async logic here
        ...
```

## 2. Build the Runtime

Same as the sync case — the Runtime is synchronous and called directly from async methods:

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

## 3. Create the Async Adapter

```python
from memory_garden.integrations.async_adapter import AsyncGardenChatAdapter
from memory_garden.integrations.config import BriefInjectionMode, GardenAdapterConfig

config = GardenAdapterConfig(
    brief_injection_mode=BriefInjectionMode.context_argument,
)
adapter = AsyncGardenChatAdapter(
    agent=your_async_agent,
    runtime=runtime,
    config=config,
)
```

## 4. Use in an Async Loop

```python
import asyncio

async def main():
    r = await adapter.reply("花花开")
    session_id = r.session_id

    r = await adapter.reply("I prefer dark mode.", session_id=session_id)
    print(r.reply)

    r = await adapter.reply("花花关", session_id=session_id)
    print(r.feedback.summary if r.feedback else "no feedback")

asyncio.run(main())
```

## Design Note

The async adapter calls Runtime methods synchronously (no `asyncio.to_thread`). This keeps the first version simple and deterministic. If your use case requires offloading Runtime work, wrap it at the application level.
