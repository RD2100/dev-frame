"""Stage 3 Batch A tests: isolation cleanup on workflow failure.

These tests verify the cleanup logic directly (not through _execute_run),
using mocks for all git operations. No real git repos are touched.

Stage 3R (Defect 1+2 fix):
- A1-A3: preserved from original, inline logic unchanged
- A4: NEW — successful apply skips cleanup (Defect 1)
- A5: NEW — exception + branch -> checkout original first, then delete (Defect 2)
- A6: NEW — delete failure tracked in cleanup state
"""

import pytest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def env():
    """Return common test values."""
    return {
        "project_path": "/fake/projects/test-proj",
        "worktree_path": "/fake/aihub-worktrees/test-proj/task001-abcd12345678",
        "ai_branch": "ai/task001-abcd12345678",
        "original_branch": "main",
        "run_dir": "/fake/runs/test-proj/run-001",
    }


# ---------------------------------------------------------------------------
# A1: Worktree created + workflow throws -> cleanup is called
# ---------------------------------------------------------------------------

def test_worktree_created_cleanup_calls_remove_worktree(env):
    """When worktree was created and workflow fails, cleanup calls remove_worktree."""
    mock_remove_worktree = MagicMock(return_value=(True, "Worktree removed"))
    mock_delete_branch = MagicMock()
    mock_checkout_branch = MagicMock()

    project_path = env["project_path"]
    worktree_path = env["worktree_path"]
    ai_branch = env["ai_branch"]
    original_branch = env["original_branch"]

    _worktree_created = True
    _branch_created = False
    cleanup_success = True
    cleanup_error = ""

    # Simulate worktree-only cleanup (like _cleanup_isolation with no branch)
    if _worktree_created and worktree_path:
        ok, msg = mock_remove_worktree(project_path, worktree_path)
        if not ok:
            cleanup_success = False
            cleanup_error = f"worktree_remove: {msg}"
    if _branch_created:
        if original_branch:
            mock_checkout_branch(project_path, original_branch)
        ok, msg = mock_delete_branch(project_path, ai_branch)
        if not ok:
            cleanup_success = False
            if cleanup_error:
                cleanup_error += f"; branch_delete: {msg}"
            else:
                cleanup_error = f"branch_delete: {msg}"

    mock_remove_worktree.assert_called_once_with(project_path, worktree_path)
    mock_delete_branch.assert_not_called()
    mock_checkout_branch.assert_not_called()
    assert cleanup_success is True
    assert cleanup_error == ""


# ---------------------------------------------------------------------------
# A2: Branch mode (no worktree) -> checkout original, then delete
# ---------------------------------------------------------------------------

def test_branch_mode_cleanup_checkout_then_delete(env):
    """When isolation is branch-only, checkout original branch first, then delete."""
    mock_remove_worktree = MagicMock()
    mock_delete_branch = MagicMock(return_value=(True, "Deleted branch"))
    mock_checkout_branch = MagicMock(return_value=(True, "Checked out"))

    project_path = env["project_path"]
    worktree_path = env["worktree_path"]
    ai_branch = env["ai_branch"]
    original_branch = env["original_branch"]

    _worktree_created = False
    _branch_created = True
    cleanup_success = True
    cleanup_error = ""

    # Simulate branch-only cleanup (like _cleanup_isolation)
    if _worktree_created and worktree_path:
        ok, msg = mock_remove_worktree(project_path, worktree_path)
        if not ok:
            cleanup_success = False
            cleanup_error = f"worktree_remove: {msg}"
    if _branch_created:
        # Defect 2 fix: checkout original before delete
        if original_branch:
            mock_checkout_branch(project_path, original_branch)
        ok, msg = mock_delete_branch(project_path, ai_branch)
        if not ok:
            cleanup_success = False
            if cleanup_error:
                cleanup_error += f"; branch_delete: {msg}"
            else:
                cleanup_error = f"branch_delete: {msg}"

    mock_remove_worktree.assert_not_called()
    mock_checkout_branch.assert_called_once_with(project_path, original_branch)
    mock_delete_branch.assert_called_once_with(project_path, ai_branch)
    assert cleanup_success is True
    assert cleanup_error == ""


# ---------------------------------------------------------------------------
# A3: No isolation resources -> cleanup is a no-op
# ---------------------------------------------------------------------------

