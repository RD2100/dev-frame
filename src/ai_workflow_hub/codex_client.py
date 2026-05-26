"""Codex 客户端 — CLI + HTTP API 双后端.

优先 Codex CLI，回退到 OpenAI-compatible HTTP API (DeepSeek)。
规划/复审角色共用 DeepSeek key。
"""

from __future__ import annotations

import json as _json
import os
import subprocess
from pathlib import Path
from typing import Any, Protocol


# ---------------------------------------------------------------------------
# CodexAdapter — SDK adapter interface (future)
# ---------------------------------------------------------------------------

class CodexAdapter(Protocol):
    """Codex SDK adapter 接口."""

    def execute(self, prompt: str, model: str, working_dir: str | None = None,
                timeout: int = 600) -> dict[str, Any]: ...


class CodexSDKAdapter:
    def __init__(self, model: str = "deepseek-chat"):
        self._model = model

    def execute(self, prompt: str, model: str = "", working_dir: str | None = None,
                timeout: int = 600) -> dict[str, Any]:
        return codex_exec(prompt=prompt, model=model or self._model, cwd=working_dir, timeout=timeout)


# ---------------------------------------------------------------------------
# CLI detection
# ---------------------------------------------------------------------------

_codex_path: str | None = None
_codex_help_text: str | None = None
_codex_flags_known: dict[str, bool] = {}


def _find_codex() -> str | None:
    global _codex_path
    if _codex_path is not None:
        return _codex_path
    for c in ["codex", os.path.expanduser("~/.local/bin/codex"),
              os.path.expanduser("~/bin/codex"), r"D:\Tools\npm_pack\codex"]:
        for use_shell in (False, True):
            try:
                r = subprocess.run(
                    [c, "--version"] if not use_shell else f"{c} --version",
                    capture_output=True, text=True, timeout=5, shell=use_shell)
                if r.returncode == 0:
                    _codex_path = c
                    return c
                break
            except (FileNotFoundError, PermissionError, subprocess.TimeoutExpired, OSError):
                if use_shell: continue
    return None


def codex_is_available() -> bool:
    return _find_codex() is not None


def codex_cli_check() -> dict[str, Any]:
    p = _find_codex()
    if not p:
        return {"available": False, "path": None, "error": "codex CLI not found"}
    try:
        r = subprocess.run(f"{p} exec --help", capture_output=True, text=True, timeout=10, shell=True)
        help_text = r.stdout or r.stderr or ""
    except Exception:
        help_text = ""
    return {"available": True, "path": p, "exec_help_ok": bool(help_text),
            "flags_found": [], "flags_missing": []}


# ---------------------------------------------------------------------------
# HTTP API client (OpenAI-compatible)
# ---------------------------------------------------------------------------

def _http_exec(prompt: str, model: str, timeout: int, stdout_log: str | None,
               stderr_log: str | None) -> dict[str, Any]:
    """通过 HTTP API 调用 OpenAI-compatible 接口."""
    import urllib.request as _urllib
    import urllib.error as _urlerror
    import json as _json

    api_key = os.environ.get("CODEX_API_KEY") or os.environ.get("OPENCODE_API_KEY", "")
    api_base = os.environ.get("CODEX_API_BASE") or os.environ.get("OPENCODE_API_BASE", "")

    if not api_key:
        return {"exit_code": 1, "stdout": "", "stderr": "ERROR: no API key (CODEX_API_KEY or OPENCODE_API_KEY)",
                "model": model, "cwd": ""}

    if not api_base:
        api_base = "https://api.deepseek.com/v1"

    url = f"{api_base.rstrip('/')}/chat/completions"

    payload = _json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": 4096,
    }).encode("utf-8")

    req = _urllib.Request(url, data=payload, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    })

    try:
        with _urllib.urlopen(req, timeout=timeout) as resp:
            body = _json.loads(resp.read().decode("utf-8"))
        content = body["choices"][0]["message"]["content"]
        stdout = content
        stderr = ""

        if stdout_log:
            Path(stdout_log).parent.mkdir(parents=True, exist_ok=True)
            Path(stdout_log).write_text(stdout, encoding="utf-8")
        if stderr_log:
            Path(stderr_log).parent.mkdir(parents=True, exist_ok=True)
            Path(stderr_log).write_text(stderr, encoding="utf-8")

        return {"exit_code": 0, "stdout": stdout, "stderr": stderr, "model": model, "cwd": ""}

    except _urlerror.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        msg = f"HTTP {e.code}: {err_body[:500]}"
        if stderr_log:
            Path(stderr_log).parent.mkdir(parents=True, exist_ok=True)
            Path(stderr_log).write_text(msg, encoding="utf-8")
        return {"exit_code": 1, "stdout": "", "stderr": msg, "model": model, "cwd": ""}
    except Exception as e:
        msg = f"HTTP ERROR: {e}"
        if stderr_log:
            Path(stderr_log).parent.mkdir(parents=True, exist_ok=True)
            Path(stderr_log).write_text(msg, encoding="utf-8")
        return {"exit_code": 1, "stdout": "", "stderr": msg, "model": model, "cwd": ""}


def _http_available() -> bool:
    key = os.environ.get("CODEX_API_KEY") or os.environ.get("OPENCODE_API_KEY")
    return bool(key)


# ---------------------------------------------------------------------------
# Main exec — CLI first, HTTP fallback
# ---------------------------------------------------------------------------
# Auth check
# ---------------------------------------------------------------------------

