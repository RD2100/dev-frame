# Operator Runbook Index

Quick navigation to operational procedures.

| Scenario | Document | Key Command |
|----------|----------|-------------|
| Verify all systems | this index | `acceptance run recovery-pipeline && acceptance run rc-check` |
| Recover from OS kill | `RECOVERY_PIPELINE_RUNBOOK.md` | `sync_goal_runs('<goal_id>')` |
| Review recovered evidence | `RECOVERY_PIPELINE_RUNBOOK.md` | `goal review-recovered <goal_id> --dry-run` |
| Run real reviewer | `RECOVERY_PIPELINE_RUNBOOK.md` | `goal review-recovered <goal_id> --apply` (requires ACK) |
| Clean test artifacts | `ARTIFACT_RETENTION_POLICY.md` | `acceptance run cleanup` (dry-run only) |
| Run real E2E | `E2E_PROBE_RUNBOOK.md` | requires ACK; planner=300s, system=600s |
| Adjust timeout | `E2E_TIMEOUT_DECISION.md` | config: `timeouts.planner_seconds` / env: `AIHUB_PLANNER_TIMEOUT_SECONDS` |
| Check assertion safety | `EXECUTION_REPORT_TEMPLATE.md` | `acceptance run assertion-check` |
| Release verification | `RELEASE_VERIFICATION_CHECKLIST.md` | 9 commands, no backend |
| Understand status machine | `STATUS_MACHINE.md` | batch/goal state transitions |
| Full workflow experiment | `E2E_FULL_WORKFLOW_EXPERIMENT.md` | v1.8-v1.10 experiment results |
| Next stage planning | `NEXT_STAGE_BACKLOG.md` | P1/P2/P3 backlog |
