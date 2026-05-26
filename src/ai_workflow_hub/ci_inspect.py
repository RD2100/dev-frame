"""CI inspect — 只读 GitHub Actions 状态."""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config_loader import _hub_dir
from .run_store import save_run_file


def check_gh_ci_auth() -> tuple[bool, str]:
    try:
        r = subprocess.run(["gh", "auth", "status"], capture_output=True, text=True, timeout=10)
        if r.returncode == 0:
            return True, "OK"
        return False, "BLOCKED_BY_ENV: gh not authenticated"
    except FileNotFoundError:
        return False, "BLOCKED_BY_ENV: gh CLI not found"


def pr_checks(repo: str, pr_number: int) -> list[dict[str, Any]]:
    """获取 PR check runs."""
    try:
        # gh pr checks --json may not be supported on all versions
        # Try JSON first, fallback to parsing text output
        r = subprocess.run(
            ["gh", "pr", "checks", "--repo", repo, str(pr_number)],
            capture_output=True, encoding="utf-8", errors="replace", timeout=30,
        )
        stdout = r.stdout.strip()
        if not stdout:
            return []
        # Parse tabular: name\tconclusion\tduration\turl
        checks = []
        for line in stdout.split("\n"):
            parts = line.split("\t")
            if len(parts) >= 3:
                conc = parts[1].strip()
                status = "completed" if conc in ("pass", "fail", "skipped") else "pending"
                checks.append({
                    "name": parts[0].strip(),
                    "status": status,
                    "conclusion": conc.upper() if conc == "pass" else
                                 "FAILURE" if conc == "fail" else
                                 "NEUTRAL" if conc == "skipped" else conc.upper(),
                    "detailsUrl": parts[3].strip() if len(parts) > 3 else "",
                })
        return checks
    except Exception:
        return []


def run_logs(repo: str, run_id: str, max_lines: int = 100) -> str:
    """获取 workflow run 日志摘要."""
    try:
        r = subprocess.run(
            ["gh", "run", "view", "--repo", repo, run_id, "--log"],
            capture_output=True, text=True, timeout=60,
        )
        return r.stdout[-4000:] if r.returncode == 0 else r.stderr[:500]
    except Exception as e:
        return f"ERROR: {e}"


def build_ci_report(repo: str, pr_number: int) -> str:
    """生成 ci-report.md."""
    checks = pr_checks(repo, pr_number)
    if not checks:
        return f"""# CI Report

**PR**: #{pr_number} in {repo}
**Time**: {datetime.now(timezone.utc).isoformat(timespec='seconds')}

## Result
CI_UNKNOWN — no check runs found. Check PR exists and has CI configured.
"""

    failed = [c for c in checks if c.get("conclusion") == "FAILURE"]
    passing = [c for c in checks if c.get("conclusion") == "SUCCESS"]
    pending = [c for c in checks if c.get("status") != "completed"]

    overall = "CI_PASS"
    if pending:
        overall = "CI_RUNNING"
    if failed:
        overall = "CI_FAIL"

    lines = [
        f"# CI Report",
        "",
        f"**PR**: #{pr_number} in {repo}",
        f"**Time**: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        f"**Result**: {overall}",
        "",
        "## Checks",
        "",
        "| Name | Status | Conclusion |",
        "|------|--------|------------|",
    ]
    for c in checks:
        lines.append(f"| {c.get('name','?')} | {c.get('status','?')} | {c.get('conclusion','?')} |")

    # Failed job details
    if failed:
        lines.append("")
        lines.append("## Failed Jobs")
        for f in failed:
            name = f.get("name", "?")
            url = f.get("detailsUrl", "")
            # Extract run ID from URL
            run_id = url.split("/")[-1] if "/" in url else ""
            lines.append(f"\n### {name}")
            lines.append(f"URL: {url}")
            if run_id:
                log_excerpt = run_logs(repo, run_id)
                lines.append(f"\n```\n{log_excerpt[:2000]}\n```")

    conclusion = {
        "CI_PASS": "- All checks pass. Proceed to review.",
        "CI_FAIL": "- CI failures detected. Review logs above.\n- Fix and re-run, or use `aihub ci fix --pr ...`.",
        "CI_RUNNING": "- CI is still running. Wait for completion.",
        "CI_UNKNOWN": "- No CI data. Check if PR has CI configured.",
    }

    lines.append("")
    lines.append("## Recommended Action")
    lines.append(conclusion.get(overall, "- Manual review required."))

    return "\n".join(lines)


