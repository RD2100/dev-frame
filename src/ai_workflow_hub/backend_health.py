"""Backend health tracking."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config_loader import _hub_dir
from .run_store import list_runs


def _health_dir() -> Path:
    d = _hub_dir() / "runs" / "backend-health"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _load_health() -> dict[str, Any]:
    f = _health_dir() / "backend-health.json"
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    return {}


def _save_health(data: dict[str, Any]) -> None:
    p = _health_dir() / "backend-health.json"
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def compute_health(backend: str) -> dict[str, Any]:
    """从历史 runs 计算 backend 健康度."""
    runs = list_runs(limit=200)
    stats = {"total": 0, "passed": 0, "blocked": 0, "failed": 0,
             "timeouts": 0, "durations": [], "last_error": ""}

    for r in runs:
        pid = r.get("project_id", "")
        rid = r.get("run_id", "")
        sf = _hub_dir() / "runs" / pid / rid / "state.json"
        if not sf.exists():
            continue
        s = json.loads(sf.read_text(encoding="utf-8"))
        bc = s.get("backend_calls", {})
        executor = bc.get("executor", {})
        if not isinstance(executor, dict):
            continue
        if executor.get("backend") != backend:
            continue

        stats["total"] += 1
        status = s.get("status", "")
        if status == "passed":
            stats["passed"] += 1
        elif status == "blocked":
            stats["blocked"] += 1
        elif status == "failed":
            stats["failed"] += 1

        if executor.get("timed_out"):
            stats["timeouts"] += 1

        dur = executor.get("duration_seconds")
        if isinstance(dur, (int, float)) and dur > 0:
            stats["durations"].append(dur)

        err = s.get("error_message", "")
        if err and not stats["last_error"]:
            stats["last_error"] = err[:200]

    total = stats["total"]
    durations = sorted(stats["durations"])
    health_score = 1.0

    if total > 0:
        health_score = stats["passed"] / total
        if stats["timeouts"] > 0:
            health_score -= 0.2 * stats["timeouts"] / total

    p95 = 0
    if durations:
        p95 = durations[int(len(durations) * 0.95)]

    result = {
        "backend": backend,
        "total_runs": total,
        "passed": stats["passed"],
        "blocked": stats["blocked"],
        "failed": stats["failed"],
        "timeouts": stats["timeouts"],
        "avg_duration_seconds": round(sum(durations) / len(durations), 1) if durations else 0,
        "p95_duration_seconds": round(p95, 1),
        "last_error": stats["last_error"][:200],
        "health_score": round(health_score, 2),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    return result


def update_all_health() -> dict[str, Any]:
    """更新所有 backend 健康度."""
    data = _load_health()
    for backend in ["claude", "opencode"]:
        data[backend] = compute_health(backend)
    data["_updated"] = datetime.now(timezone.utc).isoformat()
    _save_health(data)

    # Markdown
    lines = [
        "# Backend Health",
        f"Updated: {data['_updated']}",
        "",
        "| Backend | Runs | Passed | Blocked | Failed | Timeout | Avg(s) | P95(s) | Score |",
        "|---------|------|--------|---------|--------|---------|--------|--------|-------|",
    ]
    for b in ["claude", "opencode"]:
        h = data.get(b, {})
        lines.append(
            f"| {b} | {h.get('total_runs',0)} | {h.get('passed',0)} | {h.get('blocked',0)} | "
            f"{h.get('failed',0)} | {h.get('timeouts',0)} | {h.get('avg_duration_seconds',0)}s | "
            f"{h.get('p95_duration_seconds',0)}s | {h.get('health_score',0)} |")
    p = _health_dir() / "backend-health.md"
    p.write_text("\n".join(lines), encoding="utf-8")

    return data
