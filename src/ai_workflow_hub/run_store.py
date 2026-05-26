"""运行存储 — 管理 runs/ 目录."""

from __future__ import annotations

import json
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config_loader import _hub_dir


def create_run_dir(project_id: str) -> tuple[str, str]:
    """创建运行目录.

    Returns:
        (run_id, run_dir): 运行 ID 和目录路径.
    """
    run_id = f"run-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
    run_dir = _hub_dir() / "runs" / project_id / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_id, str(run_dir)


def save_run_file(run_dir: str, filename: str, content: str) -> str:
    """保存运行文件."""
    filepath = Path(run_dir) / filename
    filepath.parent.mkdir(parents=True, exist_ok=True)
    filepath.write_text(content, encoding="utf-8")
    return str(filepath)


def save_run_json(run_dir: str, filename: str, data: dict[str, Any]) -> str:
    """保存运行 JSON 文件."""
    filepath = Path(run_dir) / filename
    filepath.parent.mkdir(parents=True, exist_ok=True)
    filepath.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return str(filepath)


def load_run_file(run_dir: str, filename: str) -> str:
    """读取运行文件."""
    filepath = Path(run_dir) / filename
    if filepath.exists():
        return filepath.read_text(encoding="utf-8")
    return ""


def list_runs(project_id: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
    """列出最近的运行."""
    runs_base = _hub_dir() / "runs"
    result = []

    project_dirs = [runs_base / project_id] if project_id else list(runs_base.iterdir())

    for proj_dir in project_dirs:
        if not proj_dir.is_dir():
            continue
        for run_dir in sorted(proj_dir.iterdir(), reverse=True):
            if not run_dir.is_dir():
                continue
            final_report = run_dir / "final-report.md"
            state_file = run_dir / "state.json"

            info = {
                "run_id": run_dir.name,
                "project_id": proj_dir.name,
                "has_report": final_report.exists(),
            }
            if state_file.exists():
                try:
                    state = json.loads(state_file.read_text(encoding="utf-8"))
                    info["status"] = state.get("status", "unknown")
                    info["task_id"] = state.get("task_id", "")
                    info["created_at"] = state.get("created_at", "")
                except json.JSONDecodeError:
                    pass
            result.append(info)
            if len(result) >= limit:
                break
        if len(result) >= limit:
            break

    return result


def get_run_report(run_id: str, project_id: str) -> str:
    """读取 final-report.md."""
    run_dir = _hub_dir() / "runs" / project_id / run_id
    return load_run_file(str(run_dir), "final-report.md")
