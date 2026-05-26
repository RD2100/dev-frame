# E2E Timeout A/B Experiment

**Date**: 2026-05-25
**Backend probe**: READY (proxy=api.deepseek.com/anthropic, latency=4.69s, Codex auth=chatgpt)

## Results

| Budget | Goal ID | Run ID | Planner Result | Elapsed | Full Result | Category |
|--------|---------|--------|---------------|---------|-------------|----------|
| 120s | goal-20260525-110203-e2e-probe-timeout-120 | run-20260525-110214-60a8e2 | never completed | N/A | OS kill at 180s | MODEL_TIMEOUT |
| 300s | goal-20260525-110203-e2e-probe-timeout-300 | run-20260525-110537-d1bbf3 | success (188s, exit=0) | 187.75s | OS kill at 360s (executor node) | PARTIAL_SUCCESS |
| 600s | skipped — early stop rule: 300s showed planner viable | — | — | — | — |

## Evidence Paths

### 120s Run
- state: `runs/test-repo/run-20260525-110214-60a8e2/state.json`
- trace: `runs/test-repo/run-20260525-110214-60a8e2/trace.json`
- goal: `goals/goal-20260525-110203-e2e-probe-timeout-120/goal.json`

### 300s Run
- state: `runs/test-repo/run-20260525-110537-d1bbf3/state.json`
- trace: `runs/test-repo/run-20260525-110537-d1bbf3/trace.json`
- plan: `runs/test-repo/run-20260525-110537-d1bbf3/plan.md`
- goal: `goals/goal-20260525-110203-e2e-probe-timeout-300/goal.json`

## Key Metrics (300s run)

| Metric | Value |
|--------|-------|
| timeout_budget_seconds | 300 |
| elapsed_seconds (planner) | 187.75 |
| planner_prompt_chars | 2586 |
| task_description_chars | 436 |
| allowed_files_count | 1 |
| forbidden_files_count | 4 |
| last_node | planner |
| last_event | response_received_0 |
| last_backend | codex_cli |
| last_model | gpt-5.5-codex |
| timeout_source | planner_codex_exec |
| planner exit_code | 0 |
| plan quality | correct — boundaries, forbidden files, rollback all properly identified |

## Analysis

- **120s budget**: Planner never completes. gpt-5.5-codex via deepseek proxy needs >120s.
- **300s budget**: Planner completes in ~188s (within 300s budget). Workflow advances to executor node but is killed by OS-level timeout (budget + 60s margin = 360s).
- **Planner budget 300s is the right minimum for this model/proxy combination.**
- Full workflow (planner + executor + reviewer + finalizer + fixer) needs more total time than planner budget alone.
- `planner_prompt_chars = 2586` is reasonable (well under 10K threshold).

## Recommendation

| Decision | Value | Reason |
|----------|-------|--------|
| Default planner timeout | **300s** | 120s too small, 600s likely unnecessary for planner alone |
| System-level timeout | **600s** | Planner needs ~200s, executor/reviewer need their own budget |
| Prompt compression | **not needed** | 2586 chars is well within healthy range |
| Planner model switch | **not recommended** | Model completes under 300s; latency is proxy, not model |
| More experiments | **optional** | Test full workflow with 600s system timeout |
