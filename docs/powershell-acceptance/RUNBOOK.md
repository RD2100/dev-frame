# PowerShell Acceptance Runner Runbook

## Quick Start

```powershell
cd D:\devFrame\ai-workflow-hub

# Smoke test (no real backend)
powershell -ExecutionPolicy Bypass -File scripts/acceptance/Run-Smoke.ps1

# Custom flow
powershell -ExecutionPolicy Bypass -File scripts/acceptance/Run-Smoke.ps1 -ProjectPath D:\my-project
```

## Exit Codes

| Exit | Meaning |
|------|---------|
| 0 | PASS — all checks passed |
| 1 | BLOCKED — some pre-flight checks blocked (config missing, tool not found) |
| 2 | FAILED — at least one check failed |

## Report Structure

Every report has three sections:

| Section | Purpose |
|---------|---------|
| Implementation | Static checks: files exist, configs valid, compile passes |
| Runtime | Checks that execute code: tests, commands, backend calls |
| Explorer | UI/browser exploration (deferred until browser automation added) |

## Adding a New Flow

1. Add a flow entry in `FLOW_CATALOG.md`
2. Define: `flow_id`, `command`, `expected_exit_code`, `expected_output`, `failure_signals`
3. Run: `powershell -File scripts/acceptance/Run-Flow.ps1 -FlowId <id>`
4. Collect artifacts: output paths + screenshot paths (when available)

## When to Use Browser Automation

Currently Explorer is marked as:
```
Explorer: not run, browser automation deferred
```

## Batch Execution (v1.19)

```powershell
# Run all Tier 0 quality checks in one batch
powershell -ExecutionPolicy Bypass -File scripts/acceptance/Run-Batch.ps1 `
  -TaskFile scripts/acceptance/examples/batch-local-quality.json
```

Exit codes: 0=PASS, 1=BLOCKED, 2=FAILED.
Report: `runs/powershell-acceptance/batch-local-quality/batch-report.md`

## When to escalate to GPT-5.5

- FAILED tasks with `reason` containing timeout or exception
- 2+ FAILED in a batch
- Reviewer ACK needed (recovery reviewer, cleanup apply, real E2E)

## When to use cheap code agent

- Tier 0 checks: all batch-local-quality tasks
- Tier 1 docs generation
- Task result collection

## When to add browser validation
1. Install Playwright: `npm init playwright`
2. Write browser flow scripts in `scripts/acceptance/browser/`
3. Change Explorer note to: `Explorer: see browser-report.md`
4. Run: `npx playwright test` from the acceptance directory
