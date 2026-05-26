"""Daemon — 本地轮询任务调度."""

from __future__ import annotations

import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from .config_loader import get_execution_policy, _hub_dir
from .task_queue import (
    list_tasks, find_task, mark_task_running, mark_task_finished,
    mark_task_retry,
)
from .project_registry import find_project


def _daemon_log(msg: str) -> None:
    """写 daemon 日志."""
    log_dir = _hub_dir() / "runs" / "daemon"
    log_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    log_file = log_dir / f"daemon-{today}.log"
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    log_file.open("a", encoding="utf-8").write(f"[{ts}] {msg}\n")


def _daemon_config() -> dict[str, Any]:
    policy = get_execution_policy()
    return policy.get("daemon", {})


def find_runnable_tasks(project_id: str | None = None) -> list[dict[str, Any]]:
    """找 queued 任务，跳过非 queued 状态，过滤依赖，按 priority 排序."""
    tasks = list_tasks(status="queued")
    if project_id:
        tasks = [t for t in tasks if t.get("project_id") == project_id]

    # 显式排除所有非 queued 状态（防护：running 也不允许再次返回）
    excluded = {"running", "paused", "cancelled", "archived", "passed", "failed", "blocked", "human_required"}
    tasks = [t for t in tasks if t.get("status") not in excluded]

    priority_order = {"urgent": 0, "high": 1, "normal": 2, "low": 3}
    tasks.sort(key=lambda t: priority_order.get(t.get("priority", "normal"), 2))

    runnable = []
    for t in tasks:
        if dependencies_satisfied(t):
            runnable.append(t)
        else:
            _daemon_log(f"SKIP {t['id']}: dependencies unmet ({t.get('dependencies', [])})")
    return runnable


def dependencies_satisfied(task: dict[str, Any]) -> bool:
    deps = task.get("dependencies", []) or []
    for dep_id in deps:
        dep = find_task(dep_id)
        if not dep or dep.get("status") != "passed":
            return False
    return True


def mark_stale_running_tasks() -> int:
    """标记 stale running → failed."""
    cfg = _daemon_config()
    stale_min = cfg.get("stale_run_minutes", 30)
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=stale_min)
    count = 0

    for t in list_tasks(status="running"):
        updated = t.get("updated_at", "")
        try:
            t_updated = datetime.fromisoformat(updated)
        except (ValueError, TypeError):
            t_updated = datetime.min.replace(tzinfo=timezone.utc)

        if t_updated < cutoff:
            mark_task_finished(
                t["id"], "failed",
                run_id=t.get("last_run_id", ""),
                blocked_reason=f"stale running: exceeded {stale_min} min limit",
            )
            _daemon_log(f"STALE {t['id']}: running since {updated}, marked failed")
            count += 1
    return count


def run_queued_tasks(project_id: str | None = None) -> dict[str, Any]:
    """执行一批 queued tasks，返回启动数量和 ID 列表."""
    cfg = _daemon_config()
    max_concurrency = cfg.get("max_concurrency", 1)
    max_retries = cfg.get("max_retries", 1)

    runnable = find_runnable_tasks(project_id)
    started = 0
    started_ids: list[str] = []

    for t in runnable:
        if started >= max_concurrency:
            break

        # Check retry limit
        rc = t.get("retry_count", 0)
        if rc > max_retries:
            mark_task_finished(t["id"], "blocked",
                               blocked_reason=f"max retries ({max_retries}) exceeded")
            _daemon_log(f"BLOCK {t['id']}: retry_count={rc} > max={max_retries}")
            continue

        project = find_project(t["project_id"])
        if not project or not project.get("enabled", True):
            _daemon_log(f"SKIP {t['id']}: project not found or disabled")
            continue

        # 检查项目路径
        proj_path = project.get("path", "")
        if not Path(proj_path).exists():
            _daemon_log(f"SKIP {t['id']}: project path not found: {proj_path}")
            continue

        # **先标记 running，再执行** — 防止下个周期重复拾取
        run_id = f"daemon-{t['id']}"
        ok = mark_task_running(t["id"], run_id)
        if not ok:
            _daemon_log(f"SKIP {t['id']}: already running (mark_task_running returned False)")
            continue

        _daemon_log(f"START {t['id']} project={t['project_id']}")
        started += 1
        started_ids.append(t["id"])

        try:
            _execute_one_task(t)
        except Exception as e:
            _daemon_log(f"ERROR {t['id']}: {e}")
            # 确保异常任务不被卡在 running 状态
            mark_task_finished(t["id"], "failed",
                               blocked_reason=f"execution error: {e}")

    return {"started": started, "started_ids": started_ids}


