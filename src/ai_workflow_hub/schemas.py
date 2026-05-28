"""Workflow state schema — Pydantic model for the LangGraph state machine."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class WorkflowState(BaseModel):
    """LangGraph 工作流状态 — 贯穿所有节点的共享状态."""

    # --- 项目信息 ---
    project_id: str = ""
    project_name: str = ""
    project_type: str = ""
    project_path: str = ""
    project_config: dict[str, Any] = Field(default_factory=dict)

    # --- 任务信息 ---
    task_id: str = ""
    task_title: str = ""
    task_description: str = ""
    task_risk: str = "medium"  # low | medium | high

    # --- 运行信息 ---
    run_id: str = ""
    run_dir: str = ""
    current_branch: str = ""
    original_branch: str = ""  # branch before isolation, used for cleanup checkout
    worktree_path: str = ""
    base_project_path: str = ""
    isolation_mode: str = "branch"  # worktree | branch
    isolation_fallback_reason: str = ""
    coding_backend: str = ""  # opencode | claude
    workflow_file: str = ""   # .aiworkflow/WORKFLOW.md path
    workflow_text: str = ""   # WORKFLOW.md content (capped)
    ci_report: str = ""       # CI failure report for fix injection

    # --- LangGraph 持久化 ---
    thread_id: str = ""  # run_id 映射为 thread_id，用于 checkpointer
    resume_from: str = ""  # 恢复时跳过的节点名称

    # --- 执行模式 ---
    dry_run: bool = True
    apply_changes: bool = False
    run_tests: bool = False  # dry-run 下是否显式执行测试

    # --- 模型分配 ---
    planner_model: str = ""
    reviewer_model: str = ""
    executor_model: str = ""
    fixer_model: str = ""

    # --- 计划输出 ---
    plan: str = ""
    constraints: dict[str, Any] = Field(default_factory=dict)
    allowed_files: list[str] = Field(default_factory=list)
    forbidden_files: list[str] = Field(default_factory=list)
    protected_tests: list[str] = Field(default_factory=list)

    # --- 测试命令 ---
    test_commands: dict[str, str] = Field(default_factory=dict)

    # --- 执行结果 ---
    execution_log: str = ""
    test_output: str = ""
    test_exit_code: int = -1

    # --- Git diff (增强: 包含 name-status) ---
    git_diff: str = ""
    changed_files: list[str] = Field(default_factory=list)
    changed_files_status: dict[str, str] = Field(default_factory=dict)  # {filepath: A|M|D|R|...}
    diff_line_count: int = 0

    # --- 复审结果 ---
    review_result: str = ""  # pass | fail | human_gate | blocked
    review_summary: str = ""
    next_fixes: list[str] = Field(default_factory=list)
    allowed_fix_files: list[str] = Field(default_factory=list)

    # --- 修复控制 ---
    fix_round: int = 0
    max_fix_rounds: int = 3

    # --- 安全标记 ---
    dangerous_change: bool = False
    human_required: bool = False

    # --- 后端调用审计 ---
    backend_calls: dict[str, Any] = Field(default_factory=dict)

    # --- 副作用追踪 (防恢复时重复调用 OpenCode) ---
    executed_nodes: list[str] = Field(default_factory=list)  # 已执行的节点名
    side_effect_nodes: list[str] = Field(
        default_factory=lambda: ["execute_node"]
    )  # 仅 execute_node 防恢复时重复调用 OpenCode

    # --- 状态 ---
    status: str = "pending"  # pending | running | passed | failed | blocked | human_required
    error_message: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ReviewVerdict(BaseModel):
    """复审裁定结构."""

    verdict: str = "fail"  # pass | fail | human_gate | blocked
    test_exit_code: int = -1
    files_changed: int = 0
    diff_lines: int = 0
    forbidden_touched: bool = False
    tests_deleted: bool = False
    assertions_lowered: bool = False
    blocking_fixes: list[str] = Field(default_factory=list)
    allowed_fix_files: list[str] = Field(default_factory=list)
    required_tests: list[str] = Field(default_factory=list)
    risk_summary: str = ""


class ProjectEntry(BaseModel):
    """projects.yaml 中的项目条目."""

    id: str
    name: str
    path: str
    config: str = ".aiworkflow.yaml"
    enabled: bool = True
    priority: str = "medium"  # low | medium | high


class TaskEntry(BaseModel):
    """tasks.yaml 中的任务条目 — v0.2 control plane."""

    id: str
    project_id: str
    title: str
    description: str = ""
    risk: str = "medium"  # low | medium | high
    status: str = "queued"  # queued | running | passed | failed | blocked | human_required | cancelled
    priority: str = "normal"  # low | normal | high | urgent
    dependencies: list[str] = Field(default_factory=list)
    coding_backend: str = ""
    last_run_id: str = ""
    retry_count: int = 0
    blocked_reason: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ProjectWorkflowConfig(BaseModel):
    """业务项目 .aiworkflow.yaml 结构."""

    project: dict[str, Any] = Field(default_factory=dict)
    commands: dict[str, str] = Field(default_factory=dict)
    policy: dict[str, Any] = Field(default_factory=dict)
    models: dict[str, str] = Field(default_factory=dict)


class RunManifest(BaseModel):
    """单次运行的文件清单."""

    run_id: str
    run_dir: str
    files: dict[str, str] = Field(default_factory=dict)
    status: str = "pending"
