"""任务队列 — v0.3 atomic control plane."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .config_loader import get_tasks, save_tasks, tasks_lock

_DEFAULTS = {
    "status": "queued",
    "priority": "normal",
    "dependencies": [],
    "coding_backend": "",
    "last_run_id": "",
    "retry_count": 0,
    "blocked_reason": "",
    "ci_report": "",
    "ci_fix_round": 0,
    "last_started_at": "",
    "lease_until": "",
}


def _normalize(task: dict[str, Any]) -> dict[str, Any]:
    """补全旧任务缺失字段."""
    for key, default in _DEFAULTS.items():
        if key not in task:
            task[key] = default
    if task.get("status") == "pending":
        task["status"] = "queued"
    return task


_VALID_STATUSES = {"queued", "running", "passed", "failed", "blocked",
                   "human_required", "cancelled", "paused", "archived"}

_TERMINAL_STATUSES = {"passed", "failed", "blocked", "cancelled",
                      "archived", "human_required"}


def list_tasks(status: str | None = None) -> list[dict[str, Any]]:
    """只读列出任务，不加锁."""
    data = get_tasks()
    tasks = data.get("tasks") or []
    tasks = [_normalize(t) for t in tasks if isinstance(t, dict)]
    if status:
        tasks = [t for t in tasks if t.get("status") == status]
    return tasks


def find_task(task_id: str) -> dict[str, Any] | None:
    """只读查找，不加锁."""
    for t in list_tasks():
        if t.get("id") == task_id:
            return t
    return None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def add_task(project_id: str, title: str, description: str = "",
             risk: str = "medium", priority: str = "normal",
             coding_backend: str = "") -> str:
    """添加任务 — 加锁 RMW."""
    import uuid
    with tasks_lock():
        data = get_tasks()
        if not data.get("tasks"):
            data["tasks"] = []

        task_id = f"task-{uuid.uuid4().hex[:8]}"
        now = _now()

        data["tasks"].append({
            "id": task_id, "project_id": project_id,
            "title": title, "description": description,
            "risk": risk, "status": "queued", "priority": priority,
            "dependencies": [], "coding_backend": coding_backend,
            "last_run_id": "", "retry_count": 0, "blocked_reason": "",
            "last_started_at": "", "lease_until": "",
            "created_at": now, "updated_at": now,
        })
        save_tasks(data)
    return task_id


def update_task_status(task_id: str, status: str) -> bool:
    """更新状态 — 加锁 RMW."""
    with tasks_lock():
        data = get_tasks()
        tasks = data.get("tasks") or []
        for t in tasks:
            if t.get("id") == task_id:
                t["status"] = status
                t["updated_at"] = _now()
                save_tasks(data)
                return True
    return False


def mark_task_running(task_id: str, run_id: str) -> bool:
    """标记运行中 — 加锁 RMW，仅 queued→running 转换.

    终态任务不可重新启动；已在运行中的任务不可重复标记.
    """
    with tasks_lock():
        data = get_tasks()
        tasks = data.get("tasks") or []
        for t in tasks:
            if t.get("id") == task_id:
                current = t.get("status", "")
                # 终态任务不可重新启动
                if current in _TERMINAL_STATUSES:
                    return False
                # 已经是 running 则不重复标记（防护重复启动）
                if current == "running":
                    return False
                t["status"] = "running"
                t["last_run_id"] = run_id
                t["last_started_at"] = _now()
                t["updated_at"] = _now()
                save_tasks(data)
                return True
    return False


def mark_task_finished(task_id: str, status: str, run_id: str = "",
                       blocked_reason: str = "") -> bool:
    """标记完成 — 加锁 RMW."""
    with tasks_lock():
        data = get_tasks()
        tasks = data.get("tasks") or []
        for t in tasks:
            if t.get("id") == task_id:
                t["status"] = status
                t["last_run_id"] = run_id or t.get("last_run_id", "")
                if blocked_reason:
                    t["blocked_reason"] = blocked_reason
                t["updated_at"] = _now()
                save_tasks(data)
                return True
    return False


def mark_task_retry(task_id: str) -> bool:
    """重新排队 — 加锁 RMW."""
    with tasks_lock():
        data = get_tasks()
        tasks = data.get("tasks") or []
        for t in tasks:
            if t.get("id") == task_id:
                t["status"] = "queued"
                t["retry_count"] = t.get("retry_count", 0) + 1
                t["blocked_reason"] = ""
                t["updated_at"] = _now()
                save_tasks(data)
                return True
    return False


def get_tasks_by_status(status: str) -> list[dict[str, Any]]:
    return list_tasks(status=status)


def pause_task(task_id: str) -> bool:
    """暂停任务 — 加锁 RMW."""
    with tasks_lock():
        data = get_tasks()
        for t in data.get("tasks", []):
            if t.get("id") == task_id and t.get("status") == "queued":
                t["status"] = "paused"
                t["updated_at"] = _now()
                save_tasks(data)
                return True
    return False


def resume_task(task_id: str) -> bool:
    """恢复任务 — 加锁 RMW."""
    with tasks_lock():
        data = get_tasks()
        for t in data.get("tasks", []):
            if t.get("id") == task_id and t.get("status") == "paused":
                t["status"] = "queued"
                t["updated_at"] = _now()
                save_tasks(data)
                return True
    return False


def cancel_task(task_id: str) -> bool:
    """取消任务 — 加锁 RMW."""
    with tasks_lock():
        data = get_tasks()
        for t in data.get("tasks", []):
            if t.get("id") == task_id and t.get("status") in ("queued", "paused"):
                t["status"] = "cancelled"
                t["updated_at"] = _now()
                save_tasks(data)
                return True
    return False


def archive_task(task_id: str) -> bool:
    """归档已完成/已取消的任务 — 加锁 RMW."""
    with tasks_lock():
        data = get_tasks()
        for t in data.get("tasks", []):
            if t.get("id") == task_id and t.get("status") in ("passed", "cancelled", "blocked", "failed"):
                t["status"] = "archived"
                t["updated_at"] = _now()
                save_tasks(data)
                return True
    return False
