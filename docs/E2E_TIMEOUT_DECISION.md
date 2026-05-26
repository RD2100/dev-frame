# E2E Timeout Decision Table

How to interpret E2E timeout results and decide next action.

## Decision Matrix

| Observation | Category | Next Action |
|------------|----------|-------------|
| `backend probe` proxy unreachable | BACKEND_UNAVAILABLE | Fix proxy URL / network / credentials |
| `backend probe` proxy reachable, Codex auth fail | BACKEND_UNAVAILABLE | Re-authenticate Codex CLI |
| `backend probe` READY, planner completes <60s | READY | E2E viable; run full goal |
| `backend probe` READY, planner 60-300s, prompt <5K chars | SLOW_READY | Budget ok (600s planner timeout); monitor |
| `backend probe` READY, planner 60-300s, prompt >10K chars | PROMPT_TOO_LARGE | Compress planner input before retry |
| `backend probe` READY, planner >300s timeout, prompt <5K chars | MODEL_TIMEOUT | Increase budget or switch planner model |
| `backend probe` READY, planner >300s timeout, prompt >10K chars | PROMPT_TOO_LARGE | Compress planner input; retry with smaller prompt |
| Codex CLI not found | BACKEND_UNAVAILABLE | Install Codex CLI or use HTTP fallback |
| Multiple consecutive MODEL_TIMEOUT | PERSISTENT_TIMEOUT | Switch planner model; this one is not viable at current budget |

## Planner Model Strategy

| Scenario | Action | Reason |
|----------|--------|--------|
| 1 MODEL_TIMEOUT | Record, do NOT switch | Single timeout could be transient |
| 3 consecutive MODEL_TIMEOUT, prompt <5K chars | Test candidate model | Current model consistently unresponsive |
| 3 consecutive MODEL_TIMEOUT, prompt >10K chars | Compress prompt first, then retest | Prompt size may be the real cause |
| Candidate model completes but plan quality poor | Revert to original + compress prompt | Model quality > speed |
| proxy/auth unavailable | Fix environment; do NOT switch model | Model not the root cause |
| Budget increased to 900s and still MODEL_TIMEOUT | Switch planner model | Current model not viable at any reasonable budget |

### Candidate Models

| Model | When to try | Fallback |
|-------|-----------|----------|
| gpt-5.5-codex (current) | Default | — |
| deepseek-chat | gpt-5.5-codex persistently times out | gpt-5.5-codex |
| gpt-5.1-codex | gpt-5.5-codex unavailable | gpt-5.5-codex |

### When NOT to switch

- Prompt >10K chars and not yet compressed
- Only 1-2 timeouts
- Backend probe shows proxy/auth issues
- No candidate model configured in model-router.yaml

## Key Metrics

| Metric | Source | Healthy Range |
|--------|--------|---------------|
| timeout_budget_seconds | `trace.json` | 300 (planner codex_exec timeout, based on v1.8 experiment) |
| system_budget_seconds | `execution-policy.yaml` | 600 (full workflow) |
| planner_prompt_chars | `trace.json` | <10000 |
| workflow_text_chars | `trace.json` | <5000 |
| task_description_chars | `trace.json` | <2000 |
| allowed_files_count | `trace.json` | <20 |
| proxy_latency | `backend probe` | <5s |

## Rules

1. **Never classify timeout as pass.** If the workflow didn't complete, the goal is not passed.
2. **Budget before model.** Try increasing timeout budget before switching models.
3. **Prompt before budget.** If prompt is >10K chars, compress first — don't just throw more budget.
4. **One change at a time.** Adjust only one variable (budget, model, or prompt size) per test.
5. **Document every attempt.** Record goal_id, trace.json, and decision in the probe log.
