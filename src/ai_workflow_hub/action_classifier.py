"""Action risk classifier — 统一行为分级 (safe/risky/destructive)."""

from __future__ import annotations

from typing import Literal

ActionLevel = Literal["safe", "risky", "destructive"]

_RISKY = {"apply", "pr.create", "ci.fix", "run.start.apply"}
_DESTRUCTIVE = {"worktree.clean", "run.prune", "branch.delete", "rm", "move", "archive"}


def classify(action: str) -> ActionLevel:
    if any(d in action for d in _DESTRUCTIVE):
        return "destructive"
    if any(r in action for r in _RISKY):
        return "risky"
    return "safe"


def auto_approve(action: str) -> bool:
    return classify(action) == "safe"


def requires_confirmation(action: str) -> bool:
    return classify(action) == "destructive"


def passes_policy(action: str) -> bool:
    return classify(action) in ("safe", "risky")


def action_note(action: str) -> str:
    return {
        "safe": "",
        "risky": " (policy gate)",
        "destructive": " [CONFIRMATION REQUIRED]",
    }.get(classify(action), "")
