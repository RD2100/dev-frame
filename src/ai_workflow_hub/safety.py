"""安全检查工具 — 基于 git diff --name-status 的硬拦截.

审计强化: 不依赖 prompt 约束，基于 git 事实做安全判定。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .config_loader import get_risk_policy, get_execution_policy
from .git_utils import detect_forbidden_paths, detect_protected_test_deletion


def check_forbidden_paths(
    name_status: dict[str, str], forbidden_patterns: list[str]
) -> tuple[bool, list[str]]:
    """硬拦截: forbidden path 变更 → 违规.

    Args:
        name_status: git diff --name-status 输出 {filepath: status}
        forbidden_patterns: .aiworkflow.yaml 中的 forbidden_paths

    Returns:
        (is_safe, violations)
    """
    violations = detect_forbidden_paths(name_status, forbidden_patterns)
    return len(violations) == 0, violations


def check_protected_tests(
    repo_path: str, protected_patterns: list[str]
) -> tuple[bool, list[str], list[str]]:
    """硬拦截: protected tests 删除 → blocked, 断言降低 → human_gate.

    Returns:
        (is_safe, deleted_tests, lowered_assertions)
    """
    deleted, lowered = detect_protected_test_deletion(repo_path, protected_patterns)
    is_safe = len(deleted) == 0 and len(lowered) == 0
    return is_safe, deleted, lowered


def check_diff_size(diff_line_count: int, max_diff_lines: int) -> tuple[bool, str]:
    """硬拦截: diff 超限 → human_gate."""
    if diff_line_count > max_diff_lines:
        return False, f"diff 行数 ({diff_line_count}) 超过限制 ({max_diff_lines})"
    return True, ""


def check_changed_files_count(changed_files_count: int, max_changed_files: int) -> tuple[bool, str]:
    """硬拦截: 文件数超限 → human_gate."""
    if changed_files_count > max_changed_files:
        return False, f"变更文件数 ({changed_files_count}) 超过限制 ({max_changed_files})"
    return True, ""


def check_risk_requires_human_gate(risk: str) -> bool:
    policy = get_risk_policy()
    categories = policy.get("risk_categories", {})
    cat = categories.get(risk, {})
    return cat.get("human_gate_required", False)


def check_shell_command_safety(command: str) -> tuple[bool, str]:
    from .shell_runner import is_shell_safe
    return is_shell_safe(command)


def produce_safety_report(
    run_dir: str,
    repo_path: str,
    name_status: dict[str, str],
    changed_files: list[str],
    forbidden_patterns: list[str],
    protected_patterns: list[str],
    diff_line_count: int,
    max_diff_lines: int,
    max_changed_files: int,
    risk: str,
) -> dict[str, Any]:
    """基于 git 事实生成安全检查报告.

    所有检查基于 git diff --name-status 的硬事实，不依赖 prompt 约束。
    """
    checks = []

    # 1. forbidden paths — 基于 name_status
    forbidden_ok, forbidden_violations = check_forbidden_paths(name_status, forbidden_patterns)
    checks.append({
        "name": "forbidden_paths",
        "passed": forbidden_ok,
        "detail": forbidden_violations if forbidden_violations else "none",
        "action": "human_gate" if not forbidden_ok else "pass",
    })

    # 2. protected tests — 基于 D status
    tests_ok, deleted_tests, lowered_assertions = check_protected_tests(repo_path, protected_patterns)
    checks.append({
        "name": "protected_tests",
        "passed": tests_ok,
        "detail": {"deleted": deleted_tests, "lowered_assertions": lowered_assertions},
        "action": "blocked" if deleted_tests else ("human_gate" if lowered_assertions else "pass"),
    })

    # 3. diff size
    diff_ok, diff_reason = check_diff_size(diff_line_count, max_diff_lines)
    checks.append({
        "name": "diff_size",
        "passed": diff_ok,
        "detail": diff_reason,
        "action": "human_gate" if not diff_ok else "pass",
    })

    # 4. changed files count
    files_ok, files_reason = check_changed_files_count(len(changed_files), max_changed_files)
    checks.append({
        "name": "changed_files_count",
        "passed": files_ok,
        "detail": files_reason,
        "action": "human_gate" if not files_ok else "pass",
    })

    # 5. risk human_gate
    risk_gate = check_risk_requires_human_gate(risk)
    checks.append({
        "name": "risk_human_gate",
        "passed": not risk_gate,
        "detail": f"risk={risk}, human_gate_required={risk_gate}",
        "action": "human_gate" if risk_gate else "pass",
    })

    # 6. name-status 摘要
    status_summary = {}
    for fp, st in name_status.items():
        status_summary.setdefault(st, []).append(fp)
    checks.append({
        "name": "name_status_summary",
        "passed": True,
        "detail": {st: len(files) for st, files in status_summary.items()},
        "action": "info",
    })

    # 7. sensitive file changes
    sensitive = _check_sensitive_files(name_status)
    checks.append({
        "name": "sensitive_files",
        "passed": sensitive["risk_level"] == "low",
        "detail": sensitive,
        "action": sensitive["action"],
    })

    # 8. test weakening detection
    test_weak = _check_test_weakening(repo_path, protected_patterns)
    checks.append({
        "name": "test_weakening",
        "passed": not test_weak["weakened"],
        "detail": test_weak,
        "action": "human_gate" if test_weak["weakened"] else "pass",
    })

    # 整体判断 (优先 blocked)
    if deleted_tests:
        overall = "blocked"
    elif not tests_ok and lowered_assertions:
        overall = "human_gate"
    elif test_weak.get("weakened"):
        overall = "human_gate"
    elif not forbidden_ok:
        overall = "human_gate"
    elif risk_gate:
        overall = "human_gate"
    elif sensitive.get("risk_level") == "high":
        overall = "human_gate"
    elif not diff_ok or not files_ok:
        overall = "human_gate"
    else:
        overall = "pass"

    report = {
        "checks": checks,
        "overall": overall,
        "summary": {
            "total_checks": len(checks),
            "passed": sum(1 for c in checks if c["passed"]),
            "failed": sum(1 for c in checks if not c["passed"]),
        },
    }

    from .run_store import save_run_json, save_run_file
    save_run_json(run_dir, "safety-report.json", {"safety_report": report})
    md_content = _render_safety_markdown(report)
    save_run_file(run_dir, "safety-report.md", md_content)

    return report


def _render_safety_markdown(report: dict[str, Any]) -> str:
    """生成 safety-report.md 人工可读版本."""
    lines = [
        "# Safety Report",
        "",
        f"**Overall**: {report.get('overall', 'unknown')}",
        "",
        f"Summary: {report['summary']['passed']}/{report['summary']['total_checks']} checks passed",
        "",
        "## Checks",
        "",
        "| Check | Result | Detail |",
        "|-------|--------|--------|",
    ]
    for c in report.get("checks", []):
        icon = "PASS" if c["passed"] else "FAIL"
        detail = str(c.get("detail", ""))[:120]
        lines.append(f"| {c['name']} | {icon} | {detail} |")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Risk signal helpers (v0.6 P4)
# ---------------------------------------------------------------------------

_SENSITIVE_PATTERNS = {
    "high": ["**/auth**", "**/payment**", "**/secret*", "**/cert*", "**/key*",
             "**/migration**", "**/deploy**", "**/production**", ".env*"],
    "medium": ["pyproject.toml", "requirements*.txt", "package.json",
               ".github/workflows/**", "Dockerfile", "docker-compose*"],
}


def _check_sensitive_files(name_status: dict[str, str]) -> dict:
    """检测敏感文件变更."""
    import fnmatch
    findings = []
    risk_level = "low"
    for fp in name_status:
        for level, patterns in _SENSITIVE_PATTERNS.items():
            for pat in patterns:
                if fnmatch.fnmatch(fp, pat):
                    findings.append(f"{fp} [{level}]")
                    if level == "high":
                        risk_level = "high"
                    elif level == "medium" and risk_level != "high":
                        risk_level = "medium"
                    break
    return {
        "findings": findings,
        "risk_level": risk_level,
        "action": "human_gate" if risk_level == "high" else ("warn" if risk_level == "medium" else "pass"),
    }


def _check_test_weakening(repo_path: str, protected_patterns: list[str]) -> dict:
    """检测测试弱化."""
    import fnmatch
    from .git_utils import get_diff_name_status
    name_status = get_diff_name_status(repo_path)

    weakened = False
    details: list[str] = []

    for fp in name_status:
        is_test = any(fnmatch.fnmatch(fp, p) for p in protected_patterns)
        if not is_test or name_status[fp] != "M":
            continue
        # Get file diff
        from .git_utils import _run_git
        ec, diff, _ = _run_git(repo_path, ["diff", "--unified=3", "--", fp])
        if ec != 0:
            continue
        removed = sum(1 for l in diff.split("\n") if l.startswith("-") and
                      ("assert" in l.lower() or "skip" in l.lower() or "xfail" in l.lower()))
        added = sum(1 for l in diff.split("\n") if l.startswith("+") and
                     ("assert" in l.lower() or "skip" in l.lower() or "xfail" in l.lower()))
        if removed > added and removed - added >= 2:
            weakened = True
            details.append(f"{fp}: -{removed}/+{added} asserts/skips/xfails")

    return {"weakened": weakened, "details": details}
