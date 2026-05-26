"""Apply preflight — 所有正式 apply 前自动门禁."""

from __future__ import annotations

from typing import Any


def run_apply_preflight(project_id: str, task_id: str = "",
                        backend: str = "", risk: str = "low",
                        project_path: str = "") -> dict[str, Any]:
    """Apply 前门禁检查.

    返回: {allowed, result, checks, reason}
    """
    checks: list[dict] = []

    # 1. Backend healthy
    from .agent_client import backend_health_summary
    from .backend_health import _load_health
    from .config_loader import get_execution_policy

    health = _load_health()
    bp = get_execution_policy().get("backend_policy", {})
    degraded = bp.get("degraded_backends", [])
    allow_degraded = bp.get("allow_degraded_fallback", False)

    be = backend or "claude"
    be_h = health.get(be, {})
    be_score = be_h.get("health_score", 0)
    be_ok = be_score >= 0.5 or (be in degraded and allow_degraded)
    checks.append({"name": "backend_healthy", "status": "PASS" if be_ok else "BLOCKED",
                   "detail": f"{be} score={be_score}"})

    # 2. Policy all blocked
    rp = get_execution_policy().get("release_policy", {})
    blocked = all(not rp.get(k, False) for k in
                  ["allow_push", "allow_pr_create", "allow_merge", "allow_deploy", "allow_ci_fix"])
    checks.append({"name": "policy_all_blocked", "status": "PASS" if blocked else "WARN",
                   "detail": "all external write actions blocked"})

    # 3. Risk gate
    high_risk = risk == "high"
    checks.append({"name": "risk_gate", "status": "BLOCKED" if high_risk else "PASS",
                   "detail": f"risk={risk}"})

    # 4. Worktree clean
    if project_path:
        from .git_utils import is_worktree_clean
        clean = is_worktree_clean(project_path)
        checks.append({"name": "worktree_clean", "status": "PASS" if clean else "BLOCKED",
                       "detail": "clean" if clean else "dirty"})

    # 5. Not main/master
    if project_path:
        from .git_utils import is_main_branch
        main = is_main_branch(project_path)
        checks.append({"name": "not_main_branch", "status": "BLOCKED" if main else "PASS",
                       "detail": "main/master" if main else "safe"})

    # 6. Session gate
    from .session_gate import ensure_session_marker
    sm = ensure_session_marker(project_path or ".", created_by="preflight")
    checks.append({"name": "session_gate", "status": "PASS" if sm["complete"] else "WARN",
                   "detail": f"{sum(1 for v in sm.get('missing_fields',[]) if v)} fields missing"})

    # Determine overall
    blocked_checks = [c for c in checks if c["status"] == "BLOCKED"]
    if blocked_checks:
        return {"allowed": False, "result": "BLOCKED",
                "checks": checks,
                "reason": "; ".join(c["name"] for c in blocked_checks)}

    warn_checks = [c for c in checks if c["status"] == "WARN"]
    if warn_checks:
        return {"allowed": True, "result": "WARN",
                "checks": checks,
                "reason": "; ".join(c["name"] for c in warn_checks)}

    return {"allowed": True, "result": "PASS", "checks": checks, "reason": ""}
