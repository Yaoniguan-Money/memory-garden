# Memory Garden v1.4.0 开源发布前检查清单

> 生成日期：2026-05-25
> 适用版本：v1.4.0
> 当前分支：`stage-hard-forget-proof`

---

## 一、安全性（发布前必须完成）

### 1.1 密钥与凭证

| 检查项 | 状态 | 说明 |
|--------|------|------|
| 无硬编码 API Key | ✅ | 全部使用 `os.environ.get()` |
| 无测试中写死真实 Key | ✅ | 全部使用 `"test-key"` 占位 |
| `.secrets.baseline` 无泄露 | ✅ | `results: {}` |
| `detect-secrets` 钩子就绪 | ✅ | `.pre-commit-config.yaml` |

### 1.2 敏感文件

| 检查项 | 状态 | 说明 |
|--------|------|------|
| 无 `.env` 被追踪 | ✅ | `.gitignore` 已覆盖 |
| 无 `*.db` 被追踪 | ✅ | `.gitignore` 已覆盖 |
| 无 `provider_config.json` 被追踪 | ✅ | `.gitignore` 已覆盖 |
| 无 `*_state.json` 被追踪 | ✅ | `.gitignore` 已覆盖 |
| 无 `.memory_garden/` 被追踪 | ✅ | `.gitignore` 已覆盖 |

### 1.3 个人信息

| 检查项 | 状态 | 说明 |
|--------|------|------|
| OPEN_SOURCE_GUIDE.md 无真实路径 | ✅ | 已替换为 `~/.memory_garden/...` |
| 源代码无用户名/绝对路径 | ✅ | |
| 未跟踪文件 `cursor_*.md` / `codex_*.md` | ⚠️ | 已加入 `.gitignore`，但不会自动清理磁盘文件 |
| `.benchmark_*/` 临时数据库 | ⚠️ | 已加入 `.gitignore`，确认未 `git add` |

### 1.4 SQL 安全

| 检查项 | 状态 | 说明 |
|--------|------|------|
| 表名白名单 | ✅ | `storage/sqlite.py:ALLOWED_TABLES` |
| Product 表名白名单 | ✅ | `storage.py:_MODEL_TABLES` |
| 参数化查询 | ✅ | 全部使用 `?` 占位符 |
| 无字符串拼接 SQL（除白名单表名） | ✅ | |

---

## 二、文件清单（开源必须）

### 2.1 必需文件

| 文件 | 状态 | 说明 |
|------|------|------|
| `LICENSE` | ✅ | MIT，2025 |
| `README.md` | ✅ | 英文，结构完整 |
| `README_中文.md` | ✅ | 中英同步完成：覆盖率徽章、检索性能表、ablations 图、行业对比表、Why 对比矩阵 |
| `CONTRIBUTING.md` | ✅ | 119 行 |
| `CODE_OF_CONDUCT.md` | ✅ | Contributor Covenant v2.1 |
| `SECURITY.md` | ✅ | 87 行 |
| `CHANGELOG.md` | ✅ | v1.0.0 + v1.4.0 |
| `CITATION.cff` | ✅ | CFF 1.2.0 |
| `ROADMAP.md` | ✅ | 路线图 |

### 2.2 推荐文件

| 文件 | 状态 | 说明 |
|------|------|------|
| `.gitignore` | ✅ | 已更新，覆盖 .benchmark_*/, cursor_*.md, codex_*.md |
| `.pre-commit-config.yaml` | ✅ | detect-secrets |
| `.secrets.baseline` | ✅ | |
| `pyproject.toml` | ✅ | PEP 621，license 冲突已修复 |
| `mkdocs.yml` | ⚠️ | 缺 skill_layer.md / garden_soil.md 导航 |
| `py.typed` | ⚠️ | 需确认存在 |

### 2.3 不应存在的文件

| 类型 | 状态 |
|------|------|
| `cursor_*.md`（IDE 临时文件） | ✅ 干净包中不存在 |
| `codex_*.md`（IDE 临时文件） | ✅ 干净包中不存在 |
| `.benchmark_*/`（临时数据库） | ✅ 干净包中不存在 |

---

## 三、README 准确性

### 3.1 基准测试数据

| 数据点 | README | 实际 JSON | 差异 | 修复 |
|--------|--------|-----------|------|------|
| FTS5 QPS | 312.0 | 297.1 | 5% | ✅ 已修复 |
| Product QPS | 6.1 | 6.37 | 4.4% | ✅ 已修复 |
| Embed QPS | 3.5 | 3.79 | 8.3% | ✅ 已修复 |
| Embed 注释 "539→552ms" | 旧数据 | 实际 "164→282ms" | — | ✅ 已修复 |

### 3.2 链接有效性

| 链接 | 状态 | 修复方案 |
|------|------|---------|
| `github.com/Yaoniguan-Money/memory-garden` | ❌ 404 | 需创建 GitHub 仓库 |
| `pypi.org/project/memory-garden` | ❌ 不存在 | 需发布 PyPI 包 |
| `pip install memory-garden` | ❌ 不可用 | 同上 |
| `docs/reports/retrieval_benchmark_v2.md` | ✅ 已重生成，内容为 medium 数据集 | |
| 其他文件引用 | ✅ | 全部存在 |

