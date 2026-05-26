"""Goal planner v1.1 — Codex 拆解为 risk-domain batches."""

from __future__ import annotations

import json
import yaml
from typing import Any

from .codex_client import codex_exec
from .goal_store import create_goal, add_batch, update_goal_status, load_goal


PLANNER_PROMPT = """You are a task planner. Break down this objective into batches grouped by risk domain.

First list ALL individual tasks, then group them into batches by risk_domain.
Same risk domain tasks can be merged into one batch. Cross-domain tasks MUST be separate batches.

Output ONLY valid YAML:

```yaml
goal:
  objective: "{objective}"
  success_criteria:
    - "criterion"
  constraints:
    - "never delete tests"
    - "never modify auth/payment/secrets"
batches:
  - batch_id: batch-01
    risk_domain: backend_logic
    risk_level: low
    objective: "Add function and test"
    included_tasks:
      - "Add new function to utils.py"
      - "Write unit test for the function"
    allowed_files:
      - "utils.py"
      - "tests/test_utils.py"
    forbidden_files:
      - ".env*"
      - "secrets/**"
    acceptance_gates:
      tests_to_run:
        - "python -m pytest tests/test_utils.py"
      static_checks:
        - "python -m py_compile utils.py"
      chain_evidence_required: true
      diff_scope_check: true
    rollback_plan: "git checkout utils.py tests/test_utils.py"
    destructive_actions: []
```

Risk domains: docs, tests, ui, backend_logic, data_migration, auth_security, config_ci, deletion_move, external_integration.

Rules:
- auth_security, data_migration, deletion_move, external_integration: risk_level=high, separate batches.
- Each batch must have allowed_files, acceptance_gates, rollback_plan.
- Missing allowed_files → batch blocked.
- Max 6 batches.
"""


def plan_goal(objective: str) -> dict[str, Any]:
    prompt = PLANNER_PROMPT.format(objective=objective)
    result = codex_exec(prompt=prompt, model="gpt-5.5-codex", timeout=300)

    stdout = result.get("stdout", "")
    if not stdout.strip():
        return {"error": "Codex returned empty plan", "raw": result}

    plan = _parse_yaml(stdout)
    if not plan:
        return {"error": "Failed to parse YAML plan", "raw": stdout}

    goal_data = plan.get("goal", {})
    batches = plan.get("batches", [])
    if not batches:
        return {"error": "Plan has no batches — missing allowed_files/acceptance_gates?", "parsed": plan}

    g = create_goal(
        objective=objective,
        success_criteria=goal_data.get("success_criteria", []),
        constraints=goal_data.get("constraints", []),
    )
    gid = g["goal_id"]
    blocked = []

    for b in batches:
        rd = b.get("risk_domain", "backend_logic")
        af = b.get("allowed_files", [])
        ag = b.get("acceptance_gates", {})
        rp = b.get("rollback_plan", "")

        if not af:
            blocked.append(f"{b.get('batch_id','?')}: missing allowed_files")
            continue
        if not ag:
            blocked.append(f"{b.get('batch_id','?')}: missing acceptance_gates")
            continue
        if not rp:
            blocked.append(f"{b.get('batch_id','?')}: missing rollback_plan")
            continue

        add_batch(
            gid,
            risk_domain=rd,
            objective=b.get("objective", "Untitled"),
            risk_level=b.get("risk_level", "low"),
            included_tasks=b.get("included_tasks", []),
            allowed_files=af,
            forbidden_files=b.get("forbidden_files", []),
            acceptance_gates=ag,
            rollback_plan=b.get("rollback_plan", ""),
            destructive_actions=b.get("destructive_actions", []),
        )

    if blocked:
        update_goal_status(gid, "blocked")
        return {"error": "Some batches blocked: " + "; ".join(blocked), "goal_id": gid}

    return load_goal(gid) or g


def _parse_yaml(text: str) -> dict[str, Any] | None:
    if "```yaml" in text:
        parts = text.split("```yaml", 1)
        if len(parts) > 1:
            text = parts[1].split("```", 1)[0]
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError:
        return None
