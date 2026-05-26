# ai-workflow-hub

稳定优先的多项目 AI 自动化闭环开发系统。

## Quick Start

```bash
cd your-project
aihub do "describe the change"
aihub do --apply "describe the change"
```

Default dry-run. Changes in isolated worktree. No push/merge/deploy.

```
v0.1  单次闭环执行器    dry-run / human_gate / Git 硬事实
v0.2  本地任务编排器    双 backend / fallback / worktree / daemon
v0.3  本地开发控制面    daemon 持续 / release_policy / board
v0.4  可持续运营        acceptance / audit / policy gate
v0.5  真实运营验证      backend health / real PR / CI inspect
v0.6  长期运营维护      task ops / run prune / safety enhanced
v0.7  近零配置入口      auto-detect / aihub do / session gate
```

## 系统用途

ai-workflow-hub 是一个**安全第一**的多项目 AI 编码自动化工单系统：

- 多个业务项目可以接入同一个 Hub
- LangGraph 负责状态机调度（只做编排，不写代码）
- Codex / GPT-5.5 负责规划、复审、风险裁决（thinking backend）
- Claude Code / DSV4 Pro 负责真实编码执行和测试失败修复（coding backend）
- OpenCode 保留为 degraded optional，不参与默认 fallback
- 以 Git diff、原始测试日志、exit code 作为唯一事实依据
- **默认 dry-run**，必须显式 `--apply` 才真实修改
- 所有真实修改发生在独立 Git worktree 中

For future agents: start with `docs/agent-onboarding.md`.

## 架构说明

```
用户
 │
 ▼
┌─────────────┐     ┌──────────────┐     ┌──────────────┐
│   aihub CLI  │────▶│  LangGraph    │────▶│  Codex/GPT5.5 │
│   (Typer)    │     │  StateGraph   │     │  (规划/复审)   │
└─────────────┘     └──────────────┘     └──────────────┘
       │                    │                      │
       ▼                    ▼                      ▼
┌─────────────┐     ┌──────────────┐     ┌──────────────┐
│  projects/  │     │  Claude Code  │     │  Shell/cmd    │
│  tasks/     │     │  DSV4 Pro     │     │  (测试执行)    │
│  configs/   │     │  (编码/修复)  │     │               │
└─────────────┘     └──────────────┘     └──────────────┘
```

### 为什么 LangGraph 只做调度，不直接写代码？

LangGraph 是状态机引擎，擅长管理复杂的状态转换和条件路由。但它不是 LLM——它不应该生成或修改代码。所有代码修改通过 Claude Code 完成，带文件白名单和黑名单约束。LangGraph 的角色是"交通警察"，确保代码修改流程走正确的安全通道。

### 为什么 Codex 负责规划复审？

Codex / GPT-5.5 擅长理解和推理——读取 task、分析约束、判断风险、决策。它不直接操作文件系统。规划和复审是"想"的任务，和正确"做"的任务需要不同的大脑。

### 为什么 Claude Code 负责编码执行？

Claude Code + DSV4 Pro 擅长忠实执行具体的编码指令——修改特定文件、运行测试、修复指定问题。DSV4 在代码生成和修复任务上有很高的性价比。Claude Code 操作文件，但只能在 LangGraph 和 Codex 划定的安全边界内操作。OpenCode 保留为 degraded optional backend，不参与默认 fallback。

## 安装步骤

```bash
# 1. 克隆或进入 ai-workflow-hub 目录
cd ai-workflow-hub

# 2. 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows

# 3. 安装
pip install -e .

# 4. 安装开发依赖（可选）
pip install -e ".[dev]"

# 5. 配置环境变量
cp .env.example .env
# 编辑 .env，填入 API Key 和模型 ID

# 6. 验证安装
aihub doctor
```

## 环境变量配置

所有 API Key 通过环境变量读取，不写在代码或配置文件里：

| 变量 | 用途 |
|------|------|
| `CODEX_API_KEY` | Codex API Key |
| `CODEX_API_BASE` | Codex API Base URL |
| `CODEX_MODEL_PLANNER` | 规划模型 ID（默认 gpt-5.5-codex） |
| `CODEX_MODEL_REVIEWER` | 复审模型 ID |
| `CODEX_MODEL_FINALIZER` | 终结模型 ID |
| `OPENCODE_API_KEY` | OpenCode API Key |
| `OPENCODE_API_BASE` | OpenCode API Base URL |
| `OPENCODE_MODEL_EXECUTOR` | 执行模型 ID（默认 deepseek-v4-pro） |
| `OPENCODE_MODEL_FIXER` | 修复模型 ID |
| `OPENROUTER_API_KEY` | OpenRouter API Key（可选） |
| `OPENROUTER_API_BASE` | OpenRouter API Base URL |

## 如何配置 projects.yaml

```yaml
projects:
  - id: my-project
    name: My Project
    path: /absolute/path/to/project
    config: .aiworkflow.yaml
    enabled: true
    priority: high
```

## 如何配置 .aiworkflow.yaml

在业务项目根目录创建 `.aiworkflow.yaml`：

