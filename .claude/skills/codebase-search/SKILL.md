---
name: codebase-search
description: Replace all Grep/Read code exploration with Codegraph MCP. Use when searching for functions, finding callers, checking impact, reading source, or exploring directory structure. This is the DEFAULT code exploration method for ai-workflow-hub.
---

# Codebase Search — Codegraph-First

Never use Grep for code exploration. Use Codegraph MCP instead.

## Grep → Codegraph Mapping

| Instead of | Use | Example |
|---|---|---|
| `grep "foo(" src/` | `codegraph_search("foo")` | Find symbol by name |
| `grep "import X"` + manual trace | `codegraph_callers("foo")` | Who calls this |
| `grep "foo"` + guess impact | `codegraph_impact("foo")` | What would changing this break |
| `read file` to understand module | `codegraph_context("pattern")` | Understand module + callers + callees |
| `read file` for source only | `codegraph_explore(["file.py"])` | Read multiple sources at once |
| `find/ls dir` | `codegraph_files("src/path")` | What's in this directory |
| `grep "class\|def"` for structure | `codegraph_node("symbol")` | Get signature + docstring |

## Quick Reference

```python
# 1. Find a symbol
mcp__codegraph__codegraph_search(query="executor_node")

# 2. Understand context (best first query)
mcp__codegraph__codegraph_context(task="how does executor_node work")

# 3. Who uses this
mcp__codegraph__codegraph_callers(symbol="executor_node")

# 4. Impact of changing this
mcp__codegraph__codegraph_impact(symbol="executor_node")

# 5. Read source (multiple files, capped)
mcp__codegraph__codegraph_explore(symbols=["executor_node", "build_executor_prompt"])

# 6. Directory listing
mcp__codegraph__codegraph_files(path="src/ai_workflow_hub/nodes/")
```

## Project Root

All codegraph queries use: `project_root="D:\devFrame\ai-workflow-hub"`
