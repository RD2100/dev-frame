"""Goal state model — multi-slice task orchestration."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config_loader import _hub_dir

GOALS_DIR = _hub_dir() / "goals"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def create_goal(objective: str, success_criteria: list[str] = None,
                constraints: list[str] = None) -> dict[str, Any]:
    import re
    safe = re.sub(r'[^a-zA-Z0-9\s-]', '', objective)[:30].strip().replace(' ', '-') or "task"
    goal_id = f"goal-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{safe}"
    g = {
        "goal_id": goal_id,
        "objective": objective,
        "status": "planned",
        "success_criteria": success_criteria or [],
        "constraints": constraints or [],
        "slices": [],
        "current_slice": 0,
        "run_ids": [],
        "replan_count": 0,
        "max_replans": 2,
        "max_fix_rounds": 3,
        "created_at": _now(),
        "updated_at": _now(),
    }
    _save(goal_id, g)
    return g


def load_goal(goal_id: str) -> dict[str, Any] | None:
    gf = GOALS_DIR / goal_id / "goal.json"
    if not gf.exists():
        return None
    return json.loads(gf.read_text(encoding="utf-8"))


def _save(goal_id: str, data: dict) -> None:
    d = GOALS_DIR / goal_id
    d.mkdir(parents=True, exist_ok=True)
    data["updated_at"] = _now()
    (d / "goal.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def add_slice(goal_id: str, title: str, description: str, risk: str = "low",
              dependencies: list[str] = None, acceptance: str = "") -> dict[str, Any]:
    g = load_goal(goal_id)
    if not g:
        return {"error": f"Goal not found: {goal_id}"}
    slice_id = f"slice-{len(g['slices'])+1:02d}"
    sl = {
        "slice_id": slice_id, "title": title, "description": description,
        "status": "planned", "risk": risk,
        "dependencies": dependencies or [], "acceptance": acceptance,
        "run_id": "", "review_result": "", "evidence_path": "",
    }
    g["slices"].append(sl)
    _save(goal_id, g)
    return sl


def update_slice_status(goal_id: str, slice_id: str, status: str,
                        run_id: str = "", review_result: str = "") -> bool:
    g = load_goal(goal_id)
    if not g:
        return False
    for sl in g["slices"]:
        if sl["slice_id"] == slice_id:
            sl["status"] = status
            if run_id:
                sl["run_id"] = run_id
                g["run_ids"].append(run_id)
            if review_result:
                sl["review_result"] = review_result
            _save(goal_id, g)
            return True
    return False


def update_goal_status(goal_id: str, status: str) -> bool:
    g = load_goal(goal_id)
    if not g:
        return False
    g["status"] = status
    _save(goal_id, g)
    return True


def increment_replan(goal_id: str) -> int:
    g = load_goal(goal_id)
    if not g:
        return -1
    g["replan_count"] = g.get("replan_count", 0) + 1
    _save(goal_id, g)
    return g["replan_count"]


def list_goals(limit: int = 20) -> list[dict[str, Any]]:
    if not GOALS_DIR.exists():
        return []
    results = []
    for d in sorted(GOALS_DIR.iterdir(), reverse=True):
        gf = d / "goal.json"
        if gf.exists():
            try:
                results.append(json.loads(gf.read_text(encoding="utf-8")))
            except Exception:
                pass
        if len(results) >= limit:
            break
    return results


def all_slices_passed(goal_id: str) -> bool:
    g = load_goal(goal_id)
    if not g or not g.get("slices"):
        return False
    return all(sl["status"] == "passed" for sl in g["slices"])


# ── v1.1 batch-first extensions ──

_RISK_DOMAINS = ["docs", "tests", "ui", "backend_logic", "data_migration",
                 "auth_security", "config_ci", "deletion_move", "external_integration"]


def add_batch(goal_id: str, risk_domain: str, objective: str, risk_level: str = "low",
              included_tasks: list[str] = None, allowed_files: list[str] = None,
              forbidden_files: list[str] = None, acceptance_gates: dict = None,
              rollback_plan: str = "", destructive_actions: list[str] = None) -> dict[str, Any]:
    g = load_goal(goal_id)
    if not g:
        return {"error": f"Goal not found: {goal_id}"}
    if not g.get("batches"):
        g["batches"] = []
    batch_id = f"batch-{len(g['batches'])+1:02d}"
    b = {
        "batch_id": batch_id, "risk_domain": risk_domain, "risk_level": risk_level,
        "objective": objective, "status": "planned",
        "included_tasks": included_tasks or [],
        "allowed_files": allowed_files or [],
        "forbidden_files": forbidden_files or [],
        "acceptance_gates": acceptance_gates or {},
        "rollback_plan": rollback_plan,
        "destructive_actions": destructive_actions or [],
        "run_id": "", "task_id": "", "review_result": "", "changed_files": [],
        "diff_scope_ok": False, "fix_round": 0,
    }
    g["batches"].append(b)
    _save(goal_id, g)
    return b


def update_batch_status(goal_id: str, batch_id: str, status: str,
                        run_id: str = "", task_id: str = "", review_result: str = "",
                        changed_files: list[str] = None, diff_scope_ok: bool = False,
                        evidence_recovered: bool = None,
                        evidence_recovery_source: str = "") -> bool:
    g = load_goal(goal_id)
    if not g or not g.get("batches"):
        return False
    for b in g["batches"]:
        if b["batch_id"] == batch_id:
            b["status"] = status
            if run_id: b["run_id"] = run_id; g.setdefault("run_ids", []).append(run_id)
            if task_id: b["task_id"] = task_id
            if review_result: b["review_result"] = review_result
            if changed_files is not None: b["changed_files"] = changed_files
            b["diff_scope_ok"] = diff_scope_ok
            if evidence_recovered is not None: b["evidence_recovered"] = evidence_recovered
            if evidence_recovery_source: b["evidence_recovery_source"] = evidence_recovery_source
            _save(goal_id, g)
            return True
    return False


def all_batches_passed(goal_id: str) -> bool:
    g = load_goal(goal_id)
    if not g or not g.get("batches"):
        return False
    return all(b["status"] == "passed" for b in g["batches"])


def get_batch(goal_id: str, batch_id: str) -> dict[str, Any] | None:
    g = load_goal(goal_id)
    if not g or not g.get("batches"):
        return None
    for b in g["batches"]:
        if b["batch_id"] == batch_id:
            return b
    return None