```yaml
project:
  id: my-project
  name: My Project
  type: backend
  repo_path: /absolute/path/to/project
  default_branch: main

commands:
  install: pip install -e ".[dev]"
  lint: ruff check .
  unit_test: pytest tests/
  typecheck: mypy src/

policy:
  forbidden_paths:
    - .env*
    - secrets/**
    - production/**
  protected_tests:
    - "**/test_*.py"
```

## 如何添加任务

```bash
# 命令行
aihub task add --project my-project --title "修复登录测试" --description "修复 3 个失败的测试" --risk medium

# 或直接编辑 tasks.yaml
```

## 如何 dry-run

```bash
# 默认 dry-run — 只规划，不修改代码
aihub run --project my-project --task task-abc123
```

Dry-run 会执行完整工作流（规划 → human_gate → 模拟执行 → 测试 → 复审），但 executor 不会真实修改任何文件。

## 如何 apply

```bash
# 显式 --apply 才会真实修改代码
aihub run --project my-project --task task-abc123 --apply
```

Apply 会：
1. 创建独立 Git 分支 `ai/{task_id}-{run_id}`
2. 在该分支上执行修改
3. 执行测试验证
4. 生成完整报告

**不会**自动 push、merge 或修改 main 分支。

## 如何查看报告

```bash
# 查看所有运行状态
aihub status

# 查看特定运行报告
aihub report --run run-20260524-120000-abc123
```

每次运行在 `runs/<project_id>/<run_id>/` 保存完整证据链。

## 如何处理 human_gate

当工作流暂停在 human_gate：
1. 查看 `runs/<project_id>/<run_id>/human-gate.md`
2. 审查 diff.patch、review.md、safety-report.md
3. 决定：批准 / 拒绝 / 修改范围
4. 如果是高风险任务，人工确认后用 `--apply` 重新运行

## 如何处理 blocked

Blocked 意味着变更违反了安全策略（删除了测试、修改了 forbidden path 等）：
1. 查看 `final-report.md` 中的 blocked 原因
2. 修改任务范围或项目配置
3. 重新提交任务

## 如何新增项目

```bash
# 1. 在业务项目根目录创建 .aiworkflow.yaml
# 2. 在 projects.yaml 中注册
# 3. 校验
aihub project validate --project my-project
```

## 如何切换模型

三种方式（优先级从高到低）：
1. **环境变量**: `export CODEX_MODEL_PLANNER=gpt-5.5-new`
2. **configs/model-router.yaml**: 修改 risk_profiles 中的模型
3. **.aiworkflow.yaml**: 在业务项目配置中定义 models 节

## 安全策略

硬规则（不可覆盖）：

| 规则 | 动作 |
|------|------|
| high 风险任务 | human_gate |
| 修改 forbidden_paths | human_gate |
| 删除 protected_tests | blocked |
| 降低测试断言 | blocked |
| diff 超 max_diff_lines | human_gate |
| 文件数超 max_changed_files | human_gate |
| 修复轮次超 max_fix_rounds | blocked |
| 自动 push | 禁止 |
| 自动 merge | 禁止 |
| 修改 main/master | 禁止 |

## 当前限制

第一版实现稳定最小闭环，**暂不实现**：

- Dashboard / Web UI
- 多项目并发执行
- 自动创建 PR
- 自动 push / merge
- 长期记忆系统
- 自动任务发现
- 高风险任务自动执行

## 后续路线

- v0.2: 并发执行、PR 自动创建
- v0.3: Web Dashboard
- v0.4: 长期记忆 + 经验学习
- v1.0: 自动任务发现 + 定时调度

## 目录结构

```
ai-workflow-hub/
  README.md               # 本文件
  pyproject.toml          # Python 项目配置
  .env.example            # 环境变量模板
  .gitignore
  projects.yaml           # 项目注册表
  tasks.yaml              # 任务队列
  configs/
    model-router.yaml      # 模型路由配置
    risk-policy.yaml       # 风险策略定义
    execution-policy.yaml  # 执行策略定义
  src/ai_workflow_hub/
    __init__.py
    cli.py                 # Typer CLI 入口
    schemas.py             # Pydantic 数据模型
    config_loader.py       # YAML 配置加载
    model_router.py        # 模型选择逻辑
    project_registry.py    # 项目管理
    task_queue.py          # 任务管理
    run_store.py           # 运行存储
    git_utils.py           # Git 安全封装
    shell_runner.py        # Shell 安全执行
    opencode_client.py     # OpenCode CLI 客户端
    codex_client.py        # Codex CLI 客户端
    safety.py              # 安全检查
    diff_utils.py          # Diff 工具
    report_utils.py        # 报告工具
    workflows/
      coding_graph.py      # LangGraph 状态机
    nodes/
      planner.py           # 规划节点
      executor.py          # 执行节点
      tester.py            # 测试节点
      fixer.py             # 修复节点
      reviewer.py          # 复审节点
      router.py            # 路由节点
      human_gate.py        # 人工门节点
      finalizer.py         # 终结节点
    prompts/               # Prompt 模板
  examples/                # 示例配置
  runs/                    # 运行输出
  scripts/                 # 工具脚本
```
