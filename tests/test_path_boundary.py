"""Path boundary validation for worktree and run storage security.

Prevents worktree path escapes and ensures run directories are
contained within the expected hub directory.
"""

import os
import tempfile
from pathlib import Path

import pytest


def validate_contained(child: str, parent: str) -> bool:
    """Check that child path is within parent directory.

    Resolves both paths to absolute canonical form before comparing.
    Returns True if child is equal to or nested under parent.
    """
    try:
        child_resolved = Path(child).resolve()
        parent_resolved = Path(parent).resolve()
        return str(child_resolved).startswith(str(parent_resolved) + os.sep) or child_resolved == parent_resolved
    except (OSError, ValueError):
        return False


def safe_worktree_path(project_path: str, task_id: str, run_suffix: str) -> Path | None:
    """Build and validate a worktree path under the project parent.

    Returns the validated Path, or None when the computed path escapes
    the project boundary (e.g. via .. traversal in run_suffix).
    """
    project_parent = str(Path(project_path).resolve().parent)
    candidate_dir = str(Path(project_parent) / "aihub-worktrees" / task_id)
    candidate = str(Path(candidate_dir) / f"task-{run_suffix}")

    if not validate_contained(candidate, project_parent):
        return None
    return Path(candidate)


class TestPathBoundaryValidation:
    def test_child_inside_parent(self):
        assert validate_contained("/tmp/worktree", "/tmp") is True
        assert validate_contained("/tmp/a/b/c", "/tmp") is True

    def test_child_equals_parent(self):
        assert validate_contained("/tmp", "/tmp") is True

    def test_child_outside_parent(self):
        assert validate_contained("/etc/passwd", "/tmp") is False

    def test_path_traversal_attack_rejected(self):
        project_parent = "C:/projects/myapp"
        candidate = "C:/projects/myapp/../other-app/worktree"
        assert validate_contained(candidate, project_parent) is False

    def test_deep_traversal_escapes_boundary(self):
        """.. traversal that escapes the project parent must be rejected."""
        # From C:/projects/aihub-worktrees/task-x/task-... to C:/windows
        # needs to go up enough levels to reach drive root first
        result = safe_worktree_path(
            "C:/projects/myapp",
            "task-abc",
            "../../../../../windows/system32",
        )
        assert result is None

    def test_traversal_inside_boundary_allowed(self):
        """.. traversal that stays inside project parent is allowed."""
        # Goes from aihub-worktrees/task-abc/ up to projects/ level
        # but stays within C:/projects
        result = safe_worktree_path(
            "C:/projects/myapp",
            "task-abc",
            "../../other-project",
        )
        # This stays under C:/projects, so should be allowed
        assert result is not None

    def test_normal_path_allowed(self):
        result = safe_worktree_path(
            "C:/projects/myapp",
            "task-abc",
            "abcd1234-abcd1234",
        )
        assert result is not None
        assert "aihub-worktrees" in str(result)

    def test_symlink_dotdot(self):
        with tempfile.TemporaryDirectory() as tmp:
            parent = os.path.join(tmp, "parent")
            os.makedirs(parent)
            assert validate_contained(parent, tmp) is True
            assert validate_contained(os.path.join(tmp, "outside"), parent) is False

    def test_empty_paths(self):
        assert validate_contained("", "/tmp") is False

    def test_worktree_path_stays_under_project_parent(self):
        result = safe_worktree_path("C:/projects/app", "task-x", "run-001")
        assert result is not None
        assert "projects" in result.as_posix() and "aihub-worktrees" in result.as_posix()
        assert "aihub-worktrees" in str(result)