def codex_auth_check() -> dict[str, Any]:
    """检测 Codex CLI 登录状态."""
    p = _find_codex()
    if not p:
        return {"authenticated": False, "auth_mode": "", "message": "codex CLI not found"}

    try:
        r = subprocess.run(f"{p} login status", capture_output=True, text=True,
                           timeout=10, shell=True)
        status = (r.stdout + r.stderr).strip().lower()
        if "logged in using chatgpt" in status:
            return {"authenticated": True, "auth_mode": "chatgpt",
                    "has_api_key": False, "message": status}
        if "logged in using api key" in status:
            return {"authenticated": True, "auth_mode": "api_key",
                    "has_api_key": True, "message": status}

        # Fallback: try codex doctor parsing
        r2 = subprocess.run(f"{p} doctor", capture_output=True, text=True,
                            timeout=10, shell=True)
        doctor = r2.stdout or r2.stderr or ""
        if "auth is configured" in doctor.lower():
            if "chatgpt tokens    true" in doctor.lower():
                return {"authenticated": True, "auth_mode": "chatgpt",
                        "has_api_key": False, "message": "auth configured (doctor)"}
            if "api key           true" in doctor.lower():
                return {"authenticated": True, "auth_mode": "api_key",
                        "has_api_key": True, "message": "auth configured (doctor)"}
            return {"authenticated": True, "auth_mode": "unknown",
                    "has_api_key": False, "message": "auth configured (unknown mode)"}

        return {"authenticated": False, "auth_mode": "",
                "has_api_key": False, "message": status or "not authenticated"}
    except Exception as e:
        return {"authenticated": False, "auth_mode": "",
                "has_api_key": False, "message": str(e)}


# ---------------------------------------------------------------------------

def codex_exec(
    prompt: str,
    model: str = "gpt-5.5-codex",
    cwd: str | None = None,
    context_files: list[str] | None = None,
    timeout: int = 600,
    stdout_log: str | None = None,
    stderr_log: str | None = None,
) -> dict[str, Any]:
    """执行 prompt — Codex CLI (ChatGPT login) 优先，HTTP API 回退."""

    from .config_loader import init_env
    init_env()

    codx = _find_codex()
    auth = codex_auth_check()

    # ChatGPT auth: map model names (gpt-5.5-codex -> gpt-5.5)
    effective_model = model
    if auth.get("auth_mode") == "chatgpt" and "gpt-5.5" in model.lower():
        effective_model = "gpt-5.5"
        if not model.endswith("-codex"):
            effective_model = model  # already correct

    if codx and auth["authenticated"]:
        # Build command string for shell=True (Windows)
        cmd_parts = [codx, "exec", "-m", effective_model, "--skip-git-repo-check"]
        if cwd:
            cmd_parts.extend(["-C", cwd])
        cmd_parts.append("-")
        cmd_str = " ".join(str(a) for a in cmd_parts)

        try:
            r = subprocess.run(
                cmd_str, input=prompt, capture_output=True,
                timeout=timeout, cwd=cwd, shell=True,
                encoding="utf-8", errors="replace",
            )
            if stdout_log: Path(stdout_log).parent.mkdir(parents=True, exist_ok=True); Path(stdout_log).write_text(r.stdout, encoding="utf-8")
            if stderr_log: Path(stderr_log).parent.mkdir(parents=True, exist_ok=True); Path(stderr_log).write_text(r.stderr, encoding="utf-8")
            # Codex CLI writes response to stderr, not stdout.
            # WebSocket tls error produces exit=1 even on success.
            # NARROW: only apply when stdout empty AND stderr has success markers
            # AND stderr does NOT contain fatal/error/timeout/auth indicators
            stdout = r.stdout
            stderr_out = r.stderr
            stderr_lower = (stderr_out or "").lower()
            has_output = bool(stdout.strip() or stderr_out.strip())
            has_success = ("ok" in stderr_lower or "tokens used" in stderr_lower)
            has_error = any(w in stderr_lower for w in
                ("fatal", "auth failed", "unauthorized", "forbidden"))
            is_codex_stderr = (not stdout.strip() and has_success and not has_error)
            if is_codex_stderr:
                stdout, stderr_out = stderr_out, stdout
            effective_exit = 0 if stdout.strip() else r.returncode
            return {
                "exit_code": effective_exit, "stdout": stdout, "stderr": stderr_out,
                "model": effective_model, "cwd": cwd or "",
                "requested_model": model, "effective_model": effective_model,
                "model_accepted": effective_model == model or effective_exit == 0,
                "backend": "codex_cli", "fallback_from": "", "fallback_reason": "",
                "auth_mode": auth.get("auth_mode", ""), "provider": "openai",
            }
        except subprocess.TimeoutExpired:
            pass
        except Exception:
            pass

    # HTTP API fallback — map model to DeepSeek-compatible
    http_model = model if "deepseek" in model.lower() else "deepseek-chat"
    if _http_available():
        result = _http_exec(prompt=prompt, model=http_model, timeout=timeout,
                            stdout_log=stdout_log, stderr_log=stderr_log)
        result["backend"] = "http_fallback"
        result["fallback_from"] = "codex"
        result["fallback_reason"] = "codex_exec_failed" if codx and auth["authenticated"] else "codex_cli_not_authenticated"
        return result

    return {"exit_code": 1, "stdout": "", "stderr": "ERROR: no backend available",
            "model": model, "cwd": cwd or "",
            "backend": "none", "fallback_from": "", "fallback_reason": "no backend"}
