"""Human Gate 节点 — 暂停执行，等待人工决策.

审计强化:
- status=human_required 后必须保存 resume instructions
- human-gate.md 必须包含: 风险原因、diff 摘要、继续命令、拒绝处理
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..run_store import save_run_file


def build_human_gate_content(state: dict[str, Any]) -> str:
    """生成增强版 human-gate.md."""
    reason = _determine_gate_reason(state)
    diff_summary = _build_diff_summary(state)
    resume_cmd = _build_resume_command(state)

    return f"""# Human Gate — Manual Approval Required

## Why This Gate Was Triggered
{reason}

---

## Task Info
| Field | Value |
|-------|-------|
| **Task** | {state.get("task_title", "")} ({state.get("task_id", "")}) |
| **Project** | {state.get("project_name", "")} ({state.get("project_id", "")}) |
| **Risk Level** | {state.get("task_risk", "medium")} |
| **Run ID** | {state.get("run_id", "")} |
| **Thread ID** | {state.get("thread_id", state.get("run_id", ""))} |
| **Fix Round** | {state.get("fix_round", 0)} / {state.get("max_fix_rounds", 3)} |
| **Dry Run** | {state.get("dry_run", True)} |

---

## Diff Summary
{diff_summary}

---

## Review Result
**Verdict**: {state.get("review_result", "")}

{state.get("review_summary", "")}

---

## Safety Flags
| Flag | Status |
|------|--------|
| Dangerous Change | {"YES" if state.get("dangerous_change") else "no"} |
| Human Required | {"YES" if state.get("human_required") else "no"} |
| Protected Tests Deleted | Check `safety-report.md` |
| Forbidden Paths Touched | Check `safety-report.md` |

---

## What Needs Human Decision
1. Review the diff — are these changes safe and correct?
2. Decide whether to approve, reject, or modify the scope.
3. If approved, re-run with the resume command below.

---

## Resume Instructions

### To APPROVE and apply:
```bash
{resume_cmd}
```

### To REJECT:
```bash
# The task status will remain 'human_required'
# No changes have been applied to the working tree
aihub task add --project {state.get("project_id", "")} --title "REJECTED: {state.get("task_title", "")}" --description "Rejected from run {state.get("run_id", "")}" --risk {state.get("task_risk", "medium")}
```

### To MODIFY SCOPE:
1. Edit the task description in `tasks.yaml`
2. Re-run: `aihub run start --project {state.get("project_id", "")} --task {state.get("task_id", "")} --apply`

---

## Evidence Files
All evidence is in: `{state.get("run_dir", "")}/`

