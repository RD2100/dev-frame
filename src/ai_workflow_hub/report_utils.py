"""报告工具 — 格式化输出、markdown 生成."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def format_check_result(name: str, passed: bool, detail: str = "") -> str:
    """格式化检查结果为单行."""
    icon = "PASS" if passed else "FAIL"
    return f"[{icon}] {name}: {detail}"


def render_summary_table(data: list[dict[str, Any]]) -> str:
    """渲染简单 markdown 表格."""
    if not data:
        return "No data"
    headers = list(data[0].keys())
    lines = ["| " + " | ".join(headers) + " |"]
    lines.append("|" + "|".join(["---"] * len(headers)) + "|")
    for row in data:
        lines.append("| " + " | ".join(str(row.get(h, "")) for h in headers) + " |")
    return "\n".join(lines)


def status_icon(status: str) -> str:
    """状态图标."""
    icons = {
        "pending": "⏳",
        "running": "🔄",
        "passed": "✅",
        "failed": "❌",
        "blocked": "🚫",
        "human_required": "👤",
        "rejected": "⛔",
    }
    return icons.get(status, "❓")
