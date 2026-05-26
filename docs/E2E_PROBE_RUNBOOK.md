# E2E Probe Runbook

How to safely run a minimal real E2E goal run and diagnose the result.

## Pre-flight

```powershell
$env:PYTHONPATH='src'
python -m ai_workflow_hub.cli backend probe
```

Expected: `Category: READY`. If not READY, see `docs/E2E_TIMEOUT_DECISION.md`.

## Run Minimal Probe

```powershell
$env:PYTHONPATH='src'
python -c "
from ai_workflow_hub.goal_store import create_goal, add_batch
from ai_workflow_hub.goal_runner import run_goal
g = create_goal('e2e-probe', ['test'], ['no delete'])
add_batch(g['goal_id'], 'probe', 'e2e probe',
    allowed_files=['main.py'],
    acceptance_gates={'tests': []},
    rollback_plan='git checkout main.py',
    included_tasks=['add # e2e-probe comment to main.py'])
print(f'Goal: {g[\"goal_id\"]}')
try:
    r = run_goal(g['goal_id'], 'test-repo')
    print(f'Status: {r.get(\"status\")}')
except Exception as e:
    print(f'Exception: {e}')
"
```

Default timeout budget: 120s (system `timeout` wrapper recommended).

## Artifact Paths

After the probe (success or timeout):

```
goals/<goal_id>/goal.json              — batch status, run_id, task_id
goals/<goal_id>/goal-report.md         — diagnostic summary with trace
goals/<goal_id>/goal-evidence.json     — structured evidence with trace + state_summary
runs/test-repo/<run_id>/state.json     — timeout_category, error_message, allowed_files
runs/test-repo/<run_id>/trace.json     — last_node, last_event, timeout_budget_seconds, prompt metrics
runs/test-repo/<run_id>/planner-prompt.md — full planner input (for size analysis only)
```

## Diagnosis

| Observation | Category | Action |
|------------|----------|--------|
| `state.json.timeout_category` = MODEL_TIMEOUT, `trace.json.last_node` = planner | Planner timed out | Check `trace.json.planner_prompt_chars`; see decision table |
| `state.json.timeout_category` = PROXY_TIMEOUT | Proxy timed out | Check proxy config/env |
| `state.json.status` = blocked | Pre-flight blocked | Check batch allowed_files |
| `goal.json.batch.run_id` = "" | run_id not recovered | Check `_discover_run_id` fallback |

## A/B Timeout Experiment

Compare planner performance at different budgets:

```powershell
# Budget A: 120s (minimal)
$env:AIHUB_PLANNER_TIMEOUT_SECONDS=120
python -c "..."  # same probe as above

# Budget B: 300s (extended)
$env:AIHUB_PLANNER_TIMEOUT_SECONDS=300
python -c "..."  # same probe as above
```

Config default is `configs/execution-policy.yaml` → `timeouts.planner_seconds: 600`.

Env override `AIHUB_PLANNER_TIMEOUT_SECONDS` takes precedence over config.
Remove env var to restore config default: `Remove-Item Env:\AIHUB_PLANNER_TIMEOUT_SECONDS`.

### Record per run

| Field | Source |
|-------|--------|
| timeout_budget_seconds | `trace.json` |
| elapsed_seconds | `trace.json` (post-model only) |
| timeout_source | `trace.json` |
| timeout_category | `state.json` |
| planner_prompt_chars | `trace.json` |
| result | `goal.json.batch.status` |

## Cleanup

```powershell
$env:PYTHONPATH='src'
python -m ai_workflow_hub.cli acceptance run cleanup
```

Dry-run only — lists test artifacts, never deletes.

## Do NOT

- Run E2E probe in default acceptance suites
- Delete artifacts without dry-run first
- Leave worktrees from failed probes (prune manually if needed)
