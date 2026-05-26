---
name: codegraph-usage-pattern
description: codebase-search skill + codegraph MCP 的使用模式和效果验证
type: reference
---

# Codegraph 使用模式

## 触发条件

任何代码探索/修改前，先用 codegraph，不用 Grep。

## 标准流程

```python
# 步骤 1：改代码前先查上下文
mcp__codegraph__codegraph_context(
    task="what does <module> do and who calls it",
    project_root="D:\devFrame\ai-workflow-hub"
)

# 步骤 2：如需查调用链
mcp__codegraph__codegraph_callers(symbol="function_name")

# 步骤 3：如需查影响面
mcp__codegraph__codegraph_impact(symbol="function_name")

# 步骤 4：精准 edit，不再盲目 read 整个文件
```

## 已验证效果

| 场景 | 无 codegraph | 有 codegraph | 节省 |
|------|-------------|-------------|------|
| P3 baseline 实现 | grep+read acceptance.py 全文 ~800 tokens | codegraph_context 一次 ~200 tokens | ~75% |
| P2 ci_inspect 修复 | grep+read 3个文件 | 未用 (违规) | — |

## 安装位置

- Skill: `~/.claude/skills/codebase-search/SKILL.md`
- 项目规则: `.claude/rules/codegraph-first.md`
- 项目配置: `CLAUDE.md`

## 审计

2026-05-24 | RD | 初始创建：P3 轮次验证 codegraph 有效，记录使用模式
