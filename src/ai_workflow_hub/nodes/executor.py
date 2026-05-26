"""Executor 节点 — 调用 OpenCode/DSV4 Pro 执行代码修改.

审计强化:
- dry-run 不得调用 OpenCode (有 edit 权限的 agent)
- dry-run 只生成 would-change 报告
- apply 才真实调用 opencode_run
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..config_loader import _hub_dir
from ..run_store import save_run_file
from ..git_utils import collect_all_diff_info, save_diff_patch


_ANSI_RE = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]')


def build_executor_prompt(state: dict[str, Any]) -> str:
    prompts_dir = _hub_dir() / "src" / "ai_workflow_hub" / "prompts"
    template = (prompts_dir / "executor.md").read_text(encoding="utf-8")
    dry_run = state.get("dry_run", True)
    apply_changes = state.get("apply_changes", False)

    mode_text = "APPLY — make real code changes now." if apply_changes else "DRY-RUN — describe changes only, do NOT modify files."
    allowed = state.get("allowed_files", [])
    forbidden = state.get("forbidden_files", [])
    allowed_str = "\n".join(f"- {f}" for f in allowed) if allowed else "(all files within scope)"
    forbidden_str = "\n".join(f"- {f}" for f in forbidden) if forbidden else "(none)"

    # 用 replace 不用 format — planner 输出可能含 { }
    result = template
    for key, val in [
        ("{task_title}", state.get("task_title", "")),
        ("{task_description}", state.get("task_description", "")),
        ("{plan}", state.get("plan", "")),
        ("{mode_text}", mode_text),
        ("{allowed_files_list}", allowed_str),
        ("{forbidden_files_list}", forbidden_str),
    ]:
        result = result.replace(key, str(val))

    # 注入 WORKFLOW.md 规则
    wf = state.get("workflow_text", "")
    if wf:
        result += "\n\n## Project Workflow Rules\n" + wf

    return result


def executor_node(state: dict[str, Any]) -> dict[str, Any]:
    """执行编码节点.

    dry-run: 只生成 would-change 报告，不调用 OpenCode.
    apply: 调用 OpenCode 执行真实修改，然后收集 diff + name-status.
    """
    run_dir = state.get("run_dir", "")
    project_path = state.get("project_path", "")
    worktree_path = state.get("worktree_path", project_path)
    model = state.get("executor_model", "deepseek/deepseek-v4-pro")
    dry_run = state.get("dry_run", True)
    apply_changes = state.get("apply_changes", False)
    allowed_files = state.get("allowed_files", [])
    forbidden_files = state.get("forbidden_files", [])
    plan = state.get("plan", "")

    cwd = worktree_path or project_path

    # 构建 prompt (用于 dry-run 报告)
    prompt = build_executor_prompt(state)
    save_run_file(run_dir, "executor-prompt.md", prompt)

    if dry_run and not apply_changes:
        # ---------- dry-run: 不调用 OpenCode ----------
        would_change = _generate_would_change_report(plan, allowed_files, forbidden_files)
        save_run_file(run_dir, "execution-log.md", would_change)

        return {
            "execution_log": would_change,
            "git_diff": "",
            "changed_files": [],
            "changed_files_status": {},
            "diff_line_count": 0,
        }

    # ---------- apply: 调用 coding agent ----------
    from ..agent_client import run_coding_agent, resolve_backend
    backend = resolve_backend(state.get("coding_backend"))

    # 保存 prompt 到文件（证据保留），通过 stdin 传入 OpenCode
    prompt_file = str(Path(run_dir) / "opencode-prompt.txt")
    Path(prompt_file).write_text(prompt, encoding="utf-8")

    # 执行前写 state.json
    state["current_node"] = "executor"
    from ..run_store import save_run_json
    save_run_json(run_dir, "state.json", state)

    result = run_coding_agent(
        backend=backend,
        prompt=prompt,
        model=model,
        cwd=cwd,
        timeout=600,
        stdout_log=str(Path(run_dir) / f"{backend}-stdout.log"),
        stderr_log=str(Path(run_dir) / f"{backend}-stderr.log"),
    )

    execution_log = result.get("stdout", "")
    stderr = result.get("stderr", "")
    exit_code = result.get("exit_code", -1)
    timed_out = result.get("timed_out", False)
    duration = result.get("duration_seconds", 0)
    fallback_from = ""
    fallback_reason = ""

    # Fallback: primary 失败 → 切备用 backend
    needs_fallback = (timed_out or exit_code not in (0, -1)) and backend != "opencode"
    if needs_fallback:
        fb_backend: str = "opencode"
        fallback_from = backend
        fallback_reason = "timeout" if timed_out else f"exit_code={exit_code}"

        fb_result = run_coding_agent(
            backend=fb_backend,
            prompt=prompt,
            model=model,
            cwd=cwd,
            timeout=600,
            stdout_log=str(Path(run_dir) / f"{fb_backend}-stdout.log"),
            stderr_log=str(Path(run_dir) / f"{fb_backend}-stderr.log"),
        )
        # 覆盖结果
        result = fb_result
        backend = fb_backend
        execution_log = result.get("stdout", "")
        stderr = result.get("stderr", "")
        exit_code = result.get("exit_code", -1)
        timed_out = result.get("timed_out", False)
        duration = result.get("duration_seconds", 0)

    # 收集 diff + name-status
    diff_info = collect_all_diff_info(cwd)
    git_diff = diff_info["diff_text"]
    changed_files = diff_info["changed_files"]
    name_status = diff_info["name_status"]
    diff_line_count = diff_info["diff_line_count"]

    save_diff_patch(cwd, str(Path(run_dir) / "diff.patch"))

    clean_stderr = _ANSI_RE.sub('', stderr).strip()

    be = {
        "executor": {
            "backend": backend,
            "model": model,
            "exit_code": exit_code,
            "timed_out": timed_out,
            "duration_seconds": duration,
            "command_preview": result.get("command_preview", ""),
            "stdout_log": str(Path(run_dir) / f"{backend}-stdout.log"),
            "stderr_log": str(Path(run_dir) / f"{backend}-stderr.log"),
            "fallback_from": fallback_from,
            "fallback_reason": fallback_reason,
        }
    }

    if timed_out:
        log_content = f"# Execution Log\n\n## Mode\napply (TIMEOUT {duration}s)\n\n## Error\n{clean_stderr[:500]}\n"
        save_run_file(run_dir, "execution-log.md", log_content)
        return {
            "execution_log": execution_log,
            "git_diff": git_diff, "changed_files": changed_files,
            "changed_files_status": name_status, "diff_line_count": diff_line_count,
            "error_message": f"TIMEOUT: opencode {duration}s",
            "status": "failed", "backend_calls": be,
        }

    is_actual_error = (exit_code not in (0, -1) or
                       'error' in clean_stderr.lower() or
                       'traceback' in clean_stderr.lower())

    if is_actual_error:
        log_content = f"# Execution Log\n\n## Mode\napply (FAILED)\n\n## Error\n{clean_stderr[:500]}\n\n## Output\n{execution_log[:500]}\n"
        save_run_file(run_dir, "execution-log.md", log_content)
        return {
            "execution_log": execution_log,
            "git_diff": git_diff, "changed_files": changed_files,
            "changed_files_status": name_status, "diff_line_count": diff_line_count,
            "error_message": clean_stderr[:500],
            "status": "failed", "backend_calls": be,
        }

    log_content = f"# Execution Log\n\n## Mode\napply ({duration}s)\n\n## Output\n{execution_log[:2000]}\n"
    save_run_file(run_dir, "execution-log.md", log_content)

    return {
        "execution_log": execution_log,
        "git_diff": git_diff, "changed_files": changed_files,
        "changed_files_status": name_status, "diff_line_count": diff_line_count,
        "error_message": "",
        "backend_calls": be,
    }


def _generate_would_change_report(
    plan: str, allowed_files: list[str], forbidden_files: list[str]
) -> str:
    """生成 dry-run 的 would-change 报告，不调用任何 agent."""
    now = datetime.now(timezone.utc).isoformat()
    lines = [
        "# Execution Log (DRY-RUN)",
        "",
        f"Generated: {now}",
        "",
        "## Mode",
        "dry-run — no code changes were made. No OpenCode agent was invoked.",
        "",
        "## Would Change",
        "The following changes WOULD be applied in --apply mode:",
        "",
    ]
    if allowed_files:
        lines.append("### Allowed Files (would modify):")
        for f in allowed_files:
            lines.append(f"- `{f}`")
        lines.append("")
    if forbidden_files:
        lines.append("### Forbidden Files (will NOT touch):")
        for f in forbidden_files:
            lines.append(f"- `{f}`")
        lines.append("")
    if plan:
        lines.append("### Plan Summary")
        lines.append(plan[:3000])
        lines.append("")

    return "\n".join(lines)
