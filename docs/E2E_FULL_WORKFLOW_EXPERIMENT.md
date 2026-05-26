# Full Workflow E2E Experiment

**Date**: 2026-05-25

## Status at v1.9 Close

v1.8 experiment established: planner (gpt-5.5-codex via deepseek proxy) needs ~188s.
300s planner budget is sufficient; 120s is not.

v1.9 delivers: boundary conflict resolution, system budget visibility, run_id sync recovery.

Full workflow E2E (planner→executor→reviewer→finalizer) not re-run in v1.9 —
Batch D deferred by design (A/B/C are code infrastructure; D is real E2E, to be run after ACK).

## Boundaries (v1.9 fix)

```
allowed_files beats forbidden_files at exact file match level.
Directory-level forbidden (src/, configs/) preserved for all files under them.
_resolve_boundary() in cli.py handles this at WorkflowState construction.
```

## Budgets (v1.9)

| Budget | Config | Default |
|--------|--------|---------|
| planner_seconds | `execution-policy.yaml` → `timeouts.planner_seconds` | 300 |
| system_seconds | `execution-policy.yaml` → `timeouts.system_seconds` | 600 |

Env overrides available: `AIHUB_PLANNER_TIMEOUT_SECONDS`, `AIHUB_SYSTEM_TIMEOUT_SECONDS`.

## Recovery (v1.9)

`sync_goal_runs(goal_id)` scans `runs/*/state.json` for matching `task_id` and backfills `batch.run_id`.
Does NOT change batch status. Safe for post-kill recovery.

## Recommended Full E2E Probe

```powershell
$env:AIHUB_PLANNER_TIMEOUT_SECONDS='300'
$env:AIHUB_SYSTEM_TIMEOUT_SECONDS='600'
# run goal with allowed_files=[docs/e2e-probe-result.md], forbidden_files=[src/, configs/, tasks.yaml, projects.yaml]
```

After run (success or timeout):
```powershell
python -c "from ai_workflow_hub.goal_runner import sync_goal_runs; sync_goal_runs('<goal_id>')"
```
