"""Recovery — 失败/blocked/human_required 时给出可执行建议."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config_loader import _hub_dir


def analyze_recovery(run_id: str, project_id: str) -> dict[str, Any]:
    """分析 run 并给出恢复建议."""
    rd = _hub_dir() / "runs" / project_id / run_id
    sf = rd / "state.json"
    if not sf.exists():
        return {"error": f"State not found: {sf}"}

    s = json.loads(sf.read_text(encoding="utf-8"))
    status = s.get("status", "?")
    task_id = s.get("task_id", "")
    branch = s.get("current_branch", "")
    wt = s.get("worktree_path", "")
    blocking = _infer_blocking(s)

    suggestions: list[str] = []
    if status == "passed":
        suggestions = [
            "aihub run archive --project ... --run-id ...",
            "aihub worktree clean passed",
        ]
    elif status in ("failed", "blocked"):
        suggestions = [
            f"Read evidence: {rd}",
            "aihub run show --run-id " + run_id,
            "aihub task retry " + task_id,
            f"cd {wt} && git diff" if wt else "",
        ]
    elif status == "human_required":
        suggestions = [
            f"Review: {rd}/human-gate.md",
            f"Approve and re-run: aihub do --apply <task>",
        ]
    elif status == "running":
        suggestions = [
            "May be stale. Check duration.",
            "aihub task mark <id> failed --reason 'stale running'",
        ]

    suggestions = [s for s in suggestions if s]
    return {
        "run_id": run_id, "status": status, "task_id": task_id,
        "blocking": blocking, "worktree": wt, "branch": branch,
        "evidence_dir": str(rd), "suggestions": suggestions,
    }


def _infer_blocking(state: dict) -> str:
    err = state.get("error_message", "")
    if err and "timeout" in err.lower():
        return "executor (timeout)"
    if state.get("human_required"):
        return "human_gate"
    if state.get("review_result") == "blocked":
        return "reviewer"
    if state.get("fix_round", 0) >= state.get("max_fix_rounds", 3):
        return "fixer (rounds exhausted)"
    if state.get("test_exit_code", 0) not in (0, -1):
        return "tester"
    return "unknown"
