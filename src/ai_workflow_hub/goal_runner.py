"""Goal runner v1.1 鈥?batch-first execution with boundary checks."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .goal_store import (
    load_goal, update_batch_status, update_goal_status,
    increment_replan, all_batches_passed, get_batch,
)
from .config_loader import _hub_dir

_logger = logging.getLogger(__name__)

# Batch statuses that mean a batch should NOT be re-executed.
# Consistent with task_queue._TERMINAL_STATUSES semantics.
_SKIP_BATCH_STATUSES = frozenset({"passed", "running", "human_required"})


def run_goal(goal_id: str, project_id: str, backend: str = "claude") -> dict[str, Any]:
    g = load_goal(goal_id)
    if not g:
        return {"error": f"Goal not found: {goal_id}"}

    update_goal_status(goal_id, "running")
    batches = g.get("batches", [])
    if not batches:
        update_goal_status(goal_id, "blocked")
        return {"error": "No batches in goal", "goal_id": goal_id}

    results = []
    # --- Per-batch retry config (v1.3) ---
    max_batch_retries = g.get("max_batch_retries", 1)  # default: 1 retry = 2 total attempts

    for b in batches:
        bid = b["batch_id"]

        # Idempotency: skip batches already in a non-restartable state
        current_status = b.get("status", "")
        if current_status in _SKIP_BATCH_STATUSES:
            _logger.info(
                "run_goal: skipping batch %s (status=%s, already in non-restartable state)",
                bid, current_status,
            )
            results.append({"batch": bid, "status": current_status,
                           "reason": f"skipped (already {current_status})"})
            continue

        # Pre-flight: batch boundary required
        if not b.get("allowed_files"):
            update_batch_status(goal_id, bid, "blocked", review_result="missing allowed_files")
            results.append({"batch": bid, "status": "blocked", "reason": "missing allowed_files"})
            continue

        # Destructive batch requires backup
        if b.get("destructive_actions"):
            update_batch_status(goal_id, bid, "human_required",
                                review_result="destructive actions require backup")
            results.append({"batch": bid, "status": "human_required", "reason": "destructive"})
            continue

        # High risk 鈫?human gate
        if b.get("risk_level") == "high":
            update_batch_status(goal_id, bid, "human_required",
                                review_result="high risk batch requires human gate")
            results.append({"batch": bid, "status": "human_required", "reason": "high risk"})
            continue

        # Build task description with boundary
        desc = _build_batch_description(b)
        from .task_queue import add_task
        task_id = add_task(project_id, b["objective"][:80], desc,
                          risk=b.get("risk_level", "low"))
        update_batch_status(goal_id, bid, "running", task_id=task_id)

        # --- Per-batch retry loop (v1.3) ---
        batch_attempt = 0
        while True:
            exec_error: str | None = None
            try:
                from .cli import _execute_run
                _execute_run(project_id=project_id, task_id=task_id,
                            apply_changes=True, run_tests=False,
                            coding_backend=backend,
                            task_allowed_files=b.get("allowed_files", []),
                            task_forbidden_files=b.get("forbidden_files", []))
            except Exception as e:
                exec_error = str(e)

            # Discover run_id (both success and exception paths)
            run_id = _discover_run_id(project_id, task_id)
            if run_id:
                new_status = "running" if exec_error is None else "failed"
                update_batch_status(goal_id, bid, new_status, run_id=run_id, task_id=task_id,
                                   review_result=exec_error or "")

            if exec_error is not None:
                batch_attempt += 1
                if batch_attempt <= max_batch_retries:
                    _logger.info("run_goal: batch %s failed with error, retry %d/%d: %s",
                                 bid, batch_attempt, max_batch_retries, exec_error)
                    b["batch_retry_count"] = batch_attempt
                    update_batch_status(goal_id, bid, "retrying", task_id=task_id,
                                       review_result=f"attempt {batch_attempt}: {exec_error}")
                    continue
                results.append({"batch": bid, "status": "failed", "error": exec_error,
                               "run_id": run_id or "", "batch_retry_count": batch_attempt})
                break

            if not run_id:
                batch_attempt += 1
                if batch_attempt <= max_batch_retries:
                    _logger.info("run_goal: batch %s no run_id, retry %d/%d",
                                 bid, batch_attempt, max_batch_retries)
                    b["batch_retry_count"] = batch_attempt
                    continue
                update_batch_status(goal_id, bid, "failed", review_result="no run_id after execute")
                results.append({"batch": bid, "status": "failed", "reason": "no run_id after execute",
                               "batch_retry_count": batch_attempt})
                break

            from .cli import verify_run_evidence
            v = verify_run_evidence(run_id, project_id)

            sf = _hub_dir() / "runs" / project_id / run_id / "state.json"
            changed = []
            if sf.exists():
                s = json.loads(sf.read_text(encoding="utf-8"))
                changed = s.get("changed_files", [])

            allowed = b.get("allowed_files", [])
            out_of_scope = [f for f in changed if f not in allowed]
            diff_ok = len(out_of_scope) == 0

            batch_passed = v["evidence_ok"] and v["chain_trusted"] and v["final_report_consistent"] and diff_ok

            if not batch_passed:
                batch_attempt += 1
                if batch_attempt <= max_batch_retries:
                    reasons = []
                    if not v["evidence_ok"]: reasons.append("evidence missing")
                    if not v["chain_trusted"]: reasons.append("chain NOT_TRUSTED")
                    if not v["final_report_consistent"]: reasons.append("report inconsistent")
                    if not diff_ok: reasons.append(f"out of scope: {out_of_scope}")
                    _logger.info("run_goal: batch %s evidence/scope check failed, retry %d/%d: %s",
                                 bid, batch_attempt, max_batch_retries, "; ".join(reasons))
                    b["batch_retry_count"] = batch_attempt
                    continue

                reasons = []
                if not v["evidence_ok"]: reasons.append("evidence missing")
                if not v["chain_trusted"]: reasons.append("chain NOT_TRUSTED")
                if not v["final_report_consistent"]: reasons.append("report inconsistent")
                if not diff_ok: reasons.append(f"out of scope: {out_of_scope}")
                if not reasons: reasons.append("unknown")
                update_batch_status(goal_id, bid, "failed", run_id=run_id,
                                   review_result="; ".join(reasons),
                                   changed_files=changed, diff_scope_ok=diff_ok)
                results.append({"batch": bid, "status": "failed", "run_id": run_id,
                               "reason": "; ".join(reasons), "batch_retry_count": batch_attempt})
                break

            update_batch_status(goal_id, bid, "passed", run_id=run_id,
                               review_result="pass", changed_files=changed,
                               diff_scope_ok=True)
            results.append({"batch": bid, "status": "passed", "run_id": run_id,
                           "batch_retry_count": batch_attempt})
            break

    # Final
    if all_batches_passed(goal_id):
        update_goal_status(goal_id, "passed")
    else:
        g2 = load_goal(goal_id)
        if g2:
            failed = [b for b in g2.get("batches", []) if b["status"] in ("failed", "blocked")]
            if failed and g2.get("replan_count", 0) < g2.get("max_replans", 2):
                update_goal_status(goal_id, "needs_replan")
            else:
                update_goal_status(goal_id, "blocked")

    # Generate goal report 鈥?always produce evidence, even on partial failure
    try:
        from .goal_report import generate_goal_report
        generate_goal_report(goal_id)
    except Exception:
        # Fallback: write minimal evidence so the goal is never untraceable
        from datetime import datetime, timezone as _tz
        gd = _hub_dir() / "goals" / goal_id
        gd.mkdir(parents=True, exist_ok=True)
        g_final = load_goal(goal_id) or {}
        minimal = {
            "goal_id": goal_id, "status": g_final.get("status", "?"),
            "batches": [{"batch_id": b.get("batch_id", "?"),
                         "run_id": b.get("run_id", ""),
                         "task_id": b.get("task_id", ""),
                         "status": b.get("status", "?")}
                        for b in g_final.get("batches", [])],
            "generated_at": datetime.now(_tz.utc).isoformat(),
            "fallback": True,
        }
        (gd / "goal-evidence.json").write_text(json.dumps(minimal, indent=2, ensure_ascii=False),
                                               encoding="utf-8")
        (gd / "goal-report.md").write_text(
            f"# Goal Report (fallback)\n\n**Goal ID**: {goal_id}\n**Status**: {g_final.get('status','?')}\n",
            encoding="utf-8")

    return {"goal_id": goal_id, "status": load_goal(goal_id).get("status", "?"),
            "results": results}


def _update_run_state_with_recovery(project_id: str, run_id: str,
                                    status: str) -> None:
    """Mark run state as recovered after OS/system kill."""
    sf = _hub_dir() / "runs" / project_id / run_id / "state.json"
    if not sf.exists():
        return
    try:
        s = json.loads(sf.read_text(encoding="utf-8"))
        if s.get("status") == "running":
            s["status"] = status
        s["evidence_recovered"] = True
        s["interrupted_workflow"] = True
        s["review_required"] = True
        from datetime import datetime, timezone as _tz
        s["evidence_recovery_at"] = datetime.now(_tz.utc).isoformat()
        sf.write_text(json.dumps(s, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def recover_run_evidence(project_id: str, run_id: str) -> dict[str, Any]:
    """Recover changed_files from diff.patch or worktree after OS/system kill.

    Priority: state.json (if nonempty) > diff.patch > worktree.
    Does NOT change run status. Does NOT git add.
    """
    rd = _hub_dir() / "runs" / project_id / run_id
    sf = rd / "state.json"

    # 1. Check existing state
    existing_files: list[str] = []
    if sf.exists():
        try:
            s = json.loads(sf.read_text(encoding="utf-8"))
            existing_files = s.get("changed_files", [])
        except Exception:
            pass
    if existing_files:
        return {"run_id": run_id, "recovered": False,
                "changed_files": existing_files,
                "source": "state", "warnings": []}

    # 2. Try diff.patch
    dp = rd / "diff.patch"
    recovered_files: list[str] = []
    recovered_status: dict[str, str] = {}
    source = ""
    warnings: list[str] = []

    if dp.exists() and dp.stat().st_size > 0:
        from .git_utils import parse_diff_changed_files
        diff_text = dp.read_text(encoding="utf-8")
        recovered_files, recovered_status = parse_diff_changed_files(diff_text)
        if recovered_files:
            source = "diff.patch"

    # 3. Fallback: worktree scan
    if not recovered_files:
        wt_path = ""
        if sf.exists():
            try:
                s = json.loads(sf.read_text(encoding="utf-8"))
                wt_path = s.get("worktree_path", "")
            except Exception:
                pass
        if wt_path and Path(wt_path).exists():
            from .git_utils import get_worktree_changes
            _, recovered_files, recovered_status, _ = get_worktree_changes(wt_path)
            if recovered_files:
                source = "worktree"

    if not recovered_files:
        return {"run_id": run_id, "recovered": False,
                "changed_files": [], "source": "",
                "warnings": ["no diff.patch or worktree evidence"]}

    # Write back to state.json
    try:
        s = json.loads(sf.read_text(encoding="utf-8")) if sf.exists() else {}
        s["changed_files"] = recovered_files
        s["changed_files_status"] = recovered_status
        s["evidence_recovered"] = True
        s["evidence_recovery_source"] = source
        sf.write_text(json.dumps(s, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        warnings.append(f"state write failed: {e}")

    return {"run_id": run_id, "recovered": True,
            "changed_files": recovered_files,
            "changed_files_status": recovered_status,
            "source": source, "warnings": warnings}


def sync_goal_runs(goal_id: str, project_id: str = "test-repo",
                   recover_evidence: bool = True) -> dict[str, Any]:
    """Recover missing batch run_ids AND evidence from run state.json via task_id matching.

    If recover_evidence=True, also runs recover_run_evidence() for diff/scope recovery.
    Safe after OS/system kill. Does NOT change batch status to passed.
    """
    g = load_goal(goal_id)
    if not g:
        return {"error": f"Goal not found: {goal_id}"}
    recovered_runs = 0
    recovered_evidence = 0
    for b in g.get("batches", []):
        bid = b["batch_id"]
        tid = b.get("task_id", "")
        if not tid:
            continue
        rid = b.get("run_id", "")
        # Fill missing run_id
        if not rid:
            runs_dir = _hub_dir() / "runs" / project_id
            if runs_dir.exists():
                for rd in sorted(runs_dir.iterdir(), reverse=True):
                    if not rd.is_dir():
                        continue
                    sf = rd / "state.json"
                    if not sf.exists():
                        continue
                    try:
                        s = json.loads(sf.read_text(encoding="utf-8"))
                        if s.get("task_id") == tid:
                            rid = s.get("run_id", "")
                            update_batch_status(goal_id, bid, s.get("status", b.get("status", "?")),
                                               run_id=rid, task_id=tid)
                            recovered_runs += 1
                            break
                    except Exception:
                        continue
        # Recover evidence from run dir
        if recover_evidence and rid:
            ev = recover_run_evidence(project_id, rid)
            if ev.get("changed_files"):  # always do scope check, even if state already populated
                changed = ev.get("changed_files", [])
                allowed = b.get("allowed_files", [])
                out = [f for f in changed if f not in allowed]
                diff_ok = len(out) == 0
                # Status reconciliation: stale running 鈫?blocked/review_required
                # Trigger on evidence availability, not on ev.recovered (may be False after prior recovery)
                curr_status = b.get("status", "?")
                is_stale_running = curr_status == "running"
                has_evidence = bool(changed)
                if is_stale_running and has_evidence:
                    new_status = "blocked"
                    review_prefix = "RECOVERED_EVIDENCE_REVIEW_REQUIRED"
                    if not diff_ok:
                        new_status = "failed"
                        review_prefix += f"; out of scope: {out}"
                    update_batch_status(goal_id, bid, new_status,
                                       run_id=rid, task_id=tid,
                                       changed_files=changed,
                                       diff_scope_ok=diff_ok,
                                       review_result=review_prefix,
                                       evidence_recovered=True,
                                       evidence_recovery_source=ev.get("source", ""))
                    # Also update run state
                    _update_run_state_with_recovery(project_id, rid, new_status)
                else:
                    review_extra = ""
                    if not diff_ok and out:
                        review_extra = f"; out of scope: {out}"
                    update_batch_status(goal_id, bid, b.get("status", "?"),
                                       run_id=rid, task_id=tid,
                                       changed_files=changed,
                                       diff_scope_ok=diff_ok,
                                       review_result=(b.get("review_result", "") + review_extra).strip("; "))
                recovered_evidence += 1

    # Regenerate evidence after recovery
    from .goal_report import generate_goal_report
    generate_goal_report(goal_id)
    return {"goal_id": goal_id, "batches": len(g.get("batches", [])),
            "recovered": recovered_runs, "recovered_evidence": recovered_evidence}


def _discover_run_id(project_id: str, task_id: str) -> str:
    """Find run_id for a task. Tries task.last_run_id first, then disk scan.

    Returns empty string if no run_id found.
    """
    from .task_queue import find_task
    task = find_task(task_id)
    run_id = task.get("last_run_id", "") if task else ""

    if run_id:
        return run_id

    # Fallback: scan runs directory for state.json with matching task_id
    from .run_store import list_runs
    recent = list_runs(limit=10)
    for r in recent:
        rid = r.get("run_id", "")
        sf = _hub_dir() / "runs" / project_id / rid / "state.json"
        if sf.exists():
            try:
                s = json.loads(sf.read_text(encoding="utf-8"))
                if s.get("task_id") == task_id:
                    return rid
            except Exception:
                continue
    return ""


def _build_batch_description(batch: dict) -> str:
    lines = [f"## Batch: {batch['batch_id']}",
             f"Risk domain: {batch.get('risk_domain','')} | Risk: {batch.get('risk_level','')}",
             f"Goal: {batch.get('objective','')}",
             "",
             "### Tasks to complete (same risk domain, execute together):"]
    for t in batch.get("included_tasks", []):
        lines.append(f"- {t}")
    lines.append("")
    lines.append("### ALLOWED FILES (do NOT touch anything else):")
    for f in batch.get("allowed_files", []):
        lines.append(f"- `{f}`")
    lines.append("")
    lines.append("### FORBIDDEN:")
    for f in batch.get("forbidden_files", []):
        lines.append(f"- `{f}`")
    lines.append("")
    lines.append("### Acceptance gates:")
    ag = batch.get("acceptance_gates", {})
    if ag.get("tests_to_run"):
        lines.append("Tests: " + ", ".join(ag["tests_to_run"]))
    if ag.get("diff_scope_check"):
        lines.append("DIFF SCOPE: only touch allowed_files. Do NOT modify any other file.")
    lines.append("")
    if batch.get("rollback_plan"):
        lines.append(f"Rollback: {batch['rollback_plan']}")
    return "\n".join(lines)