def _execute_one_task(task: dict[str, Any]) -> None:
    """同步执行一个 task。调用现有的 run start 逻辑."""
    from .cli import _execute_run
    project_id = task["project_id"]
    task_id = task["id"]
    backend = task.get("coding_backend", "")
    # 默认 apply，不 run-tests（测试命令已在 workflow 中执行）
    _execute_run(project_id=project_id, task_id=task_id,
                 apply_changes=True, run_tests=False,
                 coding_backend=backend)


# ---------------------------------------------------------------------------
# pidfile / lock / heartbeat
# ---------------------------------------------------------------------------

_PIDFILE = _hub_dir() / "runs" / "daemon" / "daemon.pid"
_HEARTBEAT = _hub_dir() / "runs" / "daemon" / "daemon.heartbeat"


def _acquire_lock() -> bool:
    """单实例锁。返回 True 表示获取成功."""
    _PIDFILE.parent.mkdir(parents=True, exist_ok=True)
    if _PIDFILE.exists():
        try:
            old_pid = int(_PIDFILE.read_text().strip())
        except (ValueError, FileNotFoundError):
            old_pid = 0
        if old_pid:
            # Windows: 检查进程是否存在
            import ctypes
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(0x0400, False, old_pid)  # PROCESS_QUERY_INFORMATION
            if handle:
                kernel32.CloseHandle(handle)
                return False  # 进程存在
    return True


def _write_pidfile() -> None:
    import os as _os
    _PIDFILE.write_text(str(_os.getpid()))


def _write_heartbeat() -> None:
    _HEARTBEAT.write_text(datetime.now(timezone.utc).isoformat())


def _cleanup_lock() -> None:
    try: _PIDFILE.unlink()
    except Exception: pass
    try: _HEARTBEAT.unlink()
    except Exception: pass


def daemon_is_running() -> bool:
    """检查 daemon 是否在运行."""
    if not _PIDFILE.exists():
        return False
    try:
        old_pid = int(_PIDFILE.read_text().strip())
    except (ValueError, FileNotFoundError):
        return False
    if old_pid:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x0400, False, old_pid)
        if handle:
            kernel32.CloseHandle(handle)
            return True
    return False


def daemon_loop(project_id: str | None = None, once: bool = False) -> int:
    """主循环."""
    if not _acquire_lock():
        _daemon_log("DAEMON ABORT: another instance is running")
        return 1

    _write_pidfile()
    cfg = _daemon_config()
    poll_interval = cfg.get("poll_interval_seconds", 10)

    _daemon_log(f"DAEMON START poll={poll_interval}s, once={once}")
    from .audit import audit_log
    audit_log("daemon.start", result="STARTED", allowed=True)

    total_started = 0
    try:
        while True:
            _write_heartbeat()
            stale = mark_stale_running_tasks()
            if stale:
                _daemon_log(f"STALE marked: {stale}")

            rqt = run_queued_tasks(project_id)
            total_started += rqt["started"]

            if once:
                _daemon_log(f"DAEMON DONE (once): started {total_started}")
                _cleanup_lock()
                return 0

            _daemon_log(f"CYCLE: stale={stale}, started={started}")
            time.sleep(poll_interval)
    except KeyboardInterrupt:
        _daemon_log(f"DAEMON STOP (interrupt): total started {total_started}")
    finally:
        _cleanup_lock()
    return 0


