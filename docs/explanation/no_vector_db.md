# Why No Vector Database?

Many memory systems use vector databases for retrieval. Memory Garden's baseline does not.

## Rationale

### Dependency Simplicity

Vector databases require additional infrastructure: an embedding model, a vector index, and often a separate service. Memory Garden's core dependency list is two packages: Pydantic and PyYAML.

### Deterministic Retrieval

Vector similarity is approximate and model-dependent. Change the embedding model and the same query returns different results. Memory Garden's rule-based retrieval is deterministic and model-independent.

### Privacy

Embedding user messages requires sending text to an embedding model (local or remote). Local embedding models are large downloads; remote ones are privacy leaks. Rule-based harvesting keeps all text local.

### Adequacy for the Baseline

For small-to-medium memory sets (hundreds of cards, typical for a single-user agent), tag and keyword matching is often sufficient. The architecture allows plugging in a vector-based harvester as an optional replacement if semantic scale becomes necessary.

## When Vector Search Makes Sense

If your agent accumulates thousands of memory cards with diverse semantic content, lexical matching will miss too much. The Harvest pipeline is designed with a protocol interface (`HarvesterProtocol`) that makes it possible to swap in a vector-based implementation without changing the rest of the stack.
