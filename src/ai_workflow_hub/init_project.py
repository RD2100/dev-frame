"""Project initialization — aihub init."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def detect_project_type(path: str) -> str:
    """Detect project type from files."""
    root = Path(path)
    if (root / "pyproject.toml").exists() or (root / "setup.py").exists() or list(root.glob("*.py")):
        return "python"
    if (root / "package.json").exists():
        return "node"
    if (root / "build.gradle").exists() or (root / "build.gradle.kts").exists():
        return "android"
    return "generic"


def suggest_test_commands(path: str, proj_type: str) -> dict[str, str]:
    """Suggest test commands based on project type."""
    root = Path(path)
    if proj_type == "python":
        cmds = {}
        if list(root.glob("tests/**/*.py")) or list(root.glob("test_*.py")):
            cmds["unit_test"] = "python -m pytest tests/ -x --tb=short 2>/dev/null || python -m unittest discover tests/"
        if (root / "pyproject.toml").exists():
            cmds["lint"] = "ruff check . 2>/dev/null || python -m py_compile *.py"
            cmds["typecheck"] = "mypy src/ 2>/dev/null || echo 'TODO: mypy not configured'"
        return cmds
    elif proj_type == "node":
        return {"lint": "npm run lint 2>/dev/null || echo TODO", "unit_test": "npm test"}
    return {"lint": "echo TODO", "unit_test": "echo TODO"}


def generate_workflow_md(path: str, proj_type: str, test_cmds: dict[str, str]) -> str:
    return f"""# Workflow Rules

## Project
- Type: {proj_type}
- Init: aihub init

## Test Commands
{chr(10).join(f'- {k}: `{v}`' for k,v in test_cmds.items()) if test_cmds else '- TODO: add test commands'}

## Protected Tests
- "tests/**"
- "**/test_*.py"

## Forbidden Paths
- ".env*"
- "secrets/**"
- "production/**"

## Human Gate Triggers
- auth
- payment
- database_migration
- deploy
"""


def init_project(path: str = ".", proj_type: str = "", force: bool = False,
                 auto_register: bool = False) -> dict[str, Any]:
    """Initialize project for ai-workflow-hub."""
    root = Path(path).resolve()
    if not root.exists():
        return {"error": f"Path not found: {path}"}

    # Auto-detect
    if not proj_type:
        from .project_detect import detect_project
        detected = detect_project(str(root))
        ptype = detected["type"]
        test_cmds = detected["test_commands"]
        confidence = detected["confidence"]
    else:
        ptype = proj_type
        test_cmds = suggest_test_commands(str(root), ptype)
        confidence = 1.0

    ai_dir = root / ".aiworkflow"
    wf_path = ai_dir / "WORKFLOW.md"

    if wf_path.exists() and not force:
        return {"warning": f"WORKFLOW.md already exists: {wf_path}", "project_type": ptype}

    test_cmds = test_cmds or suggest_test_commands(str(root), ptype)
    wf_content = generate_workflow_md(str(root), ptype, test_cmds)

    ai_dir.mkdir(parents=True, exist_ok=True)
    wf_path.write_text(wf_content, encoding="utf-8")

    result: dict[str, Any] = {
        "project_type": ptype,
        "workflow_file": str(wf_path),
        "test_commands": test_cmds,
        "registered": False,
        "confidence": confidence,
    }

    # Auto-register in projects.yaml
    if auto_register:
        from .project_registry import find_project, add_project
        proj_id = root.name
        existing = find_project(proj_id)
        if not existing:
            add_project(proj_id, proj_id, str(root))
            result["registered"] = True

    return result
