# Quickstart

Get Memory Garden running locally in a few minutes.

## Prerequisites

- Python 3.10 or later
- Git, if installing from source

## Install

```bash
pip install memory-garden

# or from the repository root:
pip install -e .
```

## Verify

```bash
memory-garden demo
memory-garden health
python -m pytest tests -q
```

Release gate: the full suite should pass on a clean checkout.

## Run The Demo

The demo opens a Garden session, runs two normal chat turns, harvests local memory context, and closes the session. It uses local rules by default.

```bash
memory-garden demo --path ./.memory_garden
```

Session control commands:

1. `花花开` opens a session. It is a control command and is never stored as memory.
2. User messages are observed while the session is open.
3. `花花关` closes the session and produces structured feedback.

## 接入大模型

Memory Garden 默认可以完全本地运行。需要真实模型能力时，可以显式接入 provider。

### DeepSeek

```python
from memory_garden.sdk import MemoryGarden

garden = MemoryGarden.local("./my_garden")
skill = garden.as_skill().with_deepseek()

# 通过环境变量提供 key：
# export DEEPSEEK_API_KEY="..."
```

```bash
export DEEPSEEK_API_KEY="..."
memory-garden --provider deepseek retrieve "dark mode"
memory-garden --provider deepseek brief "release checklist"
```

### OpenAI

```python
from memory_garden.sdk import MemoryGarden

garden = MemoryGarden.local("./my_garden")
skill = garden.as_skill().with_openai()

# 通过环境变量提供 key：
# export OPENAI_API_KEY="..."
```

```bash
export OPENAI_API_KEY="..."
memory-garden --provider openai retrieve "dark mode"
memory-garden --provider openai brief "release checklist"
```

避免把 API key 放进命令行参数，因为 shell history、进程列表和录屏都可能留下痕迹。

如果你在 Claude Code / Codex / Hermes / OpenClaw 的 CLI hook 中希望从环境变量或
本地 `provider_config.json` 自动加载 provider，再额外设置：

```bash
export MEMORY_GARDEN_ENABLE_PROVIDER_AUTOLOAD=1
```

完整示例见仓库中的 `scripts/real_provider_smoke.py`。单元测试仍使用 deterministic fake providers，不会发起真实 LLM 调用。

## Next Steps

- Read [Concepts](concepts.md) to understand the garden metaphor.
- Follow the [First Session tutorial](tutorials/first_session.md) to write your own integration.
- Browse [Examples](https://github.com/Yaoniguan-Money/memory-garden/tree/main/examples) for more patterns.