### 3.3 README 中英文同步

| 内容 | 英文版 | 中文版 |
|------|--------|--------|
| 覆盖率徽章 | ✅ | ✅ |
| 检索性能表格 | ✅ | ✅ |
| Ablations 瀑布图 | ✅ | ✅ |
| 延迟分布图 | ✅ | ✅ |
| 行业对比表 | ✅ | ✅ |
| Why 对比矩阵 | ✅ | ✅ |
| 检索策略配置说明 | ✅ | ✅ |
| 会话口令（花花开/花花关） | ✅ | ✅ |
| 接入代码示例 | ✅ | ✅ |
| 开发/Git 历史检查 | ✅ | ✅ |

### 3.4 核心功能验证

| 功能 | 验证结果 |
|------|---------|
| `花花开` 打开会话 | ✅ 正常 |
| `花花关` 关闭会话 | ✅ 正常 |
| 控制口令不被存储为记忆 | ✅ |
| `memory-garden demo` | ⚠️ 需验证 |
| `memory-garden health` | ⚠️ 需验证 |
| `latency_distribution.png` | ✅ 已生成 |
| `retrieval_benchmark_v2.md` (medium) | ✅ 已重生成 |
| mini benchmark 测试 | ✅ 1451 passed, 已修复噪声模板 |

### 3.5 命令可执行性

| 命令 | 可用？ | 说明 |
|------|--------|------|
| `pip install memory-garden` | ❌ | 需 PyPI 发布 |
| `pip install "memory-garden[embeddings]"` | ❌ | 同上 |
| `memory-garden demo` | ✅（本地安装后） | 入口点正确 |
| `memory-garden health` | ✅（本地安装后） | 正确 |
| `python -m benchmarks.retrieval ...` | ✅ | 需本地安装 |

---

## 四、文档一致性

### 4.1 层级数量

| 位置 | 说法 | 建议 |
|------|------|------|
| `docs/architecture.md` | "九层" 但列出十个 | 统一为"十层" |
| `docs/index.md` | "九层" | 统一为"十层" |
| `ROADMAP.md` | "十层" | 正确 |
| `mkdocs.yml` | "九层" | 统一为"十层" |

### 4.2 版本号

| 位置 | 版本 | 一致性 |
|------|------|--------|
| `pyproject.toml` | 1.4.0 | ✅ |
| `CHANGELOG.md` | 1.4.0 | ✅ |
| `CITATION.cff` | 1.4.0 | ✅ |

---

## 五、发布前操作步骤

### 步骤 1：清理磁盘文件（本地执行）

```powershell
Remove-Item -Recurse -Force .benchmark_garden, .benchmark_comparison, .benchmark_real, .benchmark_tmp -ErrorAction SilentlyContinue
Remove-Item -Force cursor_auto_review.md, cursor_exec_prompt.md, cursor_review_report.md, cursor_tech_depth_review.md -ErrorAction SilentlyContinue
Remove-Item -Force codex_tech_review_prompt.md -ErrorAction SilentlyContinue
```

### 步骤 2：修复 mkdocs.yml 导航

添加缺失的 `architecture/skill_layer.md`、`architecture/garden_soil.md` 和 `architecture.md`。

### 步骤 3：重生成 `retrieval_benchmark_v2.md`

README 引用该文件描述 medium 数据集，但文件内容是 tiny。需重新生成：
```bash
python -m benchmarks.retrieval --dataset medium --baselines default --output docs/reports/benchmark_v2.json --markdown docs/reports/retrieval_benchmark_v2.md
```

### 步骤 4：确认 `py.typed` 存在

`py.typed` 标记文件应在 `memory_garden/` 目录下。这是 PEP 561 合规要求。

### 步骤 5：统一层级描述

将 `docs/architecture.md`、`docs/index.md`、`mkdocs.yml` 中的"九层"改为"十层"。

### 步骤 6：创建 GitHub 仓库

1. 在 GitHub 创建 `memory-garden/memory-garden` 仓库
2. 推送当前分支
3. 所有徽章自动生效

### 步骤 7：发布 PyPI

```bash
pip install build twine
python -m build
twine check dist/*
twine upload dist/*
```

### 步骤 8：部署文档站点

```bash
pip install mkdocs-material
mkdocs gh-deploy
```

### 步骤 9：更新 pyproject.toml URL

将 `Documentation` URL 改为 `https://memory-garden.github.io/memory-garden/`。

---

## 六、发布后验证

| 检查项 | 验证方式 |
|--------|---------|
| PyPI 可安装 | `pip install memory-garden` 在新虚拟环境成功 |
| CLI 可运行 | `memory-garden health` 输出正常 |
| Demo 可运行 | `memory-garden demo` 无障碍 |
| GitHub 测试 CI 通过 | Actions 全部绿色 |
| README 徽章正确显示 | GitHub README 页面查看 |
| 文档站点可访问 | `https://<org>.github.io/memory-garden/` |

---

## 七、Git 备份

当前版本已通过 `git tag v1.4.0-rc1` 备份。回退命令：`git checkout v1.4.0-rc1`
