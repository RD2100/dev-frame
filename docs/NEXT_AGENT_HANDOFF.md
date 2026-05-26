# Next Agent Handoff

## Current State (v1.17)

Recovery pipeline + reviewer gate + artifact cleanup + assertion safety are all green.
Full workflow E2E control-plane passes; data-plane needs user ACK.

### Do NOT re-evaluate

- rtk (uninstalled, ROI not justified)
- Archon (Windows unsupported, closed)
- agent-skills (patterns absorbed into coding-discipline/devprocess)
- unslop / Multica / DeepTutor (archived as reference)
- Planner timeout (300s confirmed via experiment)

### Must run first

```powershell
$env:PYTHONPATH='src'
cd D:\devFrame\ai-workflow-hub
python -m ai_workflow_hub.cli acceptance run recovery-pipeline
python -m ai_workflow_hub.cli acceptance run rc-check
python -m ai_workflow_hub.cli acceptance run assertion-check
python -m compileall -q src
```

### Key docs to read

1. `docs/v1.17-release-pack.md` — what's done, what's not
2. `docs/OPERATOR_RUNBOOK_INDEX.md` — which doc for which scenario
3. `docs/RECOVERY_PIPELINE_RUNBOOK.md` — how to recover OS-killed runs
4. `docs/ARTIFACT_RETENTION_POLICY.md` — what to keep, what can be cleaned
5. `docs/NEXT_STAGE_BACKLOG.md` — what to work on next

### Real E2E evidence

```
goal_id: goal-20260525-141154-e2e-full-workflow
run_id:  run-20260525-141203-572340
```

### Report format

All execution reports must follow `docs/EXECUTION_REPORT_TEMPLATE.md`:
- Executive Decision
- Reviewer Index
- Changed files
- Evidence (commands + output)
- Hard Stop Check
- Remaining Risks

### Next recommendation

Start from `docs/NEXT_STAGE_BACKLOG.md`. If user ACKs, run real E2E data-plane probe.
If user wants maintenance, enable cleanup apply mode. Do NOT add new tools or restart closed evaluations.
