"""GitHub Issue import — 只导入，不同步."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from typing import Any

from .task_queue import add_task, find_task, list_tasks
from .config_loader import save_tasks, get_tasks


def gh_issues(repo: str, label: str = "", limit: int = 20) -> list[dict[str, Any]]:
    """用 gh CLI 查询 issue."""
    cmd = ["gh", "issue", "list", "--repo", repo, "--limit", str(limit),
           "--state", "open", "--json", "number,title,body,labels,url"]
    if label:
        cmd.extend(["--label", label])

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            return []
        return json.loads(r.stdout)
    except Exception:
        return []


def import_github_issues(
    repo: str,
    label: str = "aihub",
    limit: int = 10,
    risk: str = "low",
) -> int:
    """导入 GitHub issue 为本地 task.

    Returns:
        新导入数量
    """
    issues = gh_issues(repo, label=label, limit=limit)
    if not issues:
        return 0

    existing_ids = {t.get("source_id", "") for t in list_tasks()
                    if t.get("source") == "github"}

    from .audit import audit_log
    audit_log("issue.import", result="STARTED", allowed=True, reason=f"repo={repo}, label={label}")
    imported = 0
    for issue in issues:
        gh_id = f"gh-{issue['number']}"
        if gh_id in existing_ids:
            continue

        title = issue["title"][:100]
        body = issue.get("body", "") or ""
        url = issue.get("url", "")

        # 判定 risk
        issue_risk = _infer_risk(title, body)

        add_task(
            project_id="",  # 导入时无项目绑定
            title=title,
            description=f"[Imported from {url}]\n\n{body[:2000]}",
            risk=issue_risk,
            priority="normal",
        )

        # 补充 source 字段
        data = get_tasks() or {}
        for t in data.get("tasks", []):
            if t.get("title") == title and not t.get("source"):
                t["source"] = "github"
                t["source_id"] = gh_id
                t["source_url"] = url
                save_tasks(data)
                break

        imported += 1

    return imported


def _infer_risk(title: str, body: str) -> str:
    """推断 issue 风险."""
    combined = (title + " " + body).lower()
    high_keywords = ["auth", "security", "payment", "production", "deploy",
                     "migration", "cert", "key", "secret", "permission"]
    medium_keywords = ["refactor", "api", "config", "state", "build"]

    for kw in high_keywords:
        if kw in combined:
            return "high"
    for kw in medium_keywords:
        if kw in combined:
            return "medium"
    return "low"
