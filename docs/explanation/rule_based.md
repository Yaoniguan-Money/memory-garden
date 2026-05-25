# Why Rule-Based, Not LLM-Based?

Memory Garden uses deterministic rules for Court judgment, Harvest retrieval, and Dream cycles. This is a deliberate choice, not a temporary limitation.

## Rationale

### Auditability

Rule-based decisions are fully traceable. Given the same inputs, you get the same outputs. You can debug why a seed was composted by reading the rule that fired. With an LLM judge, the reasoning is a generated text that may or may not reflect actual decision factors.

### Determinism

Tests can assert exact behavior. A CI pipeline can verify that "negative self-descriptions are never planted as identity memories" by checking a specific rule outcome. You cannot reliably assert this against an LLM.

### Zero Cost and Zero Latency

Rules run in microseconds with no API calls. No rate limits, no billing, no network dependency.

### Privacy

User text never leaves the local process for memory judgment. With LLM-based judgment, every seed observation would require sending user content to a third-party model.

## When You Might Want an LLM

Rule-based judgment has inherent limitations:

- **Semantic understanding is shallow**: Rules match keywords and patterns, not meaning. A subtle preference expressed indirectly may be missed.
- **Edge cases abound**: The heuristic rules will misclassify some inputs.
- **No cross-cultural or multilingual nuance**: Rules are currently designed for Chinese and English with simple patterns.

These are real trade-offs. The architecture allows for pluggable LLM-based components (a `LLMCourtEngine` implementing the same interface), but the baseline remains rule-based to preserve auditability, determinism, and privacy for users who need those properties.