| File | Purpose |
|------|---------|
| `plan.md` | Original plan from planner |
| `execution-log.md` | Execution log from executor/fixer |
| `test-output.md` | Test command results |
| `diff.patch` | Full git diff |
| `review.md` | Reviewer analysis |
| `review.yaml` | Reviewer verdict (machine-readable) |
| `safety-report.md` | Safety check results |
| `state.json` | Full workflow state |
"""


def _determine_gate_reason(state: dict[str, Any]) -> str:
    """确定触发 human_gate 的原因 (带证据)."""
    reasons = []

    if state.get("task_risk") == "high":
        reasons.append("- **HIGH RISK TASK**: 高风险任务必须人工审批 (risk={})".format(state.get("task_risk")))

    if state.get("dangerous_change"):
        reasons.append("- **DANGEROUS CHANGE**: 变更涉及 security/auth/payment/config 等高风险领域")

    if state.get("human_required"):
        reasons.append("- **EXPLICIT REQUEST**: reviewer 或 planner 明确要求人工审查")

    review = state.get("review_result", "")
    if review == "human_gate":
        reasons.append("- **REVIEWER VERDICT**: reviewer 判定需要 human_gate")

    fix_round = state.get("fix_round", 0)
    max_rounds = state.get("max_fix_rounds", 3)
    if review == "fail" and fix_round >= max_rounds:
        reasons.append(f"- **FIX EXHAUSTED**: 修复轮次用尽 ({fix_round}/{max_rounds})，需人工介入")

    # 安全检查原因
    changed_files = state.get("changed_files", [])
    diff_lines = state.get("diff_line_count", 0)
    constraints = state.get("constraints", {})
    max_diff = constraints.get("max_diff_lines", 800)
    max_files = constraints.get("max_changed_files", 20)

    if diff_lines > max_diff:
        reasons.append(f"- **DIFF TOO LARGE**: {diff_lines} lines > {max_diff} limit")

    if len(changed_files) > max_files:
        reasons.append(f"- **TOO MANY FILES**: {len(changed_files)} files > {max_files} limit")

    if not reasons:
        reasons.append("- Manual review requested (reason unspecified)")

    return "\n".join(reasons)


def _build_diff_summary(state: dict[str, Any]) -> str:
    """生成 diff 摘要."""
    changed_files = state.get("changed_files", [])
    name_status = state.get("changed_files_status", {})
    diff_line_count = state.get("diff_line_count", 0)

    lines = [
        f"- **Files changed**: {len(changed_files)}",
        f"- **Diff lines**: {diff_line_count}",
        "",
    ]

    if name_status:
        lines.append("### Changed Files (by status)")
        lines.append("| Status | File |")
        lines.append("|--------|------|")
        # D 和 M/A 优先
        for fp in sorted(name_status):
            st = name_status[fp]
            icon = {"A": "+", "M": "~", "D": "-", "R": "→"}.get(st, st)
            lines.append(f"| {icon} ({st}) | `{fp}` |")
        lines.append("")
    elif changed_files:
        lines.append("### Changed Files")
        for f in changed_files:
            lines.append(f"- `{f}`")
        lines.append("")

    # diff 片段 (前 30 行)
    diff_text = state.get("git_diff", "")
    if diff_text:
        diff_preview = "\n".join(diff_text.split("\n")[:30])
        lines.append(f"### Diff Preview (first 30 lines)")
        lines.append("```diff")
        lines.append(diff_preview)
        if len(diff_text.split("\n")) > 30:
            remaining = len(diff_text.split("\n")) - 30
            lines.append(f"... ({remaining} more lines) ...")
        lines.append("```")

    return "\n".join(lines) if lines else "No diff available."


def _build_resume_command(state: dict[str, Any]) -> str:
    """构建 resume 命令 (正确的 CLI 形式: aihub run start ...)."""
    return (
        f"aihub run start "
        f"--project {state.get('project_id', '')} "
        f"--task {state.get('task_id', '')} "
        f"--apply"
    )


def human_gate_node(state: dict[str, Any]) -> dict[str, Any]:
    """Human Gate 节点.

    只在以下条件触发: high risk / dangerous_change / human_required flag.
    否则 pass-through 到 execute_node.
    """
    run_dir = state.get("run_dir", "")
    task_risk = state.get("task_risk", "medium")
    dangerous = state.get("dangerous_change", False)
    already_required = state.get("human_required", False)
    review_result = state.get("review_result", "")

    # 判定是否需要 gating
    fix_round = state.get("fix_round", 0)
    max_fix_rounds = state.get("max_fix_rounds", 3)
    fix_exhausted = review_result == "fail" and fix_round >= max_fix_rounds

    needs_gate = (
        task_risk == "high"
        or dangerous
        or already_required
        or review_result in ("human_gate", "blocked")
        or fix_exhausted
    )

    if not needs_gate:
        # 不需要 gate，直接通过
        return {"human_required": False, "status": state.get("status", "running")}

    # 需要 gate: 生成报告，停止
    content = build_human_gate_content(state)
    save_run_file(run_dir, "human-gate.md", content)

    return {
        "status": "human_required",
        "human_required": True,
    }
