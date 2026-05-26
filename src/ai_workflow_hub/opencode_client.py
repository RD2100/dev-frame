"""OpenCode 客户端 — Popen + 进程树治理.

- Popen 替代 subprocess.run，避免 PIPE 死锁
- Windows: taskkill /T /F 杀进程树
- 默认 --format json，非交互模式
- 超时后返回 timed_out=true
"""

from __future__ import annotations

import json as _json
import os
import signal
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any


def _ensure_env() -> None:
    """确保 .env 已加载（幂等）."""
    from .config_loader import init_env
    init_env()

# ---------------------------------------------------------------------------
# CLI detection
# ---------------------------------------------------------------------------

_opencode_path: str | None = None
_opencode_help_cache: dict[str, str] = {}


def _find_opencode() -> str | None:
    global _opencode_path
    if _opencode_path is not None:
        return _opencode_path
    candidates = [
        "opencode",
        os.path.expanduser("~/.local/bin/opencode"),
        os.path.expanduser("~/bin/opencode"),
        os.path.expanduser("~/npm_pack/opencode"),
        r"D:\Tools\npm_pack\opencode",
    ]
    for c in candidates:
        for use_shell in (False, True):
            try:
                r = subprocess.run(
                    [c, "--version"] if not use_shell else f"{c} --version",
                    capture_output=True, text=True, timeout=5, shell=use_shell)
                if r.returncode == 0:
                    _opencode_path = c
                    return c
                break
            except (FileNotFoundError, PermissionError, subprocess.TimeoutExpired, OSError):
                if use_shell: continue
    return None


def opencode_is_available() -> bool:
    return _find_opencode() is not None


def _run_opencode_help(args: list[str]) -> str:
    cache_key = " ".join(args)
    if cache_key in _opencode_help_cache:
        return _opencode_help_cache[cache_key]
    p = _find_opencode()
    if not p:
        return ""
    try:
        cmd = f"{p} {' '.join(args)} --help"
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10, shell=True)
        text = r.stdout or r.stderr or ""
        _opencode_help_cache[cache_key] = text
        return text
    except Exception:
        return ""


def opencode_supports_flag(flag: str) -> bool:
    help_text = _run_opencode_help(["run"])
    if not help_text:
        help_text = _run_opencode_help([])
    return flag in help_text


def opencode_cli_check() -> dict[str, Any]:
    p = _find_opencode()
    if not p:
        return {"available": False, "path": None, "error": "opencode CLI not found"}
    run_help = _run_opencode_help(["run"])
    desired_flags = ["-m", "--agent", "--format", "-f"]
    help_text = run_help or _run_opencode_help([])
    result: dict[str, Any] = {"available": True, "path": p, "run_help_ok": bool(run_help)}
    result["flags_found"] = [f for f in desired_flags if f in help_text]
    result["flags_missing"] = [f for f in desired_flags if f not in help_text]
    try:
        r = subprocess.run(f"{p} models", capture_output=True, text=True, timeout=10, shell=True)
        result["models_cmd_ok"] = r.returncode == 0
        result["models_stdout"] = r.stdout[:500] if r.returncode == 0 else ""
    except Exception:
        result["models_cmd_ok"] = False
        result["models_stdout"] = ""
    return result


def opencode_list_models() -> list[str]:
    p = _find_opencode()
    if not p:
        return []
    try:
        r = subprocess.run(f"{p} models", capture_output=True, text=True, timeout=10, shell=True)
        if r.returncode != 0:
            return []
        return [l.strip().split()[0] for l in r.stdout.strip().split("\n")
                if l.strip() and not l.startswith("Model") and not l.startswith("---")]
    except Exception:
        return []


def opencode_validate_model(model_id: str) -> tuple[bool, str]:
    if "/" not in model_id:
        return False, f"模型 ID 必须使用 provider/model 格式: {model_id}"
    models = opencode_list_models()
    if not models:
        return True, f"格式 OK (无法校验 remote): {model_id}"
    if model_id in models:
        return True, f"模型已找到: {model_id}"
    return False, f"不在已知列表中: {model_id}"


# ---------------------------------------------------------------------------
# Process tree kill (Windows)
# ---------------------------------------------------------------------------