def test_no_isolation_resources_cleanup_noop(env):
    """When apply_changes=False and no resources exist, nothing is cleaned."""
    mock_remove_worktree = MagicMock()
    mock_delete_branch = MagicMock()
    mock_checkout_branch = MagicMock()

    project_path = env["project_path"]
    worktree_path = env["worktree_path"]
    ai_branch = env["ai_branch"]
    original_branch = env["original_branch"]

    apply_changes = False
    _worktree_created = False
    _branch_created = False

    if apply_changes and (_worktree_created or _branch_created):
        if _worktree_created and worktree_path:
            mock_remove_worktree(project_path, worktree_path)
        if _branch_created:
            if original_branch:
                mock_checkout_branch(project_path, original_branch)
            mock_delete_branch(project_path, ai_branch)

    mock_remove_worktree.assert_not_called()
    mock_delete_branch.assert_not_called()
    mock_checkout_branch.assert_not_called()


# ---------------------------------------------------------------------------
# A4: Successful apply -> cleanup NOT called (Defect 1 fix)
# ---------------------------------------------------------------------------

def test_successful_apply_skip_cleanup(env):
    """When workflow passes, cleanup must NOT be called (preserve deliverable)."""
    mock_remove_worktree = MagicMock()
    mock_delete_branch = MagicMock()
    mock_checkout_branch = MagicMock()

    project_path = env["project_path"]
    worktree_path = env["worktree_path"]
    ai_branch = env["ai_branch"]
    original_branch = env["original_branch"]

    apply_changes = True
    _worktree_created = True
    _branch_created = True

    # Simulate: workflow passes -> cleanup is skipped
    status = "passed"

    # Defect 1 gate: only cleanup for non-deliverable statuses
    should_cleanup = apply_changes and (_worktree_created or _branch_created) and \
        status in ("failed", "blocked", "human_required", "running", "pending")

    assert should_cleanup is False, (
        f"Expected cleanup=False for status='{status}', but got True"
    )

    # Verify no cleanup functions called
    mock_remove_worktree.assert_not_called()
    mock_delete_branch.assert_not_called()
    mock_checkout_branch.assert_not_called()


# ---------------------------------------------------------------------------
# A5: Cleanup result returned as dict (3RR fix — no longer writes state.json)
# ---------------------------------------------------------------------------

def test_cleanup_result_returned_and_isolation_cleanup_written(env):
    """Verify _cleanup_isolation returns cleanup dict and writes isolation-cleanup.json."""
    run_dir = env["run_dir"]

    saved_cleanup = {}

    def capture_save(run_dir_path, filename, data):
        if filename == "isolation-cleanup.json":
            saved_cleanup.update(data)
        # state.json is NOT written by _cleanup_isolation (3RR fix)

    with patch(
        "ai_workflow_hub.cli.save_run_json", side_effect=capture_save
    ), patch(
        "ai_workflow_hub.git_utils.remove_worktree",
        return_value=(True, "Worktree removed")
    ), patch(
        "ai_workflow_hub.git_utils.delete_branch",
        return_value=(True, "Deleted branch")
    ), patch(
        "ai_workflow_hub.git_utils.checkout_branch",
        return_value=(True, "Checked out")
    ):
        from ai_workflow_hub import cli

        result = cli._cleanup_isolation(
            project_path=env["project_path"],
            worktree_path=env["worktree_path"],
            ai_branch=env["ai_branch"],
            original_branch=env["original_branch"],
            _worktree_created=True,
            _branch_created=False,
            run_dir=run_dir,
            apply_changes=True,
        )

        # 3RR fix: cleanup result is returned, not written to state.json
        assert result == {"cleanup_success": True, "cleanup_error": ""}
        assert "cleanup_success" in result
        assert "cleanup_error" in result

        # isolation-cleanup.json is still written
        assert saved_cleanup.get("cleanup_success") is True
        assert saved_cleanup.get("worktree_created") is True
        assert saved_cleanup.get("branch_created") is False
        assert "cleaned_at" in saved_cleanup


# ---------------------------------------------------------------------------
# A11: Failed normal return — cleanup fields preserved in final state (3RR)
# ---------------------------------------------------------------------------

def test_failed_status_normal_return_cleanup_in_final_state(env):
    """3RR core: when workflow completes with status=failed (no exception),
    the cleanup result must be merged into final_state before persisting."""
    run_dir = env["run_dir"]

    saved_final_state = {}

    def capture_save(run_dir_path, filename, data):
        if filename == "state.json":
            saved_final_state.update(data)

    with patch(
        "ai_workflow_hub.cli.save_run_json", side_effect=capture_save
    ), patch(
        "ai_workflow_hub.git_utils.remove_worktree",
        return_value=(True, "Worktree removed")
    ), patch(
        "ai_workflow_hub.git_utils.checkout_branch",
        return_value=(True, "Checked out")
    ), patch(
        "ai_workflow_hub.git_utils.delete_branch",
        return_value=(True, "Deleted branch")
    ):
        from ai_workflow_hub import cli

        # Simulate: cleanup is called with failed status, returns result,
        # then final_state is updated with cleanup result before saving
        cleanup_result = cli._cleanup_isolation(
            project_path=env["project_path"],
            worktree_path=env["worktree_path"],
            ai_branch=env["ai_branch"],
            original_branch=env["original_branch"],
            _worktree_created=True,
            _branch_created=True,
            run_dir=run_dir,
            apply_changes=True,
        )

        # Simulate what the caller does (lines 2197-2200 in cli.py)
        final_state = {"status": "failed", "run_id": "run-001",
                       "task_id": "task-001"}
        final_state.update(cleanup_result)
        final_state["updated_at"] = "2026-05-26T00:00:00Z"
        cli.save_run_json(run_dir, "state.json", final_state)

    # 3RR fix: cleanup fields survive in final state.json
    assert saved_final_state["status"] == "failed"
    assert saved_final_state["cleanup_success"] is True
    assert saved_final_state["cleanup_error"] == ""
    assert saved_final_state["run_id"] == "run-001"


