# Quickstart

## 1. Setup

```bash
cd ai-workflow-hub
python -m venv .venv && source .venv/bin/activate
pip install -e .
cp .env.example .env  # edit with your API keys
```

## 2. 配置项目

```yaml
# projects.yaml
projects:
  - id: my-project
    name: My Project
    path: /path/to/repo
    enabled: true
```

```yaml
# .aiworkflow.yaml (in project root)
commands:
  lint: ruff check .
  unit_test: pytest tests/
```

## 3. 验证环境

```bash
aihub doctor
aihub acceptance run smoke
```

## 4. 执行任务

```bash
# Dry-run (不修改代码)
aihub run start --project my-project --task task-001

# Apply (真实修改, 创建独立branch/worktree)
aihub run start --project my-project --task task-001 --apply --coding-backend claude

# 查看结果
aihub run show --run-id <run-id>
aihub board
```

## 5. Daemon 持续运行

```bash
aihub daemon start --once
aihub daemon status
aihub board --watch
```

## 6. 外部集成

```bash
# Import GitHub issues
aihub issue import --repo owner/repo --label aihub

# PR preview
aihub pr preview --project my-project --run-id <run-id>

# CI inspect
aihub ci inspect --repo owner/repo --pr <number>
```

## 安全

所有 push/merge/deploy 默认 BLOCKED。需要时修改 `execution-policy.yaml` 显式开启。
