"""Audit log — 所有外部动作统一留证."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from .config_loader import _hub_dir


def _audit_path() -> str:
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    audit_dir = _hub_dir() / "runs" / "audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    return str(audit_dir / f"audit-{today}.jsonl")


def audit_log(
    action: str,
    result: str,
    allowed: bool = False,
    reason: str = "",
    project_id: str = "",
    task_id: str = "",
    run_id: str = "",
    **extra,
) -> None:
    """写审计日志."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "action": action,
        "allowed": allowed,
        "result": result,
        "reason": reason,
        "project_id": project_id,
        "task_id": task_id,
        "run_id": run_id,
        **extra,
    }
    # 过滤敏感字段
    entry = {k: v for k, v in entry.items()
             if not any(s in k.lower() for s in ("key", "secret", "token", "password"))}

    with open(_audit_path(), "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
