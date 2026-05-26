# Release Verification Checklist

Run before declaring a release candidate. All commands must PASS. No real backend.

## Fast Gate (run every time)

```powershell
$env:PYTHONPATH='src'
cd D:\devFrame\ai-workflow-hub

python -m ai_workflow_hub.cli acceptance run recovery-pipeline
python -m ai_workflow_hub.cli acceptance run rc-check
python -m ai_workflow_hub.cli acceptance run cleanup-safety
python -m ai_workflow_hub.cli acceptance run assertion-check
python -m compileall -q src
```

Expected: all PASS. No "PASS ... False".

## Full Gate (pre-release)

```powershell
python -m ai_workflow_hub.cli acceptance run goal
python -m ai_workflow_hub.cli acceptance run smoke
python -m ai_workflow_hub.cli acceptance run dynamic
python -m ai_workflow_hub.cli acceptance run status-check
```

Expected: all PASS.

## Optional (requires ACK)

```powershell
python -m ai_workflow_hub.cli backend probe
```

Expected: Category READY.

## Hard Stop Conditions

If any check fails, do NOT proceed to release. Common failures:

| Failure | Fix |
|---------|-----|
| `tasks.yaml` parse error | Corrupted by race condition; check `config_loader.py` atomic write |
| `goal` suite crash | Stale fixture; re-run once |
| `assertion-check` FAIL | `PASS ... False` in recent report; fix assertion |
| `rc-check` FAIL | Config/doc mismatch; update docs or config |

## No-go Checklist

- [ ] No real backend called during verification
- [ ] No artifacts deleted during verification
- [ ] No commit/push during verification
- [ ] No Skill files modified
- [ ] tasks.yaml parse OK
