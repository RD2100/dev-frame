# Chain Truth Verification Prompt

You must verify the real thinking/execution chain from current evidence, not from intended config or previous reports.

## Goal

Determine the actual models/backends used by the latest run.

Target architecture:
- Thinking: planner, reviewer, finalizer → codex_cli / gpt-5.5-codex
- Execution: executor, fixer → claude / deepseek-v4-pro

Do not assume the target is true. Prove the actual chain from evidence.

## Required Evidence

Inspect the latest run directory:

1. state.json → backend_calls
2. final-report.md
3. planner-stdout.log / planner-stderr.log
4. reviewer-stdout.log / reviewer-stderr.log
5. finalizer-stdout.log / finalizer-stderr.log
6. claude-stdout.log / claude-stderr.log
7. opencode-*.log (should NOT exist)
8. run verify output

## Classification

For each node: codex_cli | http_fallback | claude | opencode | local_template | not_called | unknown

Record: node, backend, model, exit_code, timed_out, duration, fallback_from, fallback_reason, trusted_for_status, evidence file.

## Hard Rules

1. Do not claim "Codex thinking" unless planner AND reviewer are actually codex_cli.
2. Do not claim "Claude execution" unless executor is actually claude.
3. If finalizer is local_template, report as deterministic local, not model thinking.
4. If http_fallback used, mark explicitly with fallback_from and fallback_reason.
5. If OpenCode logs exist for executor/fixer, do not claim pure Claude execution.
6. If evidence missing, classify as unknown, not as expected.
7. Config values are NOT proof of actual execution.
8. Previous reports are NOT proof. Only current run evidence counts.

## Output

```md
## Chain Truth Result

### Summary
- Verdict: MATCH_TARGET / PARTIAL_MATCH / MISMATCH / UNKNOWN
- Run ID:
- Mode: dry-run / apply
- Status:
- Review result:

### Actual Chain
| Node | Backend | Model | Fallback | Timeout | Trusted | Evidence |
|------|---------|-------|----------|---------|---------|----------|

### Target Match
- Thinking target: yes/no/partial
- Execution target: yes/no/partial
- Finalizer trusted: yes/no
- OpenCode involved: yes/no
- HTTP fallback involved: yes/no

### Final Statement
One of:
- "The run proves Codex CLI thinking + Claude execution."
- "The run proves Codex CLI planner/reviewer + Claude executor, with non-Codex finalizer fallback."
- "The run does not prove the target chain."
- "The evidence is insufficient to determine the target chain."
```

## Acceptance

- planner is codex_cli
- reviewer is codex_cli
- executor is claude for apply runs
- OpenCode is not used
- fallback/local finalizer is clearly labeled
- run verify passes

If conclusion relies on expected config rather than backend_calls or log evidence, mark verdict as UNKNOWN.