# ---------------------------------------------------------------------------
# Soak
# ---------------------------------------------------------------------------

def daemon_soak(duration_minutes: int, projects: list[str] | None = None,
                mode: str = "plan") -> dict[str, Any]:
    """运行指定时长的 daemon soak 测试.

    Args:
        duration_minutes: 运行时长（分钟）
        projects: 项目 ID 列表
        mode: plan（只看不执行）| apply-safe（低风险 apply）

    Returns:
        soak report dict
    """
    import os as _os
    start_time = time.time()
    cfg = _daemon_config()
    poll_interval = cfg.get("poll_interval_seconds", 10)
    end_time = start_time + duration_minutes * 60

    simulated = (mode == "plan")
    _daemon_log(f"SOAK START duration={duration_minutes}m mode={mode} projects={projects}")

    cycle_count = 0
    tasks_seen = 0
    tasks_started = 0
    tasks_passed = 0
    tasks_blocked = 0
    tasks_failed = 0
    tasks_human_required = 0
    stale_running_count = 0
    errors = []
    end_reason = "duration_elapsed"

    wt_base = _hub_dir().parent / "aihub-worktrees"
    wt_before = len(list(wt_base.rglob("*"))) if wt_base.exists() else 0
    bk_before = _count_backups()
    log_dir = _hub_dir() / "runs" / "daemon"
    log_files_before = list(log_dir.glob("daemon-*.log")) if log_dir.exists() else []

    try:
        while time.time() < end_time:
            cycle_count += 1
            stale = mark_stale_running_tasks()
            stale_running_count += stale
            if stale:
                _daemon_log(f"SOAK CYCLE {cycle_count}: stale={stale}")

            # v0.3: 支持多项目过滤
            if projects:
                for pid in projects:
                    runnable = find_runnable_tasks(pid)
                    tasks_seen += len(runnable)

                    if mode == "plan":
                        tasks_started += len(runnable)
                        high_risk = sum(1 for t in runnable if t.get("risk") == "high")
                        tasks_human_required += high_risk
                        tasks_passed += len(runnable) - high_risk
                    else:
                        if _os.environ.get("HTTPS_PROXY") or _os.environ.get("ALL_PROXY"):
                            rqt = run_queued_tasks(pid)
                            tasks_started += rqt["started"]
                            # Count final statuses for started tasks
                            for tid in rqt.get("started_ids", []):
                                t = find_task(tid)
                                if t:
                                    st = t.get("status", "")
                                    if st == "passed": tasks_passed += 1
                                    elif st == "blocked": tasks_blocked += 1
                                    elif st == "failed": tasks_failed += 1
                                    elif st == "human_required": tasks_human_required += 1
                        else:
                            _daemon_log("SOAK: apply-safe blocked — no proxy for Codex readiness")
            else:
                runnable = find_runnable_tasks(None)
                tasks_seen += len(runnable)

                if mode == "plan":
                    tasks_started += len(runnable)
                    high_risk = sum(1 for t in runnable if t.get("risk") == "high")
                    tasks_human_required += high_risk
                    tasks_passed += len(runnable) - high_risk
                else:
                    if _os.environ.get("HTTPS_PROXY") or _os.environ.get("ALL_PROXY"):
                        rqt = run_queued_tasks(None)
                        tasks_started += rqt["started"]
                        for tid in rqt.get("started_ids", []):
                            t = find_task(tid)
                            if t:
                                st = t.get("status", "")
                                if st == "passed": tasks_passed += 1
                                elif st == "blocked": tasks_blocked += 1
                                elif st == "failed": tasks_failed += 1
                                elif st == "human_required": tasks_human_required += 1
                    else:
                        _daemon_log("SOAK: apply-safe blocked — no proxy for Codex readiness")

            time.sleep(poll_interval)

        _daemon_log(f"SOAK DONE: cycles={cycle_count}")

    except KeyboardInterrupt:
        end_reason = "interrupted"
        _daemon_log(f"SOAK STOP (interrupt): cycles={cycle_count}")
    except Exception as e:
        end_reason = "error"
        errors.append(str(e))
        _daemon_log(f"SOAK ERROR: {e}")

    wt_after = len(list(wt_base.rglob("*"))) if wt_base.exists() else 0
    bk_after = _count_backups()
    log_files_after = list(log_dir.glob("daemon-*.log")) if log_dir.exists() else []
    log_sizes = {f.name: f.stat().st_size for f in log_files_after}
    log_delta = sum(log_sizes.values()) - sum(f.stat().st_size for f in log_files_before)
    elapsed = round(time.time() - start_time)

    result = {
        "duration_minutes": duration_minutes,
        "actual_duration_seconds": elapsed,
        "mode": mode,
        "simulated": simulated,
        "project_ids": projects or [],
        "cycle_count": cycle_count,
        "tasks_seen": tasks_seen,
        "tasks_started": tasks_started,
        "tasks_passed": tasks_passed,
        "tasks_blocked": tasks_blocked,
        "tasks_failed": tasks_failed,
        "tasks_human_required": tasks_human_required,
        "stale_running_count": stale_running_count,
        "worktree_delta": wt_after - wt_before,
        "backup_delta": bk_after - bk_before,
        "daemon_log_delta_bytes": log_delta,
        "errors": errors,
        "exit_code": 1 if (errors or end_reason == "error") else 0,
        "end_reason": end_reason,
        "status": "failed" if (errors or end_reason == "error") else (
            "interrupted" if end_reason == "interrupted" else "passed"),
    }

    # Write structured report
    _write_soak_report(result)
    return result


