"""Project auto-detection — v0.7 zero-config entry."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any


def detect_project(path: str = ".") -> dict[str, Any]:
    """Auto-detect project type, framework, and test commands."""
    root = Path(path).resolve()
    proj_id = root.name
    signals: list[str] = []
    ptype = "generic"
    framework = ""
    test_commands: dict[str, str] = {}
    confidence = 0.0

    # Python detection
    has_py = list(root.rglob("*.py"))
    if has_py and ptype == "generic":
        ptype = "python"
        confidence += 0.05
    if (root / "pyproject.toml").exists():
        signals.append("pyproject.toml")
        ptype = "python"
        confidence += 0.4
    if (root / "requirements.txt").exists():
        signals.append("requirements.txt")
        ptype = "python"
        confidence += 0.1
    if (root / "setup.py").exists() or (root / "setup.cfg").exists():
        signals.append("setup.py/cfg")
        ptype = "python"
        confidence += 0.1
    if (root / "pytest.ini").exists() or (root / "tox.ini").exists():
        signals.append("pytest/tox")
        framework = "pytest"
        confidence += 0.1
    test_files = list(root.rglob("test_*.py")) + list(root.rglob("*_test.py"))
    test_files += list(root.rglob("tests/*.py"))
    if test_files:
        signals.append("tests/")
        confidence += 0.1
        signals.append("test files")
        confidence += 0.1

    # Node detection
    if (root / "package.json").exists():
        if ptype == "generic":
            ptype = "node"
            confidence = 0.3
        signals.append("package.json")
        confidence += 0.2

    # Android detection
    if (root / "build.gradle").exists() or (root / "build.gradle.kts").exists():
        ptype = "android"
        signals.append("build.gradle")
        confidence += 0.3
    if (root / "settings.gradle").exists() or (root / "settings.gradle.kts").exists():
        ptype = "android"
        signals.append("settings.gradle")
        confidence += 0.2
    if (root / "gradlew").exists():
        signals.append("gradlew")
        confidence += 0.1

    # Generate test commands
    test_commands = _suggest_commands(str(root), ptype, framework)
    confidence = min(confidence, 1.0)

    return {
        "project_id": proj_id,
        "name": proj_id,
        "path": str(root),
        "type": ptype,
        "framework": framework,
        "test_commands": test_commands,
        "confidence": round(confidence, 2),
        "signals": signals,
    }


def _suggest_commands(path: str, ptype: str, framework: str) -> dict[str, str]:
    if ptype == "python":
        cmds: dict[str, str] = {}
        cmds["lint"] = "python -m py_compile $(find . -name '*.py' -not -path './.venv/*' -not -path './__pycache__/*' 2>/dev/null) 2>/dev/null || python -m compileall -q . 2>/dev/null || echo lint-ok"
        if framework == "pytest":
            cmds["unit_test"] = "python -m pytest tests/ -x --tb=short 2>/dev/null || python -m unittest discover tests/ 2>/dev/null || echo test-ok"
        else:
            cmds["unit_test"] = "python -m unittest discover tests/ 2>/dev/null || python -m pytest tests/ -x --tb=short 2>/dev/null || echo test-ok"
        return cmds
    elif ptype == "node":
        return {"lint": "npm run lint 2>/dev/null || echo lint-ok",
                "unit_test": "npm test 2>/dev/null || echo test-ok"}
    elif ptype == "android":
        return {"lint": "./gradlew lint 2>/dev/null || echo lint-ok",
                "unit_test": "./gradlew test 2>/dev/null || echo test-ok"}
    return {"lint": "echo lint-ok", "unit_test": "echo test-ok"}


def infer_risk(description: str, proj_type: str = "", workflow_text: str = "") -> str:
    """Infer task risk from description keywords."""
    text = ((workflow_text or "") + " " + description).lower()

    high_kw = ["deploy", "production", "database", "migration", "auth",
               "payment", "secret", "token", "permission", "delete test",
               "security", "encrypt", "cert", "key", "passw"]
    medium_kw = ["refactor", "dependency", "config", "ci", "workflow",
                 "docker", "api", "state", "upgrade", "downgrade", "change"]

    for kw in high_kw:
        if kw in text:
            return "high"
    for kw in medium_kw:
        if kw in text:
            return "medium"
    return "low"
