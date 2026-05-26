"""Batch create memory cards."""
import os

base = 'D:/devFrame/ai-workflow-hub/memory'
os.makedirs(base, exist_ok=True)

cards = {
    'gotcha_pipe_deadlock.md': {
        'type': 'gotcha',
        'tags': ['subprocess', 'windows', 'opencode'],
        'title': 'PIPE Deadlock with capture_output=True',
        'problem': 'subprocess.run(capture_output=True) creates stdout/stderr pipes. OpenCode large stderr (ANSI progress) fills pipe buffer → deadlock.',
        'fix': 'Replace subprocess.run(capture_output=True) with subprocess.Popen() + temp files.',
        'avoid': 'Never use capture_output=True for long-running subprocesses with significant stderr.',
    },
    'gotcha_win_cmd_encoding.md': {
        'type': 'gotcha',
        'tags': ['windows', 'encoding', 'subprocess'],
        'title': 'Windows .cmd Files Require shell=True',
        'problem': 'On Windows, codex/opencode are .cmd files. subprocess.run(["opencode"]) with shell=False → FileNotFoundError.',
        'fix': 'Use shell=True or full path to .cmd file.',
        'avoid': 'Always test subprocess calls on Windows with actual .cmd files.',
    },
    'gotcha_format_vs_replace.md': {
        'type': 'gotcha',
        'tags': ['python', 'prompt', 'planner'],
        'title': '.format() Crashes on LLM-Generated Braces',
        'problem': 'PLANNER output contains { or } from markdown code blocks → .format() raises KeyError.',
        'fix': 'Replace .format() with str.replace() for each placeholder.',
        'avoid': 'Never use .format() or f-strings to inject LLM-generated text.',
    },
    'gotcha_yaml_fix_dict.md': {
        'type': 'gotcha',
        'tags': ['yaml', 'reviewer', 'parsing'],
        'title': 'YAML Parses "fix_1: text" as Dict Not String',
        'problem': 'LLM output "fix_1: description" → YAML parses as {fix_1: "description"} (dict), not string → Pydantic crash.',
        'fix': '_normalize_fix() converts dict items to k:v strings.',
        'avoid': 'Always normalize YAML list items from LLM output.',
    },
    'gotcha_chain_truth_false_positive.md': {
        'type': 'gotcha',
        'tags': ['chain-truth', 'acceptance', 'verification'],
        'title': 'chain-truth Passed on Failed Codex Calls',
        'problem': 'acceptance chain-truth only checked backend_calls.backend name, not exit_code. codex_cli exit=1 was MATCH_TARGET.',
        'fix': 'Chain-truth now checks exit_code==0 + stderr for ERROR + run status.',
        'avoid': 'Never trust backend name without exit_code + stderr check.',
    },
    'gotcha_state_json_log_pollution.md': {
        'type': 'gotcha',
        'tags': ['state', 'json', 'evidence'],
        'title': 'state.json Polluted with Full Log Content',
        'problem': 'state.json used to store complete Codex stderr (ANSI codes). Unparseable, unreadable.',
        'fix': 'State stores: path to log, hash of log. Log content stays in .log files.',
        'avoid': 'Never put raw log output in state.json.',
    },
    'gotcha_codex_chatgpt_model_name.md': {
        'type': 'gotcha',
        'tags': ['codex', 'chatgpt', 'model'],
        'title': 'ChatGPT Auth Does Not Accept gpt-5.5-codex',
        'problem': 'Codex ChatGPT auth rejects "gpt-5.5-codex" → model not supported. HTTP fallback also rejects it.',
        'fix': 'Map gpt-5.5-codex → gpt-5.5 when auth_mode=chatgpt. Store requested_model + effective_model.',
        'avoid': 'Always record both model names in backend_calls.',
    },
    'pattern_backend_calls.md': {
        'type': 'pattern',
        'tags': ['backend_calls', 'schema', 'evidence'],
        'title': 'backend_calls Standard Schema',
        'problem': 'Every node must record backend call in standardized format with 16+ fields.',
        'fix': 'Standard: backend, requested_model, effective_model, exit_code, timed_out, duration, fallback_from, fallback_reason, auth_mode, provider, trusted_for_status, tokens_used, stdout/stderr log paths and hashes.',
        'avoid': 'Missing requested_model/effective_model split or missing fallback_from when http_fallback used.',
    },
    'pattern_chain_truth.md': {
        'type': 'pattern',
        'tags': ['chain-truth', 'verification', 'audit'],
        'title': 'Chain Truth Verification Pattern',
        'problem': 'Every run must prove actual thinking/execution chain, not claim from config.',
        'fix': 'Check: chain-evidence.json, exit_code, stderr ERROR scan, run status, model mapping. Only passed runs with exit=0 on all thinking nodes = MATCH_TARGET.',
        'avoid': 'Only checking backend name. Missing exit_code or stderr checks.',
    },
    'pattern_readiness_gate.md': {
        'type': 'pattern',
        'tags': ['codex', 'readiness', 'apply-gate'],
        'title': 'Codex Readiness Gate Pattern',
        'problem': 'apply must check Codex is actually working before allowing real code changes.',
        'fix': 'Gate: 3/3 probe exit=0, p95<60s, auth+proxy, stderr clean. Cache 10min in runs/codex-readiness/latest.json. Block apply if not ready.',
        'avoid': 'Only checking auth+proxy, not actual probe results.',
    },
    'pattern_backup_restore.md': {
        'type': 'pattern',
        'tags': ['backup', 'safety', 'destructive'],
        'title': 'Backup/Restore Pattern',
        'problem': 'All destructive actions must back up files first with stable backup_id.',
        'fix': 'safe_backup() → backup_id + manifest + hash. safe_delete() backs up first. restore_backup(backup_id) verifies hash.',
        'avoid': 'Destructive action without confirmed backup. Using timestamp instead of backup_id for restore.',
    },
    'pattern_batch_first_goal.md': {
        'type': 'pattern',
        'tags': ['goal', 'batch', 'risk-domain'],
        'title': 'Batch-First Goal Pattern',
        'problem': 'Goals broken into batches by risk_domain. Same-domain merged, cross-domain separate.',
        'fix': 'Each batch: allowed_files (REQUIRED), acceptance_gates (REQUIRED), rollback_plan (REQUIRED). Destructive domain → human_required. Batch passed = evidence+chain+report+diff all ok.',
        'avoid': 'Missing allowed_files or acceptance_gates silently accepted.',
    },
    'pattern_run_verify_tristate.md': {
        'type': 'pattern',
        'tags': ['run-verify', 'evidence', 'chain'],
        'title': 'Run Verify Tri-State Pattern',
        'problem': 'verify_run_evidence() is shared by run verify CLI and goal_runner.',
        'fix': 'Three independent checks: evidence_ok, chain_trusted, final_report_consistent. Used by both CLI and runner.',
        'avoid': 'Mixing "evidence missing" with "chain not trusted". Duplicating verify logic in multiple places.',
    },
    'decision_primary_claude.md': {
        'type': 'decision',
        'tags': ['backend', 'claude', 'architecture'],
        'title': 'Claude is Primary Coding Backend',
        'why': 'Claude 6/6 stress passed (1.0), OpenCode 1/6 (0.17).',
        'consequence': 'OpenCode = degraded_optional. No auto fallback.',
        'revisit': 'OpenCode probe 3/3 exit=0 p95<60s.',
    },
    'decision_go_langgraph.md': {
        'type': 'decision',
        'tags': ['architecture', 'langgraph', 'state-machine'],
        'title': 'LangGraph Only Does Scheduling',
        'why': 'Separation of concerns: scheduling vs execution. LangGraph is state machine, not LLM.',
        'consequence': 'No LLM calls from LangGraph nodes. All backend calls through codex/agent clients.',
        'revisit': 'New agent type needs integration or parallel execution.',
    },
    'decision_codex_think.md': {
        'type': 'decision',
        'tags': ['codex', 'thinking', 'architecture'],
        'title': 'Codex Handles Thinking, Claude Handles Coding',
        'why': 'Codex/GPT-5.5 excels at reasoning. Claude/DSV4 Pro excels at code changes.',
        'consequence': 'Codex readiness gate required. HTTPS_PROXY required. http_fallback must be marked.',
        'revisit': 'Codex auth mode changes or better thinking backend emerges.',
    },
    'decision_no_archon.md': {
        'type': 'decision',
        'tags': ['archon', 'windows', 'no-go'],
        'title': 'Archon PoC is No-Go on Windows',
        'why': 'Native Linux/WSL2 dependency. Git Bash not supported on Windows.',
        'consequence': 'Branch closed. Goal-batch system is the multi-step path.',
        'revisit': 'Project moves to native Linux or WSL2 trivially available.',
    },
    'decision_opencode_degraded.md': {
        'type': 'decision',
        'tags': ['opencode', 'backend', 'degraded'],
        'title': 'OpenCode is Degraded Optional Backend',
        'why': '1/6 stress passed. Provider integration issues (not model).',
        'consequence': 'Not default fallback. Explicit --backend only. degraded_optional in health.',
        'revisit': 'OpenCode probe 3/3 exit=0 p95<60s.',
    },
    'decision_no_silent_fallback.md': {
        'type': 'decision',
        'tags': ['fallback', 'transparency', 'chain'],
        'title': 'No Silent Fallback',
        'why': 'Chain claimed "Codex thinking" while using DeepSeek HTTP fallback. Discovered in chain-truth audit.',
        'consequence': 'backend_calls always has fallback_from + fallback_reason. chain-truth FAILS if thinking uses http_fallback.',
        'revisit': 'Multi-tier fallback with different trust levels intentionally designed.',
    },
}

