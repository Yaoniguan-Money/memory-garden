# Related Work

Memory Garden exists in a landscape of memory systems for AI agents. This page explains how it relates to other approaches.

## MemGPT / Letta

MemGPT introduced the idea of managing LLM context as a virtual memory hierarchy. Memory Garden shares the insight that memory needs structure, but differs in approach: MemGPT uses LLM-based memory management, while Memory Garden uses deterministic rules for the baseline and keeps LLM integration optional and external.

## LangChain Memory

LangChain provides memory classes (`ConversationBufferMemory`, `VectorStoreRetMemory`) that store and retrieve conversation history. These are retrieval-focused: the question is "what should be in the context window?" Memory Garden adds lifecycle: "should this even become a memory?"

## Pinecone / Chroma / Vector DBs

Vector databases provide semantic search over embeddings. They answer "find similar items" efficiently. They do not answer "should this be remembered," "is this safe to show a model," or "why was this forgotten." Memory Garden addresses the lifecycle questions that vector DBs leave to the application.

## OpenAI / Anthropic "Memory" Features

Platform-level memory features (ChatGPT memory, Claude memory) are closed-source, cloud-only, and tied to specific models. Memory Garden is local-first, open-source, and model-agnostic.

## Mem0 / Zep / Letta (Hosted)

Hosted memory services provide APIs for storing and retrieving user memories. They are convenient but introduce a third party into the memory path. Memory Garden keeps all data local by default.

## promptfoo / DeepEval / OpenAI Evals

These are evaluation frameworks for LLM outputs. Memory Garden's Lab layer borrows organizational patterns from them (suite/case/assertion structure, CI report contracts) but applies them to snapshot-based regression of memory behavior, not LLM output quality.

## NeMo Guardrails / Guardrails AI

These are policy/guardrail frameworks for LLM applications. Memory Garden's Covenant layer serves a similar function (policy rules, hard constraints) but is specific to memory policy: what can be remembered, displayed, exported, or sent to a model.

## Comparison Summary

| System | Local-First | Lifecycle | Deterministic Baseline | Policy Layer | Open Source |
|---|---|---|---|---|---|
| Memory Garden | Yes | Yes | Yes | Yes | Yes |
| MemGPT/Letta | Configurable | Partial | No | No | Yes |
| LangChain Memory | Yes | No | N/A | No | Yes |
| Mem0 Cloud | No | No | No | No | Partial |
| Zep | Configurable | No | No | No | Yes |

Memory Garden is not "better" than these systems. It makes different trade-offs: lifecycle and auditability over semantic recall and cloud convenience. Choose based on which trade-offs matter for your use case.
