# Tutorial: First Session

This tutorial walks you through integrating Memory Garden with a simple agent. You will write a working chat loop that opens a garden session, processes user messages, and closes with structured feedback.

**Time to complete**: 15 minutes
**Prerequisites**: [Installation](../installation.md), basic Python knowledge

## Step 1: Create Your Agent

Memory Garden works with any agent that follows `ChatAgentProtocol`. For this tutorial, we'll use the built-in demo agent.

Create a file `my_first_garden.py`:

```python
from memory_garden.core import MemoryGardenCore
from memory_garden.integrations.config import BriefInjectionMode, GardenAdapterConfig
from memory_garden.integrations.sync import SyncGardenChatAdapter
from memory_garden.runtime import (
    GardenSessionManager,
    NullHarvester,
    RuntimeHooks,
    TemplateBriefWriter,
)
from memory_garden.runtime.runtime import GardenRuntime


class EchoAgent:
    \"\"\"A minimal agent that echoes back the user message.\"\"\"

    def generate_assistant_reply(self, *, user_message, session_id, extra_context=None):
        ctx_note = ""
        if extra_context:
            ctx_note = f" [context available: {len(extra_context)} chars]"
        return f"Echo: {user_message}{ctx_note}"


# Build the runtime
core = MemoryGardenCore()
manager = GardenSessionManager()
hooks = RuntimeHooks(manager, NullHarvester(), TemplateBriefWriter(), core)
runtime = GardenRuntime(core, manager, hooks)

# Create the adapter
agent = EchoAgent()
config = GardenAdapterConfig(brief_injection_mode=BriefInjectionMode.context_argument)
adapter = SyncGardenChatAdapter(agent=agent, runtime=runtime, config=config)
```

## Step 2: Open a Session

```python
result = adapter.reply("花花开")
print(f"Session opened: {result.session_id}")
print(f"Reply: {result.reply}")
```

The adapter recognizes "花花开" as a control command, opens a session, and returns the result. The command text is **never** stored as a memory.

## Step 3: Send a Message

```python
result = adapter.reply(
    "I prefer dark mode for all interfaces.",
    session_id=result.session_id,
)
print(f"Reply: {result.reply}")
print(f"Brief available: {result.garden_brief is not None}")
```

The Runtime observes your message (creates a Seed), runs a garden tick (may open Court), and prepares a Garden Brief for the next turn.

## Step 4: Send Another Message

```python
result = adapter.reply(
    "Also, please remember that I work best in the morning.",
    session_id=result.session_id,
)
print(f"Reply: {result.reply}")
print(f"Brief available: {result.garden_brief is not None}")
```

Now the Garden Brief may contain context from the previous turn, since the Harvest pipeline has a memory to draw from.

## Step 5: Close the Session

```python
result = adapter.reply("花花关", session_id=result.session_id)
print(f"Session closed. Feedback: {result.feedback is not None}")
if result.feedback:
    print(f"Feedback summary: {result.feedback.summary}")
```

The session closes with structured `RuntimeFeedback`.

## Complete Script

Put it all together:

```python
from memory_garden.core import MemoryGardenCore
from memory_garden.integrations.config import BriefInjectionMode, GardenAdapterConfig
from memory_garden.integrations.sync import SyncGardenChatAdapter
from memory_garden.runtime import (
    GardenSessionManager,
    NullHarvester,
    RuntimeHooks,
    TemplateBriefWriter,
)
from memory_garden.runtime.runtime import GardenRuntime


class EchoAgent:
    def generate_assistant_reply(self, *, user_message, session_id, extra_context=None):
        ctx_note = ""
        if extra_context:
            ctx_note = f" [ctx: {len(extra_context)} chars]"
        return f"Echo: {user_message}{ctx_note}"


core = MemoryGardenCore()
manager = GardenSessionManager()
hooks = RuntimeHooks(manager, NullHarvester(), TemplateBriefWriter(), core)
runtime = GardenRuntime(core, manager, hooks)
agent = EchoAgent()
config = GardenAdapterConfig(brief_injection_mode=BriefInjectionMode.context_argument)
adapter = SyncGardenChatAdapter(agent=agent, runtime=runtime, config=config)

# Open
r = adapter.reply("花花开")
sid = r.session_id
print(f"[1] {r.reply}")

# Chat
r = adapter.reply("I prefer dark mode.", session_id=sid)
print(f"[2] {r.reply}")

r = adapter.reply("I work best in the morning.", session_id=sid)
print(f"[3] {r.reply}")

# Close
r = adapter.reply("花花关", session_id=sid)
print(f"[4] {r.reply}")
if r.feedback:
    print(f"    Feedback: {r.feedback.summary}")
```

Run it:

```bash
python my_first_garden.py
```

## Next Steps

- Read [Concepts](../concepts.md) for the full garden metaphor.
- See [Strategy-Filtered Retrieval](../how_to/use_strategy_filtered_retrieval.md) for tuning memory retrieval.
- Browse [Examples](https://github.com/Yaoniguan-Money/memory-garden/tree/main/examples) for more integration patterns.