def _kill_process_tree(pid: int) -> None:
    """Windows: 杀整棵进程树."""
    if os.name == "nt":
        try:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(pid)],
                           capture_output=True, timeout=10)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Main run
# ---------------------------------------------------------------------------

def opencode_run(
    prompt: str,
    model: str = "deepseek/deepseek-v4-pro",
    cwd: str | None = None,
    agent: str | None = None,
    format_output: str | None = None,
    file_input: str | None = None,
    timeout: int = 300,
    stdout_log: str | None = None,
    stderr_log: str | None = None,
) -> dict[str, Any]:
    """调用 opencode run — 非交互模式，Popen + 进程树治理."""

    _ensure_env()
    p = _find_opencode()
    if not p:
        return {"exit_code": 1, "stdout": "", "stderr": "ERROR: opencode CLI not found",
                "timed_out": False, "duration_seconds": 0, "model": model, "cwd": cwd or ""}

    safe_model = model or "deepseek/deepseek-v4-pro"
    safe_prompt = prompt if isinstance(prompt, str) else str(prompt or "")
    start_time = time.time()

    # 构建命令
    cmd = [p, "run", "-m", safe_model]

    if format_output and opencode_supports_flag("--format"):
        cmd.extend(["--format", format_output])

    if agent and opencode_supports_flag("--agent"):
        cmd.extend(["--agent", agent])

    if file_input and opencode_supports_flag("-f"):
        cmd.extend(["-f", file_input])

    cmd.append(safe_prompt)

    # shell 命令字符串
    if os.name == "nt":
        parts = [str(a) for a in cmd[:-1]]
        parts.append('"' + safe_prompt.replace('"', '""') + '"')
        cmd_str = " ".join(parts)
    else:
        import shlex
        cmd_str = " ".join(shlex.quote(str(a)) for a in cmd)

    command_preview = cmd_str[:200] + ("..." if len(cmd_str) > 200 else "")

    # 临时文件捕获输出
    stdout_fd, stdout_tmp = tempfile.mkstemp(suffix=".log", prefix="oc_stdout_")
    stderr_fd, stderr_tmp = tempfile.mkstemp(suffix=".log", prefix="oc_stderr_")
    os.close(stdout_fd)
    os.close(stderr_fd)

    proc = None
    timed_out = False
    exit_code = -1

    try:
        with open(stdout_tmp, "w", encoding="utf-8") as out_f, \
             open(stderr_tmp, "w", encoding="utf-8") as err_f:
            proc = subprocess.Popen(
                cmd_str,
                stdout=out_f,
                stderr=err_f,
                shell=True,
                cwd=cwd,
                env={**os.environ,
                     "OPENCODE_API_KEY": os.environ.get("OPENCODE_API_KEY", ""),
                     "OPENCODE_API_BASE": os.environ.get("OPENCODE_API_BASE", "")},
            )
            try:
                exit_code = proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                _kill_process_tree(proc.pid)
                try: proc.wait(timeout=5)
                except Exception: pass

        # 读取输出
        stdout = Path(stdout_tmp).read_text(encoding="utf-8", errors="replace")
        stderr = Path(stderr_tmp).read_text(encoding="utf-8", errors="replace")

        if timed_out:
            stderr = f"TIMEOUT after {timeout}s\ncommand: {command_preview}\n{stderr}"
            exit_code = 124

        # 复制到 run_dir 日志
        if stdout_log:
            Path(stdout_log).parent.mkdir(parents=True, exist_ok=True)
            Path(stdout_log).write_text(stdout, encoding="utf-8")
        if stderr_log:
            Path(stderr_log).parent.mkdir(parents=True, exist_ok=True)
            Path(stderr_log).write_text(stderr, encoding="utf-8")

    except Exception as e:
        stdout = ""
        stderr = f"ERROR: opencode run exception: {e}"
        if stderr_log:
            Path(stderr_log).parent.mkdir(parents=True, exist_ok=True)
            Path(stderr_log).write_text(stderr, encoding="utf-8")
    finally:
        try: os.unlink(stdout_tmp)
        except Exception: pass
        try: os.unlink(stderr_tmp)
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