def _write_soak_report(result: dict) -> None:
    import json as _j
    from datetime import datetime, timezone
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    soak_dir = _hub_dir() / "runs" / "daemon" / "soaks"
    soak_dir.mkdir(parents=True, exist_ok=True)

    jp = soak_dir / f"soak-{ts}.json"
    mp = soak_dir / f"soak-{ts}.md"

    jp.write_text(_j.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    result["report_json"] = str(jp)
    result["report_md"] = str(mp)

    lines = [
        f"# Daemon Soak Report",
        f"**Status**: {result['status']}",
        f"**Duration**: {result['actual_duration_seconds']}s (requested {result['duration_minutes']}m)",
        f"**Mode**: {result['mode']} {'(simulated)' if result['simulated'] else ''}",
        f"**Projects**: {', '.join(result.get('project_ids', [])) or 'all'}",
        f"**End**: {result['end_reason']}",
        f"**Exit**: {result['exit_code']}",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| cycles | {result['cycle_count']} |",
        f"| tasks_seen | {result['tasks_seen']} |",
        f"| tasks_started | {result['tasks_started']} |",
        f"| tasks_passed | {result['tasks_passed']} |",
        f"| tasks_blocked | {result['tasks_blocked']} |",
        f"| tasks_failed | {result['tasks_failed']} |",
        f"| stale | {result['stale_running_count']} |",
        f"| errors | {len(result.get('errors',[]))} |",
        f"| worktree_delta | {result['worktree_delta']} |",
        f"| backup_delta | {result['backup_delta']} |",
    ]
    if result.get("errors"):
        lines.append("")
        lines.append("## Errors")
        for e in result["errors"]:
            lines.append(f"- {e[:200]}")
    mp.write_text("\n".join(lines), encoding="utf-8")


def _count_backups() -> int:
    import os as _os
    bk = Path("E:/Backups/deleted")
    return len(list(bk.glob("manifest-*.json"))) if bk.exists() else 0
