"""Fixer 节点 — 修复测试失败或 reviewer 指出的 blocking fixes.

审计: fixer 在 dry-run 时不调用 OpenCode，只生成 would-fix 报告。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..config_loader import _hub_dir
from ..run_store import save_run_file
from ..git_utils import collect_all_diff_info, save_diff_patch


def build_fixer_prompt(state: dict[str, Any]) -> str:
    prompts_dir = _hub_dir() / "src" / "ai_workflow_hub" / "prompts"
    template = (prompts_dir / "fixer.md").read_text(encoding="utf-8")

    context = f"""
## Fix Round
{state.get("fix_round", 0) + 1} / {state.get("max_fix_rounds", 3)}

## Task
- Title: {state.get("task_title", "")}

## Test Output (FACTS)
{state.get("test_output", "")}

## Review Result
{state.get("review_result", "")}

## Blocking Fixes
{chr(10).join(f'- {f}' for f in state.get("next_fixes", []))}

## Allowed Fix Files
{chr(10).join(f'- {f}' for f in state.get("allowed_fix_files", []))}

## Current Diff
{state.get("git_diff", "")[:3000]}
"""
    result = template + "\n\n" + context

    # 注入 CI 失败报告
    ci_report = state.get("ci_report", "")
    if ci_report:
        result += f"\n\n## CI Failure Report (FACTS)\n{ci_report[:3000]}\n\nFix the CI failures above."

    return result


def fixer_node(state: dict[str, Any]) -> dict[str, Any]:
    """执行修复节点.

    fix_round + 1。dry-run 时只生成 would-fix 报告，不调用 OpenCode。
    """
    run_dir = state.get("run_dir", "")
    project_path = state.get("project_path", "")
    worktree_path = state.get("worktree_path", project_path)
    model = state.get("fixer_model", "deepseek/deepseek-v4-pro")
    dry_run = state.get("dry_run", True)
    apply_changes = state.get("apply_changes", False)
    fix_round = state.get("fix_round", 0) + 1
    allowed_fix_files = state.get("allowed_fix_files", [])
    next_fixes = state.get("next_fixes", [])

    cwd = worktree_path or project_path
    state["fix_round"] = fix_round

    if dry_run and not apply_changes:
        # dry-run: 不调用 OpenCode
        fix_log = f"# Fix Log (Round {fix_round}) [DRY-RUN]\n\nWould fix:\n"
        for f in next_fixes:
            fix_log += f"- {f}\n"
        if not next_fixes:
            fix_log += "(no blocking fixes identified)\n"
        fix_log += "\nNo OpenCode agent was invoked. Use --apply to execute fixes.\n"

        prev_log = state.get("execution_log", "")
        save_run_file(run_dir, "execution-log.md", prev_log + "\n\n" + fix_log)

        return {
            "fix_round": fix_round,
            "execution_log": prev_log + "\n\n" + fix_log,
            "git_diff": state.get("git_diff", ""),
            "changed_files": state.get("changed_files", []),
            "changed_files_status": state.get("changed_files_status", {}),
            "diff_line_count": state.get("diff_line_count", 0),
        }

    # apply: 调 coding agent
    from ..agent_client import run_coding_agent, resolve_backend
    backend = resolve_backend(state.get("coding_backend"))

    prompt = build_fixer_prompt(state)
    save_run_file(run_dir, f"fixer-prompt-r{fix_round}.md", prompt)

    result = run_coding_agent(
        backend=backend,
        prompt=prompt,
        model=model,
        cwd=cwd,
        timeout=600,
        stdout_log=str(Path(run_dir) / f"{backend}-fixer-r{fix_round}-stdout.log"),
        stderr_log=str(Path(run_dir) / f"{backend}-fixer-r{fix_round}-stderr.log"),
    )

    execution_log = result.get("stdout", "")
    diff_info = collect_all_diff_info(cwd)
    save_diff_patch(cwd, str(Path(run_dir) / "diff.patch"))

    fix_log = f"# Fix Log (Round {fix_round})\n\n{execution_log}\n"
    prev_log = state.get("execution_log", "")
    save_run_file(run_dir, "execution-log.md", prev_log + "\n\n" + fix_log)

    return {
        "fix_round": fix_round,
        "execution_log": prev_log + "\n\n" + fix_log,
        "git_diff": diff_info["diff_text"],
        "changed_files": diff_info["changed_files"],
        "changed_files_status": diff_info["name_status"],
        "diff_line_count": diff_info["diff_line_count"],
        "error_message": result.get("stderr", ""),
        "backend_calls": {
            "fixer": {
                "backend": backend,
                "model": model,
                "exit_code": result.get("exit_code", -1),
                "timed_out": result.get("timed_out", False),
                "duration_seconds": result.get("duration_seconds", 0),
                "command_preview": result.get("command_preview", ""),
                "stdout_log": str(Path(run_dir) / f"{backend}-fixer-r{fix_round}-stdout.log"),
                "stderr_log": str(Path(run_dir) / f"{backend}-fixer-r{fix_round}-stderr.log"),
                "fallback_from": "",
                "fallback_reason": "",
            }
        },
    }
