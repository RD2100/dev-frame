# AI Workflow Hub — Claude Code Instructions

## Codegraph-First (NOT Grep)

Grep on `*.py` files is FORBIDDEN for code exploration. Use Codegraph instead.

Always do THIS, never Grep:
1. `codegraph_context(task="what does X do")` — understand module + callers + callees
2. `codegraph_callers(symbol="X")` — who calls this
3. `codegraph_impact(symbol="X")` — what would changing this break
4. `codegraph_explore(symbols=["X","Y"])` — read source of multiple symbols
5. `codegraph_search(query="X")` — find symbol by name

Grep is only allowed for:
- Counting output lines (grep -c "PASS" after tests)
- Searching config YAML keys (grep "key" configs/*.yaml)
- Finding literal strings/error messages (not code symbols)

Skill: `/codebase-search`
Project root: `D:\devFrame\ai-workflow-hub`
Hook: settings.json postToolUse will warn on every Grep(*.py) call

Before non-trivial work, read `docs/agent-onboarding.md` and relevant `memory/` cards.

## Python

All code in `src/ai_workflow_hub/`. Configs in `configs/`.
