# Memory Garden 开源准备指南

## 零、发布前原则

五条铁律，违反一条就别发：

1. **不要暴露任何人的数据。** 你的花园 DB 里有 108 条真实背景信息，如果这 108 条随着源码一起被 commit，那你开源的不是代码，是隐私。
2. **不要提交任何 key。** DeepSeek API key、阿里云百炼 key——哪怕"只是测试环境"。git history 里有就是有，删不掉的。
3. **1,330 tests 必须全绿。** 如果因为 README 改了一行 markdown 导致 CI 炸了，先修 CI。开源第一天崩测试 = 永远洗不掉的印象。
4. **可以大幅度重构。** 拆文件、合模块、改名、提抽象——都可以。但必须在重构前先确保 1,330 测试全绿，重构后一个测试不许挂。
5. **不许功能降级。** 当前跑通的链路（LLM 提取、LLM brief、Hook 注入、Dream 周期、hard forget）重构后一条都不能少。删代码前先确认谁在调用它。

---

## 一、隐私数据清理

### 1.1 本地花园 DB

```
~/.memory_garden/garden.db              ← 真实背景记忆
~/.memory_garden/provider_config.json   ← API keys
~/.memory_garden/claude_code_state.json ← 对话状态
```

**绝不提交。** 确认 `.gitignore` 里有：

```
.memory_garden/
*.db
*.db-wal
*.db-shm
*_state.json
provider_config.json
```

### 1.2 git history 审计

在 push 前跑一遍：

```bash
git log --all --full-history -- "*.db" "*.key" "*_state.json"
```

确保历史中没有误提交的敏感文件。如果有——用 `git filter-branch` 或 `BFG Repo-Cleaner` 清理，别手动删完就 push。

### 1.3 测试数据

检查所有 test fixture 和 seed 脚本：
- `tests/seed_garden_batch.py` ← 删掉，这是手动灌数据的，不是测试
- 所有测试 fixture 里的 `":memory:"` SQLite 是安全的
- 确认没有任何测试里写死了真实路径如 `~/.memory_garden` 或绝对用户路径

### 1.4 日志和输出

- `logger.warning` 有没有打印用户消息原文？审查 `product/system.py` 和 `runtime/hooks.py` 里的日志
- Hook 的 stderr 输出在生产环境应该关闭 `debug` 级别

---

## 二、安全防护

### 2.1 API Key 管理

当前问题：provider_config.json 明文存 key。

开源的代码不能强制用户用明文。提供三层方案：

| 层级 | 方式 | 优先级 |
|------|------|--------|
| 1 | 环境变量 `DEEPSEEK_API_KEY` | 最高（代码已支持） |
| 2 | 配置文件 `~/.memory_garden/provider_config.json` | 中（当前方案） |
| 3 | 交互式输入 `python -m memory_garden init --interactive` | 低（doctor 命令可做） |

README 里只宣传第 1 层。第 2 层作为"不想设环境变量时"的备案。

### 2.2 Secret Detection

在 `.pre-commit-config.yaml` 里加 secret 扫描，防自己失手：

```yaml
repos:
  - repo: https://github.com/Yelp/detect-secrets
    rev: v1.5.0
    hooks:
      - id: detect-secrets
        args: ['--baseline', '.secrets.baseline']
```

初始化 baseline：

```bash
pip install detect-secrets
detect-secrets scan > .secrets.baseline
detect-secrets audit .secrets.baseline  # 标记所有真实 secret 为 true positive
```

### 2.3 SQL 注入

已做：表名白名单 `ALLOWED_TABLES`，参数化查询。

还需做：
- `product/storage.py` 的 `_MODEL_TABLES` 白名单要显式出现在 README 安全章节里——让别人审计时一眼看到
- `soil/forget.py` 里 `repo._conn.execute(f"DELETE FROM {FTS_TABLE}...` 的 `FTS_TABLE` 是常量，安全，但要加注释说明

### 2.4 路径遍历

- `observatory/` 和 `soil/` 里接受外部 `garden_home` 参数。确认所有路径操作都是用 `Path(...).resolve()` 并限制在用户目录内
- `_read_transcript_user_message()` 用了 `strict=True`，已安全

---

## 三、屎山重构 —— 不该现在做的事

以下区域不要碰，留到 v1.5+：

| 区域 | 问题 | 为什么不要现在动 |
|------|------|-----------------|
| `skill.py` 的 `product` getter | 绕过了 provider 配置层 | Codex 已修，稳定的 workaround |
| `cognition/` 的三个 stage | 和 runtime/product 层断连 | 功能完整，只是没接入，不是坏了 |
| `soil/forget.py` 的 `_conn` 穿透 | 直接从 repo._conn 操作 SQL | 封装不够，但 1,330 测试保证正确性 |
| 两层 HarvestMode 枚举 | harvest 和 cognition 各自定义 | 改名会连锁炸 import，不值得 |

