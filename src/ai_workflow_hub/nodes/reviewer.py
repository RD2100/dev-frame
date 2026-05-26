"""Reviewer 节点 — 调用 Codex/GPT-5.5 复审执行结果.

审计强化:
- 接受 git diff --name-status 作为硬事实
- safety_report 的硬拦截结果纳入 review 输入
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from ..codex_client import codex_exec
from ..config_loader import _hub_dir
from ..run_store import save_run_file, save_run_json
from ..safety import produce_safety_report


def build_reviewer_prompt(state: dict[str, Any]) -> str:
    prompts_dir = _hub_dir() / "src" / "ai_workflow_hub" / "prompts"
    template = (prompts_dir / "reviewer.md").read_text(encoding="utf-8")

    # name-status 摘要
    name_status = state.get("changed_files_status", {})
    ns_lines = []
    for fp, st in sorted(name_status.items()):
        ns_lines.append(f"  {st}  {fp}")
    ns_text = "\n".join(ns_lines) if ns_lines else "(no changes)"

    context = f"""
## Task
- Title: {state.get("task_title", "")}
- Risk: {state.get("task_risk", "medium")}
- Fix Round: {state.get("fix_round", 0)} / {state.get("max_fix_rounds", 3)}

## Git Diff --name-status (HARD FACTS)
```
{ns_text}
```

## Plan (original)
{state.get("plan", "")[:3000]}

## Test Output (FACTS)
{state.get("test_output", "")[:5000]}

## Git Diff (FACTS)
{state.get("git_diff", "")[:5000]}

## Changed Files
{chr(10).join(f'- {f}' for f in state.get("changed_files", []))}

## Diff Line Count
{state.get("diff_line_count", 0)}

## Allowed Files
{chr(10).join(f'- {f}' for f in state.get("allowed_files", []))}

## Forbidden Files (NEVER touch)
{chr(10).join(f'- {f}' for f in state.get("forbidden_files", []))}

## Protected Tests (NEVER delete)
{chr(10).join(f'- {f}' for f in state.get("protected_tests", []))}

## Constraints
- max_fix_rounds: {state.get("max_fix_rounds", 3)}
- max_changed_files: {state.get("constraints", {}).get("max_changed_files", 20)}
- max_diff_lines: {state.get("constraints", {}).get("max_diff_lines", 800)}