# Write gotcha cards
for name, c in list(cards.items()):
    path = os.path.join(base, name)
    if c['type'] in ('pattern', 'decision'):
        continue
    content = f"""---
type: {c['type']}
tags: {c['tags']}
date: 2026-05-25
---

# {c['title']}

## Problem
{c['problem']}

## Fix
{c['fix']}

## Avoid
{c['avoid']}

## Evidence
See project development history. This card created from v0.1-v1.1 audit.
"""
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)

# Write pattern cards
for name, c in list(cards.items()):
    path = os.path.join(base, name)
    if c['type'] != 'pattern':
        continue
    content = f"""---
type: {c['type']}
tags: {c['tags']}
date: 2026-05-25
---

# {c['title']}

## Context
{c['problem']}

## Standard
{c['fix']}

## Avoid
{c['avoid']}

## Evidence
See project development history. This card created from v0.1-v1.1 audit.
"""
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)

# Write decision cards
for name, c in list(cards.items()):
    path = os.path.join(base, name)
    if c['type'] != 'decision':
        continue
    content = f"""---
type: {c['type']}
tags: {c['tags']}
date: 2026-05-25
---

# {c['title']}

## Decision
{c['title']}

## Why
{c['why']}

## Consequence
{c['consequence']}

## Revisit only if
{c['revisit']}
"""
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)

for name in sorted(os.listdir(base)):
    if name.endswith('.md') and name != 'README.md' and name != '_template.md':
        print(f'  {name}')
print('Done')
