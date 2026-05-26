"""Shell 执行器 — 安全执行 .aiworkflow.yaml 中声明的命令."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

from .config_loader import get_execution_policy


def is_command_allowed(command: str, project_commands: dict[str, str]) -> bool:
    """检查命令是否在项目配置的 commands 中声明."""
    # 检查是否是声明的命令之一
    for cmd_value in project_commands.values():
        if cmd_value and cmd_value.strip() == command.strip():
            return True
    return False


def is_shell_safe(command: str) -> tuple[bool, str]:
    """检查命令是否匹配 forbidden_shell_patterns.

    Returns:
        (is_safe, reason)
    """
    policy = get_execution_policy()
    forbidden = policy.get("forbidden_shell_patterns", [])

    cmd_lower = command.lower()
    for pattern in forbidden:
        pattern_lower = pattern.lower()
        if pattern_lower in cmd_lower:
            return False, f"命令匹配禁止模式: '{pattern}'"

    return True, ""


def run_command(
    command: str,
    cwd: str,
    timeout: int | None = None,
    output_file: str | None = None,
) -> tuple[int, str, str]:
    """安全执行命令.

    Args:
        command: 要执行的命令
        cwd: 工作目录
        timeout: 超时秒数
        output_file: 可选，将输出同时写入文件

    Returns:
        (exit_code, stdout, stderr)
    """
    if not command or not command.strip():
        return -1, "", "ERROR: 空命令，不允许执行"

    if timeout is None:
        policy = get_execution_policy()
        timeout = policy.get("command_timeout_seconds", 600)

    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        stdout = result.stdout
        stderr = result.stderr
        exit_code = result.returncode

        if output_file:
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            content = f"# Command: {command}\n# Exit Code: {exit_code}\n# CWD: {cwd}\n\n## STDOUT\n{stdout}\n\n## STDERR\n{stderr}\n"
            output_path.write_text(content, encoding="utf-8")

        return exit_code, stdout, stderr

    except subprocess.TimeoutExpired:
        msg = f"TIMEOUT: 命令超时 ({timeout}s): {command}"
        if output_file:
            Path(output_file).write_text(msg, encoding="utf-8")
        return 124, "", msg
    except Exception as e:
        msg = f"ERROR: 命令执行异常: {e}"
        if output_file:
            Path(output_file).write_text(msg, encoding="utf-8")
        return 1, "", msg


def run_project_commands(
    commands: dict[str, str],
    cwd: str,
    run_dir: str,
    command_names: list[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """按顺序执行项目命令.

    Args:
        commands: .aiworkflow.yaml 中的 commands 节
        cwd: 项目工作目录
        run_dir: 运行目录（用于保存输出）
        command_names: 要执行的命令名称列表，默认执行所有非空命令

    Returns:
        {command_name: {exit_code, stdout, stderr, output_file}}
    """
    results = {}

    to_run = command_names or ["lint", "typecheck", "unit_test", "integration_test", "build"]

    for cmd_name in to_run:
        cmd_value = commands.get(cmd_name, "")
        if not cmd_value or "TODO" in str(cmd_value).upper():
            results[cmd_name] = {
                "exit_code": -1,
                "stdout": "",
                "stderr": f"SKIPPED: 命令未配置或为 TODO: '{cmd_name}'",
                "output_file": "",
            }
            continue

        # 安全检查
        safe, reason = is_shell_safe(cmd_value)
        if not safe:
            results[cmd_name] = {
                "exit_code": -1,
                "stdout": "",
                "stderr": f"BLOCKED: {reason}",
                "output_file": "",
            }
            continue

        output_file = str(Path(run_dir) / f"{cmd_name}-output.log")
        exit_code, stdout, stderr = run_command(
            cmd_value, cwd=cwd, output_file=output_file
        )
        results[cmd_name] = {
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr,
            "output_file": output_file,
        }

    return results
