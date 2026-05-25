# Comparison: Memory Garden vs Other AI Memory Systems

This is an honest feature comparison.  Empty cells mean "unverified — check the
project's own documentation."  We do not denigrate other projects; every design
choice has tradeoffs.

## Core Philosophy

| | Memory Garden | Mem0 | Letta/MemGPT | LangChain Memory | LlamaIndex Memory |
|---|---|---|---|---|---|
| **Approach** | Lifecycle (Seed→Court→Dream→Harvest) | Embed→Store→Retrieve | OS-like memory management | Key-value + chat history | Chat buffer + token management |
| **Memory model** | Structured cards with lifecycle state | Flat embeddings | Blocks with read/write/edit | Dict + message list | ChatMessageBuffer |
| **Local-first** | ✅ Default, zero network | ❌ Cloud API required | ⚠️ Can self-host | ✅ | ✅ |
| **Offline capable** | ✅ Full functionality offline | ❌ | ⚠️ Server required | ✅ | ✅ |
| **Default deps** | pydantic + PyYAML | openai + chromadb + ... | Server + DB | langchain-core | llama-index-core |

## Memory Lifecycle

| | Memory Garden | Mem0 | Letta/MemGPT | LangChain | LlamaIndex |
|---|---|---|---|---|---|
| **Judgment (should this be a memory?)** | ✅ 27-rule Court | ❌ Everything is embedded | ❌ | ❌ | ❌ |
| **Growth (plant/compost/greenhouse)** | ✅ 6 actions | ❌ | ❌ | ❌ | ❌ |
| **Dream (batch review/clustering)** | ✅ Rule-based + optional LLM | ❌ | ❌ | ❌ | ❌ |
| **Harvest (retrieval for context)** | ✅ FTS5 + embedding + optional LLM rerank | ✅ Embedding similarity | ✅ | ⚠️ Simple | ✅ |
| **Human-in-the-loop proposal review** | ✅ Proposal workflow | ❌ | ❌ | ❌ | ❌ |

## Safety & Audit

| | Memory Garden | Mem0 | Letta/MemGPT | LangChain | LlamaIndex |
|---|---|---|---|---|---|
| **Forget with proof** | ✅ 6-surface verification | ❌ | ⚠️ Delete only | ❌ | ❌ |
| **Cascade forget** | ✅ opt-in | ❌ | ❌ | ❌ | ❌ |
| **Greenhouse (sensitive isolation)** | ✅ | ❌ | ❌ | ❌ | ❌ |
| **Policy engine with hard baselines** | ✅ 7 non-overridable rules | ❌ | ❌ | ❌ | ❌ |
| **Audit trace (why was this harvested?)** | ✅ HarvestTrace | ❌ | ❌ | ❌ | ❌ |
| **Redaction (PUBLIC/SAFE/INTERNAL)** | ✅ 3-tier | ❌ | ❌ | ❌ | ❌ |

## Integration

| | Memory Garden | Mem0 | Letta/MemGPT | LangChain | LlamaIndex |
|---|---|---|---|---|---|
| **OpenAI SDK** | ✅ GardenOpenAI | ✅ Native | ⚠️ | ✅ | ✅ |
| **Anthropic SDK** | ✅ GardenAnthropic | ❌ | ❌ | ⚠️ | ⚠️ |
| **LangChain** | ✅ BaseMemory | ⚠️ | ❌ | ✅ Native | ✅ |
| **LlamaIndex** | ✅ ChatMemory | ❌ | ❌ | ❌ | ✅ Native |
| **FastAPI** | ✅ Depends helper | ❌ | ❌ | ❌ | ❌ |
| **LangGraph** | ✅ StateGraph node | ❌ | ❌ | ✅ Native | ❌ |
| **Claude Code** | ✅ Hook adapter | ❌ | ❌ | ❌ | ❌ |
| **Codex CLI** | ✅ System prompt | ❌ | ❌ | ❌ | ❌ |
| **Auto-memory (one line)** | ✅ AutoMemory | ⚠️ add() | ❌ | ⚠️ | ⚠️ |

## Developer Experience

| | Memory Garden | Mem0 | Letta/MemGPT | LangChain | LlamaIndex |
|---|---|---|---|---|---|
| **CLI** | ✅ 26 commands | ⚠️ Limited | ⚠️ Server CLI | ❌ | ❌ |
| **Python SDK** | ✅ MemoryGarden.local() | ✅ | ⚠️ REST API | ✅ | ✅ |
| **Drop-in for any framework** | ✅ GardenSkill | ❌ | ❌ | ❌ | ❌ |
| **Zero-config demo** | ✅ `memory-garden demo` | ❌ | ❌ | ❌ | ❌ |
| **Observatory (HTML/MD/JSON)** | ✅ Terminal + HTML + Markdown | ❌ | ❌ | ❌ | ❌ |
| **Strategy profiles** | ✅ Layer + Scope + Maturity | ❌ | ❌ | ❌ | ❌ |

## When to Use Each

- **Memory Garden**: You want a local-first memory layer with judgment, lifecycle,
  and audit. You care about forget proof and policy. You want to integrate into
  your own agent without cloud dependencies.

- **Mem0**: You need a quick cloud-based memory API for a production app and
  don't mind the OpenAI dependency. Simpler mental model, less control.

- **Letta/MemGPT**: You're building stateful agents that need OS-like memory
  management with self-editing capabilities. You're comfortable running a server.

- **LangChain Memory**: You're already in the LangChain ecosystem and want the
  simplest possible memory for a chain.

- **LlamaIndex Memory**: You're already in the LlamaIndex ecosystem and want
  chat buffer memory for your index queries.

## Limitations (honest)

Memory Garden does not have:
- Cloud hosting or managed service
- Multi-user / multi-tenant isolation
- A web UI
- Built-in encryption at rest
- PyPI package (yet — coming soon)

These are design choices, not bugs.  Memory Garden is a library, not a service.
