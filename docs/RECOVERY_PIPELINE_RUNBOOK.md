# Recovery Pipeline Runbook

How to recover from OS/system kill during a real E2E goal run.

## When to Use

- `goal run` output shows "timed out" or was killed
- `goal.json` batch has `status=running` but no active process
- Run directory exists but process is gone
- `state.json` shows `status=running` or empty `changed_files`

## Quick Start

```powershell
$env:PYTHONPATH='src'
cd D:\devFrame\ai-workflow-hub

# 1. Sync goal runs (fills missing run_id + recovers evidence)
python -c "from ai_workflow_hub.goal_runner import sync_goal_runs; print(sync_goal_runs('<goal_id>'))"

# 2. Dry-run reviewer gate (checks readiness, no backend)
python -m ai_workflow_hub.cli goal review-recovered <goal_id> --dry-run

# 3. Inspect evidence
# goals/<goal_id>/goal-report.md
# goals/<goal_id>/goal-evidence.json
# runs/test-repo/<run_id>/diff.patch
# runs/test-repo/<run_id>/trace.json
# runs/test-repo/<run_id>/state.json
```

## Run Real Reviewer (requires explicit ACK)

```powershell
# ONLY after dry-run shows ready_for_review=true
python -m ai_workflow_hub.cli goal review-recovered <goal_id> --apply
```

## Decision Table

| Observation | Verdict | Action |
|------------|---------|--------|
| `ready_for_review=true`, `diff_scope_ok=true` | Reviewable | ACK then `--apply` |
| `ready_for_review=true`, `diff_scope_ok=false` | Blocked | Out-of-scope files; investigate |
| `diff.patch` missing | Blocked | No evidence to review |
| `batch.status=passed`, `review_required=false` | Done | Already reviewed |
| `batch.status=blocked`, `review_required=true` | Waiting | Needs reviewer ACK |

## Forbidden

- Do NOT `git add` recovered files
- Do NOT commit/push recovered evidence
- Do NOT change `batch.status` to `passed` without reviewer gate
- Do NOT delete diff.patch or trace.json before review
- Do NOT call `--apply` without explicit ACK

## Artifact Paths

```text
goals/<goal_id>/goal.json              — batch status, task_id, run_id
goals/<goal_id>/goal-report.md         — diagnostic summary
goals/<goal_id>/goal-evidence.json     — structured trace + state_summary
runs/test-repo/<run_id>/diff.patch     — recovered diff (untracked included)
runs/test-repo/<run_id>/trace.json     — last_node, elapsed, budget, prompt metrics
runs/test-repo/<run_id>/state.json     — status, changed_files, review_required
```
