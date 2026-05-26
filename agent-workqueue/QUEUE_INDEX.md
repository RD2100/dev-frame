# WorkQueue Index

| Queue | File | Purpose | Run When | Review Focus |
|-------|------|---------|----------|-------------|
| local-quality | `local-quality.queue.json` | Base quality gate: compileall, yaml, smoke, dynamic, assertion, recovery, rc, cleanup, status, docs | Every round, default first | All green |
| docs-quality | `docs-quality.queue.json` | Doc presence: release pack, runbook, recovery, powershell-acceptance, workqueue, status-machine | Doc changes, handoff | Missing/stale docs |
| recovery-regression | `recovery-regression.queue.json` | Recovery pipeline regression: all acceptance suites | Recovery code changes | Evidence chain |
| release-readiness | `release-readiness.queue.json` | Release gate: rc-check, assertion-check, smoke, compileall | Pre-release | Config/doc consistency |
| cleanup-dryrun | `cleanup-dryrun.queue.json` | Cleanup safety: classifier, retention policy | Cleanup code changes | No false delete candidates |

## Default Entry

```powershell
# Serial (default, safe)
powershell -ExecutionPolicy Bypass -File scripts/acceptance/Run-QueueGroup.ps1 `
  -QueueFiles agent-workqueue/local-quality.queue.json,agent-workqueue/docs-quality.queue.json,agent-workqueue/recovery-regression.queue.json,agent-workqueue/release-readiness.queue.json,agent-workqueue/cleanup-dryrun.queue.json

# Parallel (3 parallel-safe queues)
powershell -ExecutionPolicy Bypass -File scripts/acceptance/Run-QueueGroup.ps1 `
  -Parallel -MaxParallel 2 `
  -QueueFiles agent-workqueue/docs-quality.queue.json,agent-workqueue/release-readiness.queue.json,agent-workqueue/cleanup-dryrun.queue.json
```

## Parallel Policy

| Queue | Parallel Safe | Reason |
|-------|--------------|--------|
| docs-quality | yes | Read-only doc checks |
| release-readiness | yes | Read-only quality checks |
| cleanup-dryrun | yes | Dry-run, no delete |
| local-quality | conditional | Multiple suites; prefer serial or limit concurrency |
| recovery-regression | no | Recovery fixtures; serial required |

## For Code Agent

Default: serial Run-QueueGroup with all 5 queues.
Only use -Parallel with explicitly marked parallel-safe queues (docs, release, cleanup).

## For Reviewer