## CRITICAL RULES
- If any file in Forbidden Files was touched → verdict=human_gate
- If any Protected Test file was deleted (status D) → verdict=blocked
- If test assertions are clearly reduced → verdict=human_gate
"""
    return template + "\n\n" + context


def reviewer_node(state: dict[str, Any]) -> dict[str, Any]:
    """复审节点.

    输入: plan, execution_log, test_output, git_diff + name-status
    先执行硬安全拦截 (safety report)，再调用 Codex 复审。
    """
    run_dir = state.get("run_dir", "")
    project_path = state.get("project_path", "")
    worktree_path = state.get("worktree_path", project_path)
    model = state.get("reviewer_model", "gpt-5.5-codex")

    cwd = worktree_path or project_path

    # --- 硬安全拦截 (基于 git 事实，先于 Codex) ---
    name_status = state.get("changed_files_status", {})
    if not name_status:
        from ..git_utils import get_diff_name_status
        name_status = get_diff_name_status(cwd)

    constraints = state.get("constraints", {})
    safety_report = produce_safety_report(
        run_dir=run_dir,
        repo_path=cwd,
        name_status=name_status,
        changed_files=state.get("changed_files", []),
        forbidden_patterns=state.get("forbidden_files", []),
        protected_patterns=state.get("protected_tests", []),
        diff_line_count=state.get("diff_line_count", 0),
        max_diff_lines=constraints.get("max_diff_lines", 800),
        max_changed_files=constraints.get("max_changed_files", 20),
        risk=state.get("task_risk", "medium"),
    )

    safety_overall = safety_report.get("overall", "pass")

    # 如果硬拦截已经是 blocked 或 human_gate，短路 — 不调 Codex
    if safety_overall in ("blocked", "human_gate"):
        save_run_file(run_dir, "review.md", f"# Review (short-circuited by safety)\n\nsafety_overall={safety_overall}")
        review_yaml = {
            "verdict": safety_overall,
            "test_exit_code": state.get("test_exit_code", -1),
            "files_changed": len(state.get("changed_files", [])),
            "diff_lines": state.get("diff_line_count", 0),
            "forbidden_touched": any(
                c.get("name") == "forbidden_paths" and not c.get("passed")
                for c in safety_report.get("checks", [])
            ),
            "tests_deleted": any(
                c.get("name") == "protected_tests" and c.get("detail", {}).get("deleted")
                for c in safety_report.get("checks", [])
            ),
            "assertions_lowered": any(
                c.get("name") == "protected_tests" and c.get("detail", {}).get("lowered_assertions")
                for c in safety_report.get("checks", [])
            ),
            "blocking_fixes": [],
            "allowed_fix_files": [],
            "required_tests": [],
            "risk_summary": f"Hard safety check: {safety_overall}",
        }
        save_run_file(run_dir, "review.yaml", yaml.safe_dump(review_yaml, allow_unicode=True))

        return {
            "review_result": safety_overall,
            "review_summary": review_yaml["risk_summary"],
            "next_fixes": [],
            "allowed_fix_files": [],
            "backend_calls": {
                "reviewer": {"backend": "safety_short_circuit", "model": "", "exit_code": 0}
            },
        }

    # --- Codex 复审 ---
    prompt = build_reviewer_prompt(state)
    save_run_file(run_dir, "reviewer-prompt.md", prompt)

    result = codex_exec(
        prompt=prompt,
        model=model,
        cwd=project_path,
        timeout=600,
        stdout_log=str(Path(run_dir) / "reviewer-stdout.log"),
        stderr_log=str(Path(run_dir) / "reviewer-stderr.log"),
    )

    review_content = result.get("stdout", "")
    save_run_file(run_dir, "review.md", review_content)

    review_yaml = _extract_review_yaml(review_content)
    verdict = _validate_review_verdict(review_yaml, state)

    save_run_file(run_dir, "review.yaml", yaml.safe_dump(review_yaml, allow_unicode=True))

    backend = result.get("backend", "codex")
    fallback_from = result.get("fallback_from", "")

    return {
        "review_result": verdict,
        "review_summary": review_yaml.get("risk_summary", ""),
        "next_fixes": review_yaml.get("blocking_fixes", []),
        "allowed_fix_files": review_yaml.get("allowed_fix_files", []),
        "backend_calls": {
            "reviewer": {
                "backend": backend,
                "model": model,
                "exit_code": result.get("exit_code", -1),
                "stdout_log": str(Path(run_dir) / "reviewer-stdout.log"),
                "stderr_log": str(Path(run_dir) / "reviewer-stderr.log"),
                "fallback_from": fallback_from,
                "fallback_reason": "codex CLI unavailable" if fallback_from else "",
            }
        },
    }


def _extract_review_yaml(text: str) -> dict[str, Any]:
    defaults = {
        "verdict": "fail",
        "test_exit_code": -1,
        "files_changed": 0,
        "diff_lines": 0,
        "forbidden_touched": False,
        "tests_deleted": False,
        "assertions_lowered": False,
        "blocking_fixes": [],
        "allowed_fix_files": [],
        "required_tests": [],
        "risk_summary": "",
    }
    if "```yaml" in text:
        parts = text.split("```yaml", 1)
        if len(parts) > 1:
            yaml_part = parts[1].split("```", 1)[0]
            try:
                parsed = yaml.safe_load(yaml_part)
                if isinstance(parsed, dict):
                    defaults.update(parsed)
            except yaml.YAMLError:
                pass

    # Normalize: YAML fix_1: text 会被解析成 dict
    for key in ["blocking_fixes", "allowed_fix_files", "required_tests"]:
        val = defaults.get(key, [])
        if isinstance(val, list):
            defaults[key] = [_normalize_fix(v) for v in val if v is not None]
        else:
            defaults[key] = []

    return defaults


def _normalize_fix(item: Any) -> str:
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        return "; ".join(f"{k}: {v}" for k, v in item.items())
    return str(item or "")


def _validate_review_verdict(review_yaml: dict[str, Any], state: dict[str, Any]) -> str:
    """硬规则兜底验证."""
    if review_yaml.get("tests_deleted", False):
        return "blocked"
    if review_yaml.get("assertions_lowered", False):
        return "blocked"
    if review_yaml.get("forbidden_touched", False):
        return "human_gate"
    fix_round = state.get("fix_round", 0)
    max_rounds = state.get("max_fix_rounds", 3)
    verdict = review_yaml.get("verdict", "fail")
    if verdict == "fail" and fix_round >= max_rounds:
        return "blocked"
    return verdict
