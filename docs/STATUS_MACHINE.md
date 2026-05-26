# Goal Runner Status Machine

> Source: `goal_runner.py` v1.3. Last synced: 2026-05-25.
> Validated by: `acceptance run status-check`.

## Batch-Level States

| Pre-flight Check | Outcome | Batch Status | Goal Continues? |
|-----------------|---------|-------------|-----------------|
| `allowed_files` empty | Blocked immediately | `blocked` | Yes → next batch |
| `destructive_actions` set | Requires human approval | `human_required` | Yes → next batch |
| `risk_level == "high"` | Requires human approval | `human_required` | Yes → next batch |
| All pre-flight passed | Creates task, sets `running`, calls `_execute_run` | `running` | — (blocks until execution completes) |

## Post-Execution Gate

After `_execute_run` completes:

```
evidence_ok       = all 7 required files present
chain_trusted     = chain-evidence.json status not blocked/failed
fr_consistent     = final-report.md matches run status
diff_ok           = changed_files ⊆ allowed_files
batch_passed      = evidence_ok AND chain_trusted AND fr_consistent AND diff_ok
```

| batch_passed | Batch Status | Review Result |
|-------------|-------------|---------------|
| True | `passed` | `pass` |
| False | `failed` | aggregated reasons (evidence missing / chain NOT_TRUSTED / report inconsistent / out of scope) |

## Goal-Level States

After all batches processed:

| Condition | Goal Status |
|-----------|------------|
| All batches `passed` | `passed` |
| Some `failed` or `blocked` AND `replan_count < max_replans` | `needs_replan` |
| Some `failed` or `blocked` AND `replan_count >= max_replans` | `blocked` |

## State Diagram

```
BATCH LOOP
  │
  ├─ allowed_files empty? ──→ blocked ──→ next batch
  ├─ destructive_actions? ──→ human_required ──→ next batch
  ├─ risk_level=high? ──→ human_required ──→ next batch
  │
  └─ execute _execute_run()
       │
       └─ verify_run_evidence()
            │
            ├─ all 4 gates pass ──→ passed
            └─ any gate fails ──→ failed (with reasons)

GOAL FINAL
  ├─ all batches passed ──→ passed
  ├─ replan_count < max ──→ needs_replan
  └─ replan_count >= max ──→ blocked
```

## Example Scenarios

### Scenario 1: Missing allowed_files

Input: batch with `allowed_files=[]`
Result: batch → `blocked`, reason=`missing allowed_files`. Goal continues to next batch.
If all other batches pass → goal status depends on replan limits.

### Scenario 2: High Risk Batch

Input: batch with `risk_level="high"`, allowed_files set
Result: batch → `human_required`, reason=`high risk batch requires human gate`.
No code execution occurs. User must manually approve.

### Scenario 3: Failed Execution

Input: batch passes pre-flight, execution succeeds but evidence is incomplete
Result: `verify_run_evidence` returns `evidence_ok=False, chain_trusted=False`.
batch → `failed`, reason=`evidence missing; chain NOT_TRUSTED`.
Goal → `needs_replan` (if replans remain) or `blocked` (if exhausted).

## Audit Notes

- `replan_count` increments on `update_goal_status(goal_id, "needs_replan")`.
- `max_replans` default = 2, configurable per goal.
- `generate_goal_report()` is called unconditionally after all batches — even if goal is blocked. This is by design: every `goal run` produces an evidence package at `goals/<goal_id>/goal-report.md` + `goal-evidence.json`. Manual refresh via `aihub goal report <goal_id>` is also available.
- The `_execute_run` inside `run_goal` always uses `apply_changes=True, run_tests=False`.
