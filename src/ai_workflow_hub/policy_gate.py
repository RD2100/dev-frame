"""Policy gate — 所有外部/高风险动作统一过策略门."""

from __future__ import annotations

from typing import Any

from .config_loader import get_execution_policy
from .audit import audit_log


def _policy() -> dict[str, Any]:
    return get_execution_policy().get("release_policy", {})


def check_allow(action: str, repo: str = "", project_id: str = "",
                task_id: str = "", run_id: str = "") -> tuple[bool, str]:
    """统一策略检查."""
    p = _policy()
    allowed = p.get(action, False)

    if not allowed:
        reason = f"BLOCKED_BY_POLICY: {action}=false"
        audit_log(action, result="BLOCKED_BY_POLICY", allowed=False,
                  reason=reason, project_id=project_id, task_id=task_id, run_id=run_id)
        return False, reason

    # Repo 白名单
    allowed_repos = p.get("allowed_repos", [])
    if repo and allowed_repos and repo not in allowed_repos:
        reason = f"BLOCKED_BY_POLICY: repo '{repo}' not in allowed_repos"
        audit_log(action, result="BLOCKED_BY_POLICY", allowed=False,
                  reason=reason, project_id=project_id, run_id=run_id)
        return False, reason

    # Denied labels (for issue import)
    denied = p.get("denied_labels", [])
    if denied:
        audit_log(action, result="WARN", allowed=True,
                  reason=f"denied_labels active: {denied}", project_id=project_id)

    audit_log(action, result="ALLOWED", allowed=True, project_id=project_id,
              task_id=task_id, run_id=run_id)
    return True, "OK"


def check_push(repo: str = "", project_id: str = "", run_id: str = "") -> tuple[bool, str]:
    return check_allow("allow_push", repo=repo, project_id=project_id, run_id=run_id)


def check_pr_create(repo: str = "", project_id: str = "", run_id: str = "") -> tuple[bool, str]:
    return check_allow("allow_pr_create", repo=repo, project_id=project_id, run_id=run_id)


def check_ci_fix(project_id: str = "", task_id: str = "") -> tuple[bool, str]:
    ci = get_execution_policy().get("ci", {})
    if not ci.get("allow_ci_fix", False):
        return False, "BLOCKED_BY_POLICY: ci.allow_ci_fix=false"
    return True, "OK"


def check_issue_import(repo: str = "", project_id: str = "") -> tuple[bool, str]:
    return check_allow("allow_issue_import", repo=repo, project_id=project_id)


def check_issue_comment(repo: str = "", project_id: str = "") -> tuple[bool, str]:
    return check_allow("allow_issue_comment", repo=repo, project_id=project_id)


def check_issue_close(repo: str = "", project_id: str = "") -> tuple[bool, str]:
    return check_allow("allow_issue_close", repo=repo, project_id=project_id)


def check_branch_delete(repo: str = "", project_id: str = "") -> tuple[bool, str]:
    return check_allow("allow_branch_delete", repo=repo, project_id=project_id)


def check_worktree_force_clean(project_id: str = "") -> tuple[bool, str]:
    return check_allow("allow_worktree_force_clean", project_id=project_id)


def check_merge() -> tuple[bool, str]:
    return False, "BLOCKED_BY_POLICY: allow_merge is permanently false"


def check_deploy() -> tuple[bool, str]:
    return False, "BLOCKED_BY_POLICY: allow_deploy is permanently false"
