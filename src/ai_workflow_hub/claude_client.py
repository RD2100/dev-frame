"""Claude Code 客户端 — Popen + 进程树治理.

对齐 opencode_client.py 接口:
- claude_run() 返回统一 dict
- Popen + 临时文件, 避免 PIPE 死锁
- Windows: taskkill /T /F 杀进程树
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any


def _ensure_env() -> None:
    from .config_loader import init_env
    init_env()


# ---------------------------------------------------------------------------
# CLI detection
# ---------------------------------------------------------------------------

_claude_path: str | None = None


def _find_claude() -> str | None:
    global _claude_path
    if _claude_path is not None:
        return _claude_path
    candidates = [
        "claude",
        os.path.expanduser("~/.local/bin/claude"),
        os.path.expanduser("~/bin/claude"),
        os.path.expanduser("~/npm_pack/claude"),
        r"D:\Tools\npm_pack\claude",
    ]
    for c in candidates:
        for use_shell in (False, True):
            try:
                r = subprocess.run(
                    [c, "--version"] if not use_shell else f"{c} --version",
                    capture_output=True, text=True, timeout=5, shell=use_shell)
                if r.returncode == 0:
                    _claude_path = c
                    return c
                break
            except (FileNotFoundError, PermissionError, subprocess.TimeoutExpired, OSError):
                if use_shell: continue
    return None


def claude_is_available() -> bool:
    return _find_claude() is not None


def claude_cli_check() -> dict[str, Any]:
    p = _find_claude()
    if not p:
        return {"available": False, "path": None, "error": "claude CLI not found"}
    try:
        r = subprocess.run(f"{p} --version", capture_output=True, text=True, timeout=5, shell=True)
        version = r.stdout.strip() or r.stderr.strip()
    except Exception:
        version = "unknown"
    return {"available": True, "path": p, "version": version,
            "non_interactive": True,  # -p/--print confirmed
            "permission_bypass": True}  # --permission-mode bypassPermissions


# ---------------------------------------------------------------------------
# Process tree kill (Windows)
# ---------------------------------------------------------------------------

def _kill_process_tree(pid: int) -> None:
    if os.name == "nt":
        try:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)],
                           capture_output=True, timeout=10)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Main run
# ---------------------------------------------------------------------------

def claude_run(
    prompt: str,
    model: str = "sonnet",
    cwd: str | None = None,
    timeout: int = 600,
    stdout_log: str | None = None,
    stderr_log: str | None = None,
) -> dict[str, Any]:
    """调用 Claude Code --print 执行 prompt."""

    _ensure_env()
    p = _find_claude()
    if not p:
        return {"exit_code": 1, "stdout": "", "stderr": "ERROR: claude CLI not found",
                "timed_out": False, "duration_seconds": 0, "model": model, "cwd": cwd or ""}

    safe_prompt = prompt if isinstance(prompt, str) else str(prompt or "")
    start_time = time.time()

    # 写入临时 prompt 文件（避免 shell 编码问题）
    prompt_fd, prompt_file = tempfile.mkstemp(suffix=".txt", prefix="cc_prompt_")
    os.close(prompt_fd)
    Path(prompt_file).write_text(safe_prompt, encoding="utf-8")

    # claude -p via stdin: 避免命令行中文乱码
    cmd = [
        p, "-p",
        "--permission-mode", "bypassPermissions",
        "--no-session-persistence",
        "--bare",
        "--tools", "Bash,Read,Write,Edit,Glob,Grep",
    ]
    if model:
        cmd.extend(["--model", model])

    cmd_str = " ".join(str(a) for a in cmd)
    command_preview = cmd_str[:200] + ("..." if len(cmd_str) > 200 else "")

    # 临时文件
    stdout_fd, stdout_tmp = tempfile.mkstemp(suffix=".log", prefix="cc_stdout_")
    stderr_fd, stderr_tmp = tempfile.mkstemp(suffix=".log", prefix="cc_stderr_")
    os.close(stdout_fd)
    os.close(stderr_fd)

    proc = None
    timed_out = False
    exit_code = -1

    try:
        with open(prompt_file, "rb") as stdin_f, \
             open(stdout_tmp, "w", encoding="utf-8") as out_f, \
             open(stderr_tmp, "w", encoding="utf-8") as err_f:
            proc = subprocess.Popen(
                cmd_str,
                stdout=out_f, stderr=err_f,
                stdin=stdin_f,
                shell=True, cwd=cwd,
            )
            try:
                exit_code = proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                _kill_process_tree(proc.pid)
                try: proc.wait(timeout=5)
                except Exception: pass

        stdout = Path(stdout_tmp).read_text(encoding="utf-8", errors="replace")
        stderr = Path(stderr_tmp).read_text(encoding="utf-8", errors="replace")

        if timed_out:
            stderr = f"TIMEOUT after {timeout}s\ncommand: {command_preview}\n{stderr}"
            exit_code = 124

        if stdout_log:
            Path(stdout_log).parent.mkdir(parents=True, exist_ok=True)
            Path(stdout_log).write_text(stdout, encoding="utf-8")
        if stderr_log:
            Path(stderr_log).parent.mkdir(parents=True, exist_ok=True)
            Path(stderr_log).write_text(stderr, encoding="utf-8")

    except Exception as e:
        stdout = ""
        stderr = f"ERROR: claude run exception: {e}"
        if stderr_log:
            Path(stderr_log).parent.mkdir(parents=True, exist_ok=True)
            Path(stderr_log).write_text(stderr, encoding="utf-8")
    finally:
        try: os.unlink(stdout_tmp)
        except Exception: pass
        try: os.unlink(stderr_tmp)
        except Exception: pass
        try: os.unlink(prompt_file)
        except Exception: pass

    return {
        "exit_code": exit_code,
        "stdout": stdout,
        "stderr": stderr,
        "model": model,
        "cwd": cwd or "",
        "timed_out": timed_out,
        "duration_seconds": round(time.time() - start_time, 1),
        "command_preview": command_preview,
    }
