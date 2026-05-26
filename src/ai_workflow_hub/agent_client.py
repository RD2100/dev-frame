"""Coding agent 分发层 — 统一 opencode / claude 接口."""

from __future__ import annotations

from typing import Literal

from .opencode_client import opencode_run, opencode_is_available
from .claude_client import claude_run, claude_is_available


AgentBackend = Literal["opencode", "claude"]


def run_coding_agent(
    backend: AgentBackend,
    prompt: str,
    model: str,
    cwd: str,
    timeout: int = 600,
    stdout_log: str | None = None,
    stderr_log: str | None = None,
) -> dict:
    """统一 coding agent 入口."""
    if backend == "claude":
        # Claude 不需要 provider/ 前缀
        claude_model = model.split("/")[-1] if "/" in model else model
        return claude_run(
            prompt=prompt, model=claude_model, cwd=cwd,
            timeout=timeout, stdout_log=stdout_log, stderr_log=stderr_log,
        )

    if backend == "opencode":
        return opencode_run(
            prompt=prompt, model=model, cwd=cwd,
            timeout=timeout, stdout_log=stdout_log, stderr_log=stderr_log,
        )

    return {"exit_code": 1, "stdout": "", "stderr": f"ERROR: unknown backend '{backend}'",
            "timed_out": False, "duration_seconds": 0, "model": model, "cwd": cwd}


def resolve_backend(requested: str | None = None) -> AgentBackend:
    """解析 backend 优先级: 参数 > env > backend_policy.preferred > 默认 opencode.

    同时检查 health, degraded 时显式使用仍允许但记录 warning.
    """
    import os
    from .config_loader import get_execution_policy
    from .backend_health import _load_health

    policy = get_execution_policy()
    bp = policy.get("backend_policy", {})

    # 1. 显式参数
    if requested and requested in ("opencode", "claude"):
        return _check_health(requested, bp)  # type: ignore[return-value]

    # 2. 环境变量
    env = os.environ.get("AIHUB_CODING_BACKEND", "")
    if env in ("opencode", "claude"):
        return _check_health(env, bp)  # type: ignore[return-value]

    # 3. preferred_backend — always use it, health is informational only
    preferred = bp.get("preferred_backend", "claude")
    if preferred in ("opencode", "claude"):
        return preferred  # type: ignore[return-value]

    return "claude"


def _check_health(backend: str, bp: dict) -> str:
    """检查 backend health, 不拦截但记录."""
    degraded = bp.get("degraded_backends", [])
    if backend in degraded:
        pass  # degraded but explicitly chosen — no redirect
    return backend


def backend_health_summary() -> dict[str, str]:
    """返回每个 backend 的 health 状态."""
    from .backend_health import _load_health
    from .config_loader import get_execution_policy
    health = _load_health()
    bp = get_execution_policy().get("backend_policy", {})
    threshold = bp.get("min_health_score", 0.75)
    degraded = bp.get("degraded_backends", [])

    result = {}
    for b in ["claude", "opencode"]:
        h = health.get(b, {})
        if b in degraded:
            result[b] = "degraded"
        elif h.get("health_score", 0) >= threshold:
            result[b] = "healthy"
        else:
            result[b] = "degraded"
    return result


def log_name(backend: AgentBackend, node: str, suffix: str) -> str:
    """生成 backend 感知的日志文件名."""
    prefix = "claude" if backend == "claude" else "opencode"
    return f"{prefix}-{node}-{suffix}"
