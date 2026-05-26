"""Diff 工具 — diff 解析、统计、过滤."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def parse_diff_summary(diff_text: str) -> dict[str, Any]:
    """解析 diff 生成摘要.

    Returns:
        {files_changed, additions, deletions, hunks}
    """
    if not diff_text:
        return {"files_changed": 0, "additions": 0, "deletions": 0, "hunks": 0}

    files = []
    additions = 0
    deletions = 0
    hunks = 0

    for line in diff_text.split("\n"):
        if line.startswith("--- ") or line.startswith("+++ "):
            parts = line.split(" ", 1)
            if len(parts) > 1 and parts[1].strip() != "/dev/null":
                fpath = parts[1].strip()
                if fpath not in files:
                    files.append(fpath)
        elif line.startswith("@@"):
            hunks += 1
        elif line.startswith("+") and not line.startswith("+++"):
            additions += 1
        elif line.startswith("-") and not line.startswith("---"):
            deletions += 1

    return {
        "files_changed": len(files),
        "additions": additions,
        "deletions": deletions,
        "hunks": hunks,
    }


def load_diff_from_file(diff_path: str) -> str:
    """从文件加载 diff."""
    p = Path(diff_path)
    if p.exists():
        return p.read_text(encoding="utf-8")
    return ""


def summarize_diff_for_report(diff_text: str, max_preview_lines: int = 100) -> str:
    """生成 diff 报告摘要（截断）."""
    lines = diff_text.split("\n")
    if len(lines) <= max_preview_lines:
        return diff_text
    head = "\n".join(lines[:max_preview_lines])
    return f"{head}\n\n... ({len(lines) - max_preview_lines} more lines truncated) ...\n"
