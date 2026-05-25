# Installation

## Requirements

- Python 3.10+
- `pip` (or equivalent)

Memory Garden has a minimal dependency footprint by design:

| Dependency | Purpose |
|---|---|
| `pydantic>=2.0,<3` | Data models and validation |
| `PyYAML>=6.0,<7` | Covenant YAML configuration loading |
| `pytest>=7.0` (optional, dev) | Running the test suite |

No database drivers, HTTP clients, LLM SDKs, or vector stores are required.

## From Source (Recommended)

```bash
git clone <repository-url> memory-garden
cd memory-garden
pip install -e .
```

For development, include test dependencies:

```bash
pip install -e ".[dev]"
```

## Verify

```bash
python -c "import memory_garden; print('Memory Garden imported successfully')"
```

Run the test suite:

```bash
python -m pytest tests -q
```

## Optional Extras

Memory Garden does not ship optional dependency groups in its default package. If you want to build an integration that uses a language model, vector database, or web framework, install those separately in your own project.

The project deliberately avoids depending on:

- `openai`, `anthropic`, or any LLM provider SDK
- `sqlalchemy` or ORM layers
- `chromadb`, `faiss`, `pinecone`, or vector stores
- `fastapi`, `flask`, or web frameworks
- `langchain`, `llamaindex`, or agent frameworks

These choices keep the core package small, auditable, and free of supply-chain risk from rapidly-changing AI SDKs.
