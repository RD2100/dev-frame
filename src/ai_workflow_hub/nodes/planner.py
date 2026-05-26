"""Planner 节点 — 调用 Codex/GPT-5.5 生成计划."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..codex_client import codex_exec
from ..config_loader import _hub_dir
from ..run_store import save_run_file


def build_planner_prompt(state: dict[str, Any]) -> str:
    """构建 planner prompt."""
    prompts_dir = _hub_dir() / "src" / "ai_workflow_hub" / "prompts"
    template = (prompts_dir / "planner.md").read_text(encoding="utf-8")

    # 注入上下文
    context = f"""
## Task
- Title: {state.get("task_title", "")}
- Description: {state.get("task_description", "")}
- Risk Level: {state.get("task_risk", "medium")}

## Project Config
```yaml
{state.get("project_config", {})}
```

## Current Branch
{state.get("current_branch", "")}

## Mode
dry_run: {state.get("dry_run", True)}
"""
    return template + "\n\n" + context


def planner_node(state: dict[str, Any]) -> dict[str, Any]:
    """执行计划节点.

    调用 Codex 生成计划，写入 plan.md，更新 state.
    """
    run_dir = state.get("run_dir", "")
    project_path = state.get("project_path", "")
    model = state.get("planner_model", "gpt-5.5-codex")

    # 构建 prompt
    prompt = build_planner_prompt(state)
    save_run_file(run_dir, "planner-prompt.md", prompt)

    # Resolve planner timeout budget: env > config > default 600
    import os as _os
    budget = int(_os.environ.get("AIHUB_PLANNER_TIMEOUT_SECONDS", "0"))
    if not budget:
        from ..config_loader import get_execution_policy
        budget = get_execution_policy().get("timeouts", {}).get("planner_seconds", 600)

    # Trace: record planner invocation with budget + prompt metrics
    from ..cli import _write_trace
    import time as _time
    t0 = _time.time()
    wf_text = state.get("workflow_text", "")
    task_desc = state.get("task_description", "")
    af_count = len(state.get("allowed_files", []))
    ff_count = len(state.get("forbidden_files", []))
    _write_trace(run_dir, last_node="planner", last_event="requesting_model",
                 last_model=model, last_backend="codex_proxy",
                 timeout_budget_seconds=budget,
                 planner_prompt_chars=len(prompt),
                 workflow_text_chars=len(wf_text),
                 task_description_chars=len(task_desc),
                 allowed_files_count=af_count,
                 forbidden_files_count=ff_count)

    # 调用 Codex
    result = codex_exec(
        prompt=prompt,
        model=model,
        cwd=project_path,
        timeout=budget,
        stdout_log=str(Path(run_dir) / "planner-stdout.log"),
        stderr_log=str(Path(run_dir) / "planner-stderr.log"),
    )
    elapsed = round(_time.time() - t0, 2)
    # Trace update: post-model metrics
    _write_trace(run_dir, last_node="planner", last_event=f"response_received_{result.get('exit_code',-1)}",
                 last_model=model, last_backend=result.get("backend", "codex"),
                 elapsed_seconds=elapsed, timeout_source="planner_codex_exec")

    # 保存 plan
    plan_content = result.get("stdout", "")
    save_run_file(run_dir, "plan.md", plan_content)

    # 解析 plan 中的关键字段（简单解析，完整解析由各节点自行处理）
    allowed_files = _extract_section(plan_content, "Allowed Files")
    forbidden_files = _extract_section(plan_content, "Forbidden Files")
    test_commands = state.get("test_commands", {})

    backend = result.get("backend", "codex")  # codex or http_fallback
    fallback_from = result.get("fallback_from", "")

    return {
        "plan": plan_content,
        "allowed_files": allowed_files,
        "forbidden_files": forbidden_files,
        "error_message": result.get("stderr", ""),
        "backend_calls": {
            "planner": {
                "backend": backend,
                "model": model,
                "exit_code": result.get("exit_code", -1),
                "stdout_log": str(Path(run_dir) / "planner-stdout.log"),
                "stderr_log": str(Path(run_dir) / "planner-stderr.log"),
                "fallback_from": fallback_from,
                "fallback_reason": "codex CLI unavailable" if fallback_from else "",
            }
        },
    }


def _extract_section(text: str, section_name: str) -> list[str]:
    """从 markdown 中提取某个 section 的内容."""
    lines = text.split("\n")
    capturing = False
    items = []
    for line in lines:
        if section_name in line:
            capturing = True
            continue
        if capturing:
            if line.startswith("##") or line.startswith("# "):
                break
            stripped = line.strip()
            if stripped.startswith("- "):
                item = stripped[2:].strip()
                # 提取文件路径
                if "`" in item:
                    import re
                    match = re.search(r"`([^`]+)`", item)
                    if match:
                        items.append(match.group(1))
                elif item:
                    items.append(item.split("(")[0].strip())
    return items
