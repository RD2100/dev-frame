# Acceptance Flow Catalog

## Smoke (default)

| Field | Value |
|-------|-------|
| flow_id | `smoke` |
| command | `powershell -File scripts/acceptance/Run-Smoke.ps1` |
| expected_exit_code | 0 |
| expected_output | PASS or BLOCKED |
| artifact_paths | `$env:TEMP/acceptance-smoke-*/acceptance-report.md` |
| failure_signals | exit != 0, any FAILED, compileall non-zero |

## Goal Acceptance

| Field | Value |
|-------|-------|
| flow_id | `goal` |
| command | `$env:PYTHONPATH='src'; python -m ai_workflow_hub.cli acceptance run goal` |
| expected_exit_code | 0 |
| expected_output | X/X PASS |
| artifact_paths | `runs/acceptance/*/acceptance-report.md` |
| failure_signals | exit != 0, any FAIL in output |

## Recovery Pipeline

| Field | Value |
|-------|-------|
| flow_id | `recovery-pipeline` |
| command | `$env:PYTHONPATH='src'; python -m ai_workflow_hub.cli acceptance run recovery-pipeline` |
| expected_exit_code | 0 |
| expected_output | 16/16 PASS |
| artifact_paths | `runs/acceptance/*/acceptance-report.md` |
| failure_signals | exit != 0 |

## RC Check

| Field | Value |
|-------|-------|
| flow_id | `rc-check` |
| command | `$env:PYTHONPATH='src'; python -m ai_workflow_hub.cli acceptance run rc-check` |
| expected_exit_code | 0 |
| expected_output | 9/9 PASS |
| artifact_paths | `runs/acceptance/*/acceptance-report.md` |
| failure_signals | exit != 0 |
