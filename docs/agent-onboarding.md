# Agent Onboarding

This checklist is for agents taking over `ai-workflow-hub`. Keep changes small, evidence-backed, and reversible.

## Start Here

1. Read `CLAUDE.md`.
2. Read `.claude/rules/codegraph-first.md`.
3. Read `.claude/memory/codegraph-pattern.md`.
4. Read only the relevant files under `memory/` for the current task.

## Before Editing

1. Use CodeGraph for code structure questions. Do not grep Python symbols first.
2. Run `aihub doctor --strict` when environment readiness matters.
3. Run `aihub codex readiness` before work that depends on Codex thinking.
4. Check `git status --porcelain` if the target project is a Git repository.
5. Identify destructive actions. Delete or move operations require backup first.

## Standard Verification

Use the narrowest useful check first, then broaden if risk justifies it:

```powershell
$env:PYTHONPATH='src'; python -m ai_workflow_hub.cli acceptance run smoke
$env:PYTHONPATH='src'; python -m ai_workflow_hub.cli acceptance run dynamic
$env:PYTHONPATH='src'; python -m ai_workflow_hub.cli acceptance run chain-truth
```

For any run, inspect:

- `state.json`
- `chain-evidence.json`
- `final-report.md`
- `safety-report.json`
- `diff.patch`
- `test-output.md`

## Non-Negotiables

- Do not push, merge, deploy, or close issues by default.
- Do not let DeepSeek/http fallback masquerade as Codex thinking.
- Do not use OpenCode as automatic fallback; it is degraded optional.
- Do not mark blocked or failed runs as target-chain success.
- Do not delete or move files without a backup manifest and hash.
- Do not call a goal batch passed unless run evidence, chain evidence, final report consistency, and diff scope all pass.

## Codex Readiness (v1.0+)

Before any apply, run:

```powershell
$env:HTTPS_PROXY="http://127.0.0.1:7897"
$env:PYTHONPATH='src'; python -m ai_workflow_hub.cli codex readiness --refresh
```

Gate: 3/3 probe exit=0, p95<60s, auth+proxy+stderr clean.
Cache: `runs/codex-readiness/latest.json` (10min TTL).
If not ready: apply BLOCKED. Check `HTTPS_PROXY` first.

## Destructive Action Rules (v1.0+)

| Action | Requirement |
|--------|-------------|
| Delete file | `safe_backup()` → backup_id + manifest + hash → then delete |
| Move file | `safe_move()` always backs up source first |
| worktree clean | Confirm passed status. Keep failed/blocked/human_required |
| run prune | `--dry-run` first. Keep summary by default |

Backup: `E:\Backups\deleted\{backup_id}`. Manifest: `manifest-{backup_id}.json`.

## Reporting (v1.0+)

Reports must include:

- Modified files with change descriptions
- Verification commands and output
- Current state vs target state
- Evidence paths / run IDs

No "OK" or "PASS" only reports.

## Full Memory Reference

### Gotcha (7 cards)
- `memory/gotcha_pipe_deadlock.md` — capture_output=True PIPE deadlock
- `memory/gotcha_win_cmd_encoding.md` — Windows .cmd needs shell=True
- `memory/gotcha_format_vs_replace.md` — .format() crashes on LLM braces
- `memory/gotcha_yaml_fix_dict.md` — YAML "fix_1: text" parsed as dict
- `memory/gotcha_chain_truth_false_positive.md` — chain-truth passed on failed Codex
- `memory/gotcha_state_json_log_pollution.md` — state.json polluted with full logs
- `memory/gotcha_codex_chatgpt_model_name.md` — ChatGPT auth rejects gpt-5.5-codex

### Pattern (6 cards)
- `memory/pattern_backend_calls.md` — standard 16-field schema
- `memory/pattern_chain_truth.md` — chain verification pattern
- `memory/pattern_readiness_gate.md` — Codex readiness gate
- `memory/pattern_backup_restore.md` — backup/restore requirements
- `memory/pattern_batch_first_goal.md` — batch-first goal orchestration
- `memory/pattern_run_verify_tristate.md` — evidence/chain/report tristate

### Decision (6 cards)
- `memory/decision_primary_claude.md` — Claude primary coding backend
- `memory/decision_go_langgraph.md` — LangGraph only schedules
- `memory/decision_codex_think.md` — Codex thinks, Claude codes
- `memory/decision_no_archon.md` — Archon no-go on Windows
- `memory/decision_opencode_degraded.md` — OpenCode degraded optional
- `memory/decision_no_silent_fallback.md` — all fallback must be marked
