"""Session gate — 自动确保 .aiworkflow/session/current.json 完整."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REQUIRED_FIELDS = {
    "status": "ready_for_file_edits",
    "startup_gate.bb_register": True,
    "startup_gate.bb_recent_knowledge": True,
    "startup_gate.active_memory_loaded": True,
    "startup_gate.project_conventions_loaded": True,
    "startup_gate.required_skills_loaded": True,
    "startup_gate.slice_plan_created": False,
}


def _marker_path(project_path: str) -> Path:
    return Path(project_path) / ".aiworkflow" / "session" / "current.json"


def ensure_session_marker(project_path: str, created_by: str = "aihub") -> dict[str, Any]:
    """确保 session marker 存在且完整。缺失则自动创建."""
    mp = _marker_path(project_path)
    mp.parent.mkdir(parents=True, exist_ok=True)

    if mp.exists():
        try:
            data = json.loads(mp.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    else:
        data = {}

    missing = []
    for key, default in REQUIRED_FIELDS.items():
        val = data
        parts = key.split(".")
        for p in parts[:-1]:
            val = val.setdefault(p, {})
        last = parts[-1]
        if last not in val:
            val[last] = default
            missing.append(key)

    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    data["auto_created_by"] = created_by

    mp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    return {
        "path": str(mp),
        "missing_fields": missing,
        "created": not mp.exists() if False else bool(missing),  # had changes
        "complete": len(missing) == 0,
    }