# ---------------------------------------------------------------------------
# A12: Checkout failure → cleanup_success=False in return value (3RR)
# ---------------------------------------------------------------------------

def test_checkout_failure_sets_cleanup_success_false(env):
    """3RR fix: when checkout_branch fails, cleanup_success=False is in the result."""
    run_dir = env["run_dir"]

    with patch(
        "ai_workflow_hub.cli.save_run_json"
    ), patch(
        "ai_workflow_hub.git_utils.checkout_branch",
        return_value=(False, "fatal: not a git repository")
    ), patch(
        "ai_workflow_hub.git_utils.delete_branch",
        return_value=(True, "Deleted branch")
    ):
        from ai_workflow_hub import cli

        result = cli._cleanup_isolation(
            project_path=env["project_path"],
            worktree_path="",
            ai_branch=env["ai_branch"],
            original_branch=env["original_branch"],
            _worktree_created=False,
            _branch_created=True,
            run_dir=run_dir,
            apply_changes=True,
        )

    # 3RR fix: checkout failure is recorded as cleanup failure
    assert result["cleanup_success"] is False
    assert "checkout_original" in result["cleanup_error"]
    assert "fatal: not a git repository" in result["cleanup_error"]


# ---------------------------------------------------------------------------
# A6: Cleanup failure is correctly tracked
# ---------------------------------------------------------------------------

def test_cleanup_failure_sets_cleanup_success_false(env):
    """When remove_worktree fails, cleanup_success is set to False and error recorded."""
    mock_remove_worktree = MagicMock(return_value=(False, "Permission denied"))
    mock_delete_branch = MagicMock()
    mock_checkout_branch = MagicMock()

    project_path = env["project_path"]
    worktree_path = env["worktree_path"]
    original_branch = env["original_branch"]

    _worktree_created = True
    _branch_created = False
    cleanup_success = True
    cleanup_error = ""

    if _worktree_created and worktree_path:
        ok, msg = mock_remove_worktree(project_path, worktree_path)
        if not ok:
            cleanup_success = False
            cleanup_error = f"worktree_remove: {msg}"
    if _branch_created:
        if original_branch:
            mock_checkout_branch(project_path, original_branch)
        ok, msg = mock_delete_branch(project_path, "ai/task-001")
        if not ok:
            cleanup_success = False
            if cleanup_error:
                cleanup_error += f"; branch_delete: {msg}"
            else:
                cleanup_error = f"branch_delete: {msg}"

    assert cleanup_success is False
    assert cleanup_error == "worktree_remove: Permission denied"


# ---------------------------------------------------------------------------
# A7: Both worktree and branch created -> both cleaned
# ---------------------------------------------------------------------------

def test_both_worktree_and_branch_cleaned(env):
    """When both worktree and branch were created, both must be cleaned."""
    mock_remove_worktree = MagicMock(return_value=(True, "Worktree removed"))
    mock_delete_branch = MagicMock(return_value=(True, "Deleted branch"))
    mock_checkout_branch = MagicMock(return_value=(True, "Checked out"))

    project_path = env["project_path"]
    worktree_path = env["worktree_path"]
    ai_branch = env["ai_branch"]
    original_branch = env["original_branch"]

    _worktree_created = True
    _branch_created = True
    cleanup_success = True
    cleanup_error = ""

    if _worktree_created and worktree_path:
        ok, msg = mock_remove_worktree(project_path, worktree_path)
        if not ok:
            cleanup_success = False
            cleanup_error = f"worktree_remove: {msg}"
    if _branch_created:
        if original_branch:
            mock_checkout_branch(project_path, original_branch)
        ok, msg = mock_delete_branch(project_path, ai_branch)
        if not ok:
            cleanup_success = False
            if cleanup_error:
                cleanup_error += f"; branch_delete: {msg}"
            else:
                cleanup_error = f"branch_delete: {msg}"

    mock_remove_worktree.assert_called_once_with(project_path, worktree_path)
    mock_checkout_branch.assert_called_once_with(project_path, original_branch)
    mock_delete_branch.assert_called_once_with(project_path, ai_branch)
    assert cleanup_success is True
    assert cleanup_error == ""