def inspect_ci_pr(repo: str, pr_number: int) -> tuple[str, str]:
    """执行 CI inspect，返回 (report_path, overall)."""
    report = build_ci_report(repo, pr_number)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    report_dir = _hub_dir() / "runs" / "ci"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"ci-report-{ts}.md"
    report_path.write_text(report, encoding="utf-8")

    overall = "CI_UNKNOWN"
    for line in report.split("\n"):
        if line.startswith("**Result**:"):
            overall = line.split(":")[1].strip()
            break

    return str(report_path), overall


# ---------------------------------------------------------------------------
# CI fix
# ---------------------------------------------------------------------------

def check_ci_fix_policy() -> tuple[bool, str]:
    """检查 CI fix 策略."""
    from .config_loader import get_execution_policy
    policy = get_execution_policy()
    ci = policy.get("ci", {})
    if not ci.get("allow_ci_fix", False):
        return False, "BLOCKED_BY_POLICY: allow_ci_fix=false"
    return True, "OK"


def build_ci_fix_prompt(base_prompt: str, ci_report_path: str) -> str:
    """把 CI 失败注入修复 prompt."""
    try:
        ci_content = Path(ci_report_path).read_text(encoding="utf-8")
    except Exception:
        ci_content = "CI report not available."
    return base_prompt + f"\n\n## CI Failure Report\n{ci_content[:3000]}\n\nFix the CI failures described above."


def ci_fix_task(
    project_id: str,
    task_id: str,
    repo: str,
    pr_number: int,
) -> dict[str, Any]:
    """CI fix: 读取 CI 报告，注入 fixer prompt，调用 apply."""
    from .config_loader import get_execution_policy
    ci_policy = get_execution_policy().get("ci", {})
    max_rounds = ci_policy.get("max_ci_fix_rounds", 2)

    ok, reason = check_ci_fix_policy()
    if not ok:
        return {"run_id": "", "status": "blocked", "ci_results": reason}

    report_path, overall = inspect_ci_pr(repo, pr_number)
    if overall not in ("CI_FAIL",):
        return {"run_id": "", "status": "blocked",
                "ci_results": f"CI fix not applicable: {overall}"}

    # 读取 CI 报告并注入 state
    try:
        ci_report = Path(report_path).read_text(encoding="utf-8", errors="replace")
    except Exception:
        ci_report = overall

    # 通过 tasks.yaml 的 extra 字段传递 CI 报告
    from .task_queue import find_task, mark_task_finished, update_task_status
    task = find_task(task_id)
    if not task:
        return {"run_id": "", "status": "blocked", "ci_results": f"Task not found: {task_id}"}

    # 重置 task 状态并附上 CI 报告
    from .config_loader import get_tasks, save_tasks
    data = get_tasks() or {}
    for t in data.get("tasks", []):
        if t.get("id") == task_id:
            t["status"] = "queued"
            t["ci_report"] = ci_report[:5000]
            t["ci_fix_round"] = t.get("ci_fix_round", 0) + 1
            if t["ci_fix_round"] > max_rounds:
                t["status"] = "blocked"
                t["blocked_reason"] = f"CI fix rounds exceeded ({max_rounds})"
                save_tasks(data)
                return {"run_id": "", "status": "blocked",
                        "ci_results": f"CI fix rounds exceeded ({max_rounds})"}
            save_tasks(data)
            break

    return {"run_id": "", "status": "queued",
            "ci_results": f"Fix queued for {overall}"}
