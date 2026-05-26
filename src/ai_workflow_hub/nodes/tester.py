"""Tester 节点 — 执行 .aiworkflow.yaml 中声明的测试命令.

审计强化:
- dry-run 且未显式 --run-tests: 只列出命令，不执行
- dry-run + --run-tests: 执行测试但不修改文件
- apply: 始终执行测试
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..shell_runner import run_project_commands
from ..run_store import save_run_file


def tester_node(state: dict[str, Any]) -> dict[str, Any]:
    """执行测试节点.

    dry-run (默认): 列出测试命令，不执行
    dry-run + run_tests: 执行测试
    apply: 始终执行测试
    """
    run_dir = state.get("run_dir", "")
    project_path = state.get("project_path", "")
    worktree_path = state.get("worktree_path", project_path)
    dry_run = state.get("dry_run", True)
    apply_changes = state.get("apply_changes", False)
    run_tests = state.get("run_tests", False)

    cwd = worktree_path or project_path

    # 获取测试命令
    test_commands = state.get("test_commands", {})
    if not test_commands:
        test_commands = state.get("project_config", {}).get("commands", {})

    if not test_commands:
        save_run_file(run_dir, "test-output.md", "# Test Output\n\nNo test commands configured.")
        return {"test_output": "No test commands configured.", "test_exit_code": -1}

    # dry-run 且未显式 run_tests: 只列出
    if dry_run and not apply_changes and not run_tests:
        output = _generate_test_listing(test_commands)
        save_run_file(run_dir, "test-output.md", output)
        return {
            "test_output": output,
            "test_exit_code": 0,
        }

    # 执行测试
    results = run_project_commands(
        commands=test_commands,
        cwd=cwd,
        run_dir=run_dir,
    )

    output_lines = ["# Test Output\n"]
    overall_exit = 0

    for cmd_name, cmd_result in results.items():
        ec = cmd_result["exit_code"]
        status = "PASS" if ec == 0 else ("FAIL" if ec > 0 else "SKIP")
        if ec > 0:
            overall_exit = ec
        output_lines.append(f"## {cmd_name}: {status}")
        output_lines.append(f"Exit Code: {ec}")
        if cmd_result["stdout"]:
            output_lines.append(f"```\n{cmd_result['stdout'][:2000]}\n```")
        if cmd_result["stderr"]:
            output_lines.append(f"**Stderr:**\n```\n{cmd_result['stderr'][:2000]}\n```")
        output_lines.append("")

    test_output = "\n".join(output_lines)
    save_run_file(run_dir, "test-output.md", test_output)

    return {
        "test_output": test_output,
        "test_exit_code": overall_exit,
    }


def _generate_test_listing(commands: dict[str, str]) -> str:
    """生成测试命令清单（dry-run 不执行）."""
    lines = [
        "# Test Output (DRY-RUN — tests NOT executed)",
        "",
        "The following commands WOULD be executed in --apply mode or with --run-tests:",
        "",
    ]
    for cmd_name, cmd_value in sorted(commands.items()):
        if not cmd_value or "TODO" in str(cmd_value).upper():
            lines.append(f"- **{cmd_name}**: SKIPPED (TODO)")
        else:
            lines.append(f"- **{cmd_name}**: `{cmd_value}`")
    lines.append("")
    lines.append("To execute tests in dry-run mode: `aihub run ... --run-tests`")
    return "\n".join(lines)
