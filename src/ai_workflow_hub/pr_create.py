"""PR create — 从 run evidence 生成 GitHub PR。默认不 push/merge."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from .audit import audit_log
from .config_loader import get_execution_policy, _hub_dir
from .policy_gate import check_pr_create, check_push


def check_gh_auth() -> tuple[bool, str]:
    """检查 gh CLI 是否已认证."""
    try:
        r = subprocess.run(["gh", "auth", "status"], capture_output=True, text=True, timeout=10)
        if r.returncode == 0:
            return True, "gh CLI authenticated"
        return False, "BLOCKED_BY_ENV: gh not authenticated"
    except FileNotFoundError:
        return False, "BLOCKED_BY_ENV: gh CLI not found"


def build_pr_body(run_dir: str) -> str:
    """从 run 目录构建 PR body."""
    sf = Path(run_dir) / "state.json"
    if not sf.exists():
        return "No run evidence found."

    s = json.loads(sf.read_text(encoding="utf-8"))

    # Summary
    status = s.get("status", "?")
    review = s.get("review_result", "?")
    task_title = s.get("task_title", "?")
    run_id = s.get("run_id", "?")
    branch = s.get("current_branch", "?")
    wt = s.get("worktree_path", "") or "none"
    backend_calls = s.get("backend_calls", {})
    exec_info = backend_calls.get("executor", {})

    # Backend calls table
    bc_lines = ["| Node | Backend | Model | Exit | Timeout | Dur(s) |",
                "|------|---------|-------|------|---------|--------|"]
    for node, info in backend_calls.items():
        if isinstance(info, dict):
            bc_lines.append(
                f"| {node} | {info.get('backend','?')} | {info.get('model','?')} | "
                f"{info.get('exit_code','?')} | {info.get('timed_out',False)} | "
                f"{info.get('duration_seconds','?')} |")

    # Changed files
    changed = s.get("changed_files", [])
    changed_lines = "\n".join(f"- `{f}`" for f in changed) if changed else "- (none)"

    # Tests
    test_exit = s.get("test_exit_code", -1)
    test_status = "PASS" if test_exit == 0 else "FAIL" if test_exit > 0 else "N/A"

    # Remaining sections
    body = f"""## Summary
{task_title}

## Run Evidence
- **Run ID**: {run_id}
- **Status**: {status}
- **Review Result**: {review}
- **Coding Backend**: {exec_info.get("backend", "?")}
- **Branch**: {branch}
- **Worktree**: {wt}

## Changed Files
{changed_lines}

## Verification
- **Tests**: {test_status}
- **Safety Report**: exists
- **Failure Analysis**: {"exists" if (Path(run_dir) / "failure-analysis.md").exists() else "none"}

## Backend Calls
{chr(10).join(bc_lines)}

## Human Checklist
- [ ] Review diff
- [ ] Confirm tests pass
- [ ] Confirm no forbidden files touched
- [ ] Decide merge manually
"""
    return body


def preview_pr(project_id: str, run_id: str) -> str:
    """生成 PR preview."""
    run_dir = _hub_dir() / "runs" / project_id / run_id
    if not run_dir.exists():
        return f"Run directory not found: {run_dir}"
    return build_pr_body(str(run_dir))


def create_pr(
    project_id: str,
    run_id: str,
    repo: str,
    push: bool = False,
    base: str = "",
) -> dict[str, Any]:
    """创建 GitHub PR.

    Returns:
        {success, url, body, error}
    """
    # Policy gate
    ok, reason = check_pr_create(repo=repo, project_id=project_id, run_id=run_id)
    if not ok:
        return {"success": False, "url": "", "body": "", "error": reason}
    if push:
        ok, reason = check_push(repo=repo, project_id=project_id, run_id=run_id)
        if not ok:
            return {"success": False, "url": "", "body": "", "error": reason}

    # Auth check
    ok, reason = check_gh_auth()
    if not ok:
        return {"success": False, "url": "", "body": "", "error": reason}

    # Build body
    body = preview_pr(project_id, run_id)
    if "Run directory not found" in body:
        return {"success": False, "url": "", "body": "", "error": body}

    # Detect base branch from remote
    if not base:
        try:
            r = subprocess.run(["gh", "api", f"repos/{repo}", "--jq", ".default_branch"],
                              capture_output=True, text=True, timeout=10)
            base = r.stdout.strip() or "main"
        except Exception:
            base = "main"

    s = json.loads((_hub_dir() / "runs" / project_id / run_id / "state.json").read_text(encoding="utf-8"))
    branch = s.get("current_branch", "")

    if push:
        try:
            # First push the branch
            r = subprocess.run(
                ["git", "push", "origin", branch],
                capture_output=True, text=True, timeout=30,
                cwd=s.get("base_project_path", s.get("project_path", "")),
            )
            if r.returncode != 0:
                return {"success": False, "url": "", "body": "", "error": f"Push failed: {r.stderr}"}
        except Exception as e:
            return {"success": False, "url": "", "body": "", "error": f"Push error: {e}"}

    # Create PR via gh CLI
    try:
        title = s.get("task_title", "AI work")[:100]
        cmd = ["gh", "pr", "create", "--repo", repo,
               "--head", branch, "--base", base,
               "--title", title, "--body", body]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            return {"success": False, "url": "", "body": body, "error": r.stderr}
        url = r.stdout.strip()
        audit_log("pr.create", result="CREATED", allowed=True, reason=url,
                  project_id=project_id, run_id=run_id)
        return {"success": True, "url": url, "body": body, "error": ""}
    except Exception as e:
        return {"success": False, "url": "", "body": body, "error": str(e)}
