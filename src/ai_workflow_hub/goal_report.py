"""Goal report — 聚合 batch evidence 生成 goal-report.md + goal-evidence.json."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .goal_store import load_goal
from .config_loader import _hub_dir


def _read_trace(run_id: str) -> dict:
    """Read trace.json from run directory. Returns empty dict on failure."""
    try:
        # scan runs/*/run_id/trace.json
        runs_dir = _hub_dir() / "runs"
        for proj_dir in runs_dir.iterdir():
            if not proj_dir.is_dir(): continue
            tf = proj_dir / run_id / "trace.json"
            if tf.exists():
                return json.loads(tf.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _read_trace_summary(run_id: str) -> str:
    """One-line trace summary for markdown table."""
    t = _read_trace(run_id)
    node = t.get("last_node", "") or "?"
    event = t.get("last_event", "") or "?"
    return f"{node}/{event}"


def _read_state_summary(run_id: str) -> dict:
    """Read diagnostic fields from state.json. Never raises."""
    try:
        runs_dir = _hub_dir() / "runs"
        for proj_dir in runs_dir.iterdir():
            if not proj_dir.is_dir(): continue
            sf = proj_dir / run_id / "state.json"
            if sf.exists():
                s = json.loads(sf.read_text(encoding="utf-8"))
                return {
                    "timeout_category": s.get("timeout_category", ""),
                    "error_message": s.get("error_message", ""),
                    "status": s.get("status", ""),
                    "allowed_files": s.get("allowed_files", []),
                }
    except Exception:
        pass
    return {}


def generate_goal_report(goal_id: str) -> dict[str, Any]:
    g = load_goal(goal_id)
    if not g:
        return {"error": f"Goal not found: {goal_id}"}

    batches = g.get("batches", [])
    evidence = {
        "goal_id": goal_id,
        "objective": g.get("objective", ""),
        "status": g.get("status", ""),
        "replan_count": g.get("replan_count", 0),
        "batches": [],
        "tokens_total": 0,
        "has_fallback": False,
        "opencode_called": False,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    report_lines = [
        f"# Goal Report: {g.get('objective','')[:100]}",
        f"**Goal ID**: {goal_id}",
        f"**Status**: {g.get('status','')}",
        f"**Replans**: {g.get('replan_count',0)}/{g.get('max_replans',2)}",
        "",
        "## Batches",
        "",
        "| # | Batch | Risk Domain | Risk | Status | Run ID | Task ID | Trace | Tasks |",
        "|---|-------|-------------|------|--------|--------|---------|-------|-------|",
    ]

    for b in batches:
        bid = b.get("batch_id", "?")
        rd = b.get("risk_domain", "?")
        rl = b.get("risk_level", "?")
        st = b.get("status", "?")
        run_id = b.get("run_id", "-")
        task_id = b.get("task_id", "-")
        tasks_n = len(b.get("included_tasks", []))
        trace_summary = _read_trace_summary(run_id) if run_id and run_id != "-" else "-"
        report_lines.append(
            f"| {bid} | {bid} | {rd} | {rl} | {st} | {run_id} | {task_id} | {trace_summary} | {tasks_n} |")

        b_ev = {
            "batch_id": bid, "risk_domain": rd, "risk_level": rl,
            "status": st, "run_id": run_id,
            "task_id": task_id,
            "changed_files": b.get("changed_files", []),
            "diff_scope_ok": b.get("diff_scope_ok", False),
            "review_result": b.get("review_result", ""),
            "evidence_recovered": b.get("evidence_recovered", False),
            "evidence_recovery_source": b.get("evidence_recovery_source", ""),
        }
        # Enrich with run trace + state diagnostics
        if run_id and run_id != "-":
            trace = _read_trace(run_id)
            b_ev["trace"] = trace
            b_ev["state_summary"] = _read_state_summary(run_id)
        evidence["batches"].append(b_ev)

    # Diagnostic summary section
    report_lines.append("")
    report_lines.append("## Diagnostics")
    report_lines.append("")
    for b in batches:
        run_id = b.get("run_id", "-")
        if run_id and run_id != "-":
            trace = _read_trace(run_id)
            ss = _read_state_summary(run_id)
            report_lines.append(f"### {b.get('batch_id','?')} (run: {run_id})")
            report_lines.append(f"- last_node: {trace.get('last_node','unknown')}")
            report_lines.append(f"- last_event: {trace.get('last_event','unknown')}")
            report_lines.append(f"- last_model: {trace.get('last_model','unknown')}")
            report_lines.append(f"- timeout_budget_seconds: {trace.get('timeout_budget_seconds','unknown')}")
            report_lines.append(f"- elapsed_seconds: {trace.get('elapsed_seconds','unknown')}")
            report_lines.append(f"- timeout_source: {trace.get('timeout_source','unknown')}")
            report_lines.append(f"- planner_prompt_chars: {trace.get('planner_prompt_chars','unknown')}")
            report_lines.append(f"- timeout_category: {ss.get('timeout_category','unknown')}")
            report_lines.append(f"- error_message: {ss.get('error_message','none')[:120]}")
            report_lines.append("")

    report_lines.append("")
    report_lines.append("## Success Criteria")
    for sc in g.get("success_criteria", []):
        report_lines.append(f"- {sc}")
    report_lines.append("")
    report_lines.append("## Constraints")
    for c in g.get("constraints", []):
        report_lines.append(f"- {c}")

    # Write
    gd = _hub_dir() / "goals" / goal_id
    gd.mkdir(parents=True, exist_ok=True)
    (gd / "goal-report.md").write_text("\n".join(report_lines), encoding="utf-8")
    (gd / "goal-evidence.json").write_text(
        json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8")

    return {"report_path": str(gd / "goal-report.md"),
            "evidence_path": str(gd / "goal-evidence.json"),
            "batches": len(batches)}