**原则**：如果 1,330 测试证明它能工作，那就别因为"不优雅"去重构它。优雅是给 v2 的。

---

## 四、不疯狂打补丁

### 4.1 当前状态不需要补的

- 不新增 `--flag` 参数，除非 doctor 命令需要
- 不新增配置项，当前 env var + config file 两种方式已经覆盖需求
- 不新增抽象层，"Provider 接口有三套要不要统一"——不要。统一带来的破坏 > 收益

### 4.2 如果用户提 issue

- Bug fix → 修，加回归测试
- Feature request → 标 `good first issue` 或 `help wanted`，不自己写
- 架构建议 → 感谢，列入 v2 roadmap，不改当前代码
- "能不能支持 OpenAI" → 回"ProviderRegistry 是 Protocol，你自己实现三行就能接"

---

## 五、README 结构

### 5.1 必须有的章节

```
# Memory Garden
一句话 + badge (tests passing, python 3.10+, license)

## 为什么需要 Memory Garden
30 秒场景：Agent 聊了 50 轮，它不记得你叫小明

## 快速开始
3 步：install → env var → hook

## 效果
旧版 brief（UUID 列表）vs 新版（自然语言摘要）截图

## 架构
图 + 一句话每个层的职责

## 接入指南
Claude Code / LangChain / 自定义 Agent

## 安全性
local-first, auditable, no cloud, hard forget proof

## 开发
pip install -e ., pytest, 1,330 tests

## License
MIT
```

### 5.2 不该放在 README 里的

- 不要写"将来会支持 XXX"——你现在做了才算
- 不要写"与 LangChain Memory 对比"——容易引战，让别人写
- 不要写 benchmark——你没测，别编
- 不要写 Star 历史——空的

---

## 六、社区健康文件

需要这 5 个文件才能算正经开源项目：

| 文件 | 内容 |
|------|------|
| `CONTRIBUTING.md` | 如何设开发环境、跑测试、提 PR 的格式要求 |
| `CODE_OF_CONDUCT.md` | 直接用 Contributor Covenant v2.1，别自己写 |
| `SECURITY.md` | 报告漏洞的邮箱 + "不要公开披露，给 48 小时响应" |
| `LICENSE` | MIT |
| `CHANGELOG.md` | v1.0.0 初版发布，列关键特性 |

---

## 七、CI / 自动化

最小可用的 GitHub Actions，在 `.github/workflows/tests.yml`：

```yaml
name: tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.10", "3.11", "3.12"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - run: pip install -e ".[dev]"
      - run: pytest -q
```

不要加 lint（black/isort/mypy）。开源第一天报 lint 警告会让 contributor 不敢提交。等社区稳定后再加。

---

## 八、我个人觉得你需要保护的地方

### 8.1 `.claude/settings.json` 的 hook timeout

当前 15 秒。LLM brief 调用 DeepSeek 最快也要 2-3 秒。如果 DeepSeek 慢或挂了，15 秒到时就输出空 brief。**不要把 timeout 设太死**——调成 30 秒，给 LLM 余量。

### 8.2 hook 失败不能阻塞 Claude Code

当前 `_cmd_hook_before()` 如果抛异常，整个 before hook 挂了——但 `.claude/settings.json` 里的 `type: "command"` 默认行为是 exit code ≠ 0 时日志里报 warning 但**不阻塞** Claude。这个行为是正确的，不要试图"改进"——hook 失败时让 Claude 正常回复比截断对话重要。

### 8.3 `provider_config.json` 要不要开源前删

你已经删了学习通的代码。但 `provider_config.json` 在 `~/.memory_garden/` 下，不在项目目录里，不会被 commit。确认一下 git status 没有显示它。

### 8.4 项目名

"Memory Garden" 是好的。不要改。"Cognitive Garden" 太学术，"Agent Memory" 太泛，"Claude Memory" 有商标风险。

### 8.5 发布渠道

先发 GitHub 公开仓库。PyPI 发布 `pip install memory-garden` 放在第二步。Reddit r/LocalLLaMA、Hacker News Show HN 同时发——但要在你确认 README、CI、community files 就绪之后。第一印象只有一次。

---

## 九、发布前 Checklist

- [ ] `.gitignore` 有 `.memory_garden/`、`*.db`、`*_state.json`
- [ ] git history 无敏感文件
- [ ] `tests/seed_garden_batch.py` 已删除或移到 `scripts/` 并 gitignore
- [ ] 所有测试 fixture 无真实路径
- [ ] README.md 和 README.zh-CN.md 已更新
- [ ] `doctor` 命令可用
- [ ] 1,330 tests 全绿
- [ ] CONTRIBUTING.md / CODE_OF_CONDUCT.md / SECURITY.md / LICENSE / CHANGELOG.md 就位
- [ ] `.github/workflows/tests.yml` CI 通过
- [ ] provider_config.json 不在 git 跟踪中
- [ ] `pip install -e .` 在新 venv 里能跑通
