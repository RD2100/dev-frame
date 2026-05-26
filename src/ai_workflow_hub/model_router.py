"""模型路由器 — 根据风险等级分配模型.

审计强化:
- OpenCode 模型必须使用 provider/model 格式
- opencode models 命令校验模型可用性
- doctor 检查 codex CLI 兼容性
"""

from __future__ import annotations

import os
from typing import Any

from .config_loader import get_model_config


def resolve_model(role: str, risk: str = "medium") -> str:
    """根据角色和风险解析实际使用的 model ID.

    优先级: 环境变量 > configs/model-router.yaml 风险profile > default
    """
    config = get_model_config()

    env_map = {
        "planner": "CODEX_MODEL_PLANNER",
        "reviewer": "CODEX_MODEL_REVIEWER",
        "finalizer": "CODEX_MODEL_FINALIZER",
        "executor": "OPENCODE_MODEL_EXECUTOR",
        "fixer": "OPENCODE_MODEL_FIXER",
    }
    if role in env_map:
        env_val = os.environ.get(env_map[role], "")
        if env_val:
            return env_val

    profiles = config.get("risk_profiles", {})
    risk_profile = profiles.get(risk, profiles.get("medium", {}))
    if role in risk_profile:
        return risk_profile[role]

    defaults = config.get("default", {})
    return defaults.get(role, "gpt-5.5-codex")


def get_api_config(provider: str) -> dict[str, str]:
    config = get_model_config()
    providers = config.get("providers", {})
    info = providers.get(provider, {})
    return {
        "api_key": os.environ.get(info.get("api_key_env", ""), ""),
        "api_base": os.environ.get(info.get("api_base_env", ""), ""),
    }


def get_model_for_task(risk: str) -> dict[str, str]:
    return {
        "planner": resolve_model("planner", risk),
        "reviewer": resolve_model("reviewer", risk),
        "executor": resolve_model("executor", risk),
        "fixer": resolve_model("fixer", risk),
    }


def human_gate_required_for_risk(risk: str) -> bool:
    config = get_model_config()
    profiles = config.get("risk_profiles", {})
    risk_profile = profiles.get(risk, {})
    return risk_profile.get("human_gate_required", False)


# ---------------------------------------------------------------------------
# 模型校验
# ---------------------------------------------------------------------------

def validate_model_format(model_id: str, provider: str) -> tuple[bool, str]:
    """校验模型 ID 格式.

    OpenCode 模型必须为 provider/model 格式 (e.g. deepseek/deepseek-v4-pro).
    Codex 模型通过环境变量管理，不做格式要求.
    """
    if provider == "opencode":
        if "/" not in model_id:
            return False, f"OpenCode 模型 ID 必须为 provider/model 格式，当前: {model_id}"
    return True, "OK"


def validate_all_models(risk: str = "medium") -> dict[str, Any]:
    """校验所有角色的模型.

    Returns:
        {role: {model_id, format_ok, format_msg, remote_ok, remote_msg}}
    """
    models = get_model_for_task(risk)
    results = {}

    for role, model_id in models.items():
        if role in ("executor", "fixer"):
            from .agent_client import resolve_backend
            backend = resolve_backend()
            provider = "opencode" if backend == "opencode" else "claude"
        else:
            provider = "codex"
        fmt_ok, fmt_msg = validate_model_format(model_id, provider)
        entry: dict[str, Any] = {
            "model_id": model_id,
            "provider": provider,
            "format_ok": fmt_ok,
            "format_msg": fmt_msg,
            "remote_ok": None,
            "remote_msg": "",
        }

        # OpenCode: 尝试验证 remote
        if provider == "opencode":
            try:
                from .opencode_client import opencode_validate_model
                remote_ok, remote_msg = opencode_validate_model(model_id)
                entry["remote_ok"] = remote_ok
                entry["remote_msg"] = remote_msg
            except Exception:
                entry["remote_ok"] = None
                entry["remote_msg"] = "unable to check (opencode CLI not available)"

        # Codex: 检查 CLI 是否存在（通过 doctor）
        if provider == "codex":
            from .codex_client import codex_is_available
            entry["remote_ok"] = codex_is_available()
            entry["remote_msg"] = "codex CLI available" if codex_is_available() else "codex CLI not found"

        results[role] = entry

    return results
