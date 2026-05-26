"""项目注册表 — 管理 projects.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .config_loader import get_projects, save_projects, load_project_workflow_config
from .schemas import ProjectEntry


def list_projects() -> list[dict[str, Any]]:
    """列出所有项目."""
    data = get_projects() or {}
    projects = data.get("projects") or []
    return [p for p in projects if isinstance(p, dict)]


def find_project(project_id: str) -> dict[str, Any] | None:
    """根据 ID 查找项目."""
    for p in list_projects():
        if p.get("id") == project_id:
            return p
    return None


def add_project(
    project_id: str,
    name: str,
    path: str,
    config: str = ".aiworkflow.yaml",
    priority: str = "medium",
) -> bool:
    """添加项目到注册表."""
    data = get_projects() or {}
    if not data.get("projects"):
        data["projects"] = []

    # 检查重复
    for p in data["projects"]:
        if p.get("id") == project_id:
            return False

    data["projects"].append({
        "id": project_id,
        "name": name,
        "path": path,
        "config": config,
        "enabled": True,
        "priority": priority,
    })
    save_projects(data)
    return True


def validate_project(project_id: str) -> tuple[bool, list[str]]:
    """校验项目配置.

    Returns:
        (is_valid, messages): 校验结果和消息列表.
    """
    messages: list[str] = []
    project = find_project(project_id)
    if not project:
        return False, [f"项目 '{project_id}' 不在注册表中"]

    path = Path(project.get("path", ""))
    if not path.exists():
        messages.append(f"ERROR: 项目路径不存在: {path}")

    config_file = path / project.get("config", ".aiworkflow.yaml")
    if not config_file.exists():
        messages.append(f"WARNING: 工作流配置文件不存在: {config_file}")
    else:
        wf_config = load_project_workflow_config(str(path), project.get("config", ".aiworkflow.yaml"))
        _validate_workflow_config(wf_config, messages)

    return len([m for m in messages if m.startswith("ERROR")]) == 0, messages


def _validate_workflow_config(config: dict[str, Any], messages: list[str]) -> None:
    """校验 .aiworkflow.yaml."""
    if not config:
        messages.append("ERROR: .aiworkflow.yaml 为空或无法解析")
        return

    project = config.get("project", {})
    if not project.get("id"):
        messages.append("ERROR: project.id 未定义")

    commands = config.get("commands", {})
    if not commands:
        messages.append("WARNING: commands 为空，无法执行任何测试命令")

    policy = config.get("policy", {})

    forbidden = policy.get("forbidden_paths", [])
    if not forbidden:
        messages.append("WARNING: forbidden_paths 为空，没有受保护路径")

    protected = policy.get("protected_tests", [])
    if not protected:
        messages.append("WARNING: protected_tests 为空，测试文件没有保护")

    # 检查命令
    for cmd_name, cmd_value in commands.items():
        if not cmd_value or "TODO" in str(cmd_value).upper():
            messages.append(f"INFO: 命令 '{cmd_name}' 尚未配置 (TODO)")
