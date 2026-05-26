"""Router 节点 — 根据复审结果路由到下一节点."""

from __future__ import annotations

from typing import Any, Literal


def _s(state: dict[str, Any] | Any) -> dict[str, Any]:
    """安全解包: WorkflowState → dict."""
    if hasattr(state, "model_dump"):
        return state.model_dump()
    if isinstance(state, dict):
        return state
    return {}


def router_node(state: dict[str, Any]) -> dict[str, Any]:
    """路由决策 — pass-through."""
    return {}


def route_decision(state: dict[str, Any] | Any) -> Literal[
    "final_node", "fix_node", "human_gate_node", "__end__"
]:
    """条件路由函数 — LangGraph 直接调用，需处理 WorkflowState."""
    s = _s(state)

    review_result = s.get("review_result", "")
    fix_round = s.get("fix_round", 0)
    max_fix_rounds = s.get("max_fix_rounds", 3)
    dangerous_change = s.get("dangerous_change", False)
    human_required = s.get("human_required", False)

    # 1. human_required / dangerous → human_gate
    if human_required or dangerous_change:
        return "human_gate_node"

    # 2. review_result 路由
    if review_result == "pass":
        return "final_node"
    elif review_result == "fail":
        if fix_round < max_fix_rounds:
            return "fix_node"
        else:
            return "human_gate_node"
    elif review_result == "human_gate":
        return "human_gate_node"
    elif review_result == "blocked":
        return "final_node"

    return "final_node"