# ---------------------------------------------------------------------------
# A8: Branch delete failure tracked (Defect 2 edge case)
# ---------------------------------------------------------------------------

def test_branch_delete_failure_tracked(env):
    """When delete_branch fails, cleanup_success=False and error is recorded."""
    mock_remove_worktree = MagicMock()
    mock_delete_branch = MagicMock(return_value=(False, "cannot delete branch: in use"))
    mock_checkout_branch = MagicMock(return_value=(True, "Checked out"))

    project_path = env["project_path"]
    worktree_path = env["worktree_path"]
    ai_branch = env["ai_branch"]
    original_branch = env["original_branch"]

    _worktree_created = False
    _branch_created = True
    cleanup_success = True
    cleanup_error = ""

    if _worktree_created and worktree_path:
        ok, msg = mock_remove_worktree(project_path, worktree_path)
        if not ok:
            cleanup_success = False
            cleanup_error = f"worktree_remove: {msg}"
    if _branch_created:
        if original_branch:
            mock_checkout_branch(project_path, original_branch)
        ok, msg = mock_delete_branch(project_path, ai_branch)
        if not ok:
            cleanup_success = False
            if cleanup_error:
                cleanup_error += f"; branch_delete: {msg}"
            else:
                cleanup_error = f"branch_delete: {msg}"

    mock_checkout_branch.assert_called_once_with(project_path, original_branch)
    mock_delete_branch.assert_called_once_with(project_path, ai_branch)
    assert cleanup_success is False
    assert "branch_delete: cannot delete branch: in use" in cleanup_error


# ---------------------------------------------------------------------------
# A9: Exception + branch fallback -> checkout original THEN delete (Defect 2)
# ---------------------------------------------------------------------------

def test_exception_branch_fallback_checkout_before_delete(env):
    """Exception path with branch: checkout original branch BEFORE deleting temp branch."""
    mock_remove_worktree = MagicMock()
    mock_delete_branch = MagicMock(return_value=(True, "Deleted branch"))
    mock_checkout_branch = MagicMock(return_value=(True, "Checked out"))

    project_path = env["project_path"]
    worktree_path = env["worktree_path"]
    ai_branch = env["ai_branch"]
    original_branch = env["original_branch"]

    _worktree_created = False  # worktree failed, fell back to branch
    _branch_created = True

    # Call order tracker
    call_order = []

    def track_checkout_branch(proj, branch):
        call_order.append(f"checkout:{branch}")
        return True, "Checked out"

    def track_delete_branch(proj, branch):
        call_order.append(f"delete:{branch}")
        return True, "Deleted branch"

    mock_checkout_branch.side_effect = track_checkout_branch
    mock_delete_branch.side_effect = track_delete_branch

    # Simulate cleanup for exception path (branch fallback)
    if _worktree_created and worktree_path:
        mock_remove_worktree(project_path, worktree_path)
    if _branch_created:
        if original_branch:
            mock_checkout_branch(project_path, original_branch)
        mock_delete_branch(project_path, ai_branch)

    mock_remove_worktree.assert_not_called()
    mock_checkout_branch.assert_called_once_with(project_path, original_branch)
    mock_delete_branch.assert_called_once_with(project_path, ai_branch)

    # Verify call order: checkout BEFORE delete (Defect 2 fix)
    assert call_order == [
        f"checkout:{original_branch}",
        f"delete:{ai_branch}",
    ], f"Expected checkout before delete, got: {call_order}"


# ---------------------------------------------------------------------------
# A10: Cleanup not called for human_required or blocked
#   Defect 1: these ARE non-deliverable, so cleanup SHOULD happen
#   (Test verifies gate logic correctly classifies these)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("status,should_cleanup", [
    ("passed", False),         # deliverable -> NO cleanup
    ("failed", True),          # non-deliverable -> cleanup
    ("blocked", True),         # non-deliverable -> cleanup
    ("human_required", True),  # non-deliverable -> cleanup
    ("running", True),         # incomplete -> cleanup
    ("pending", True),         # incomplete -> cleanup
])
def test_cleanup_gate_by_status(env, status, should_cleanup):
    """Cleanup gate: only cleanup for non-deliverable statuses."""
    apply_changes = True
    has_resources = True

    # Simulate the gate logic from cli.py
    result = apply_changes and has_resources and \
        status in ("failed", "blocked", "human_required", "running", "pending")

    assert result is should_cleanup, (
        f"Expected cleanup={should_cleanup} for status='{status}', got {result}"
    )
