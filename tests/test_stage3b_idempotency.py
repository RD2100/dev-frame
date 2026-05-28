"""Stage 3 Batch B tests: Fixer error status + Goal batch duplicate execution."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Fix 1: fixer_node sets status="failed" on coding agent failure
# ---------------------------------------------------------------------------

class TestFixerErrorStatus:
    """Verify fixer_node returns status='failed' when the coding agent errors."""

    def test_fixer_sets_failed_on_nonzero_exit(self, tmp_path):
        """Exit code != 0/-1 -> status 'failed'."""
        from ai_workflow_hub.nodes.fixer import fixer_node

        run_dir = str(tmp_path)
        state = {
            "run_dir": run_dir,
            "project_path": str(tmp_path),
            "worktree_path": str(tmp_path),
            "apply_changes": True,
            "dry_run": False,
            "fix_round": 0,
            "max_fix_rounds": 3,
            "task_title": "test task",
            "test_output": "",
            "review_result": "",
            "next_fixes": ["fix-1"],
            "allowed_fix_files": ["file.py"],
            "execution_log": "",
            "git_diff": "",
            "changed_files": [],
            "changed_files_status": {},
            "diff_line_count": 0,
        }

        fake_result = {
            "stdout": "some output",
            "stderr": "FATAL ERROR: something broke",
            "exit_code": 1,
            "timed_out": False,
            "duration_seconds": 2.5,
            "command_preview": "claude fix",
        }

        with patch(
            # run_coding_agent is imported inside fixer_node from ..agent_client
            "ai_workflow_hub.agent_client.run_coding_agent",
            return_value=fake_result,
        ), patch(
            # collect_all_diff_info is module-level imported from ..git_utils
            "ai_workflow_hub.git_utils.collect_all_diff_info",
            return_value={
                "diff_text": "",
                "changed_files": [],
                "name_status": {},
                "diff_line_count": 0,
            },
        ), patch(
            "ai_workflow_hub.git_utils.save_diff_patch",
        ):
            result = fixer_node(state)

        assert result["status"] == "failed", (
            f"Expected status='failed', got status='{result.get('status')}'"
        )
        assert "FATAL ERROR" in result["error_message"]

    def test_fixer_sets_failed_on_timeout(self, tmp_path):
        """Timeout -> status 'failed'."""
        from ai_workflow_hub.nodes.fixer import fixer_node

        run_dir = str(tmp_path)
        state = {
            "run_dir": run_dir,
            "project_path": str(tmp_path),
            "worktree_path": str(tmp_path),
            "apply_changes": True,
            "dry_run": False,
            "fix_round": 0,
            "max_fix_rounds": 3,
            "task_title": "test task",
            "test_output": "",
            "review_result": "",
            "next_fixes": ["fix-1"],
            "allowed_fix_files": ["file.py"],
            "execution_log": "",
            "git_diff": "",
            "changed_files": [],
            "changed_files_status": {},
            "diff_line_count": 0,
        }

        fake_result = {
            "stdout": "",
            "stderr": "",
            "exit_code": -1,
            "timed_out": True,
            "duration_seconds": 600.0,
            "command_preview": "claude fix",
        }

        with patch(
            "ai_workflow_hub.agent_client.run_coding_agent",
            return_value=fake_result,
        ), patch(
            "ai_workflow_hub.git_utils.collect_all_diff_info",
            return_value={
                "diff_text": "",
                "changed_files": [],
                "name_status": {},
                "diff_line_count": 0,
            },
        ), patch(
            "ai_workflow_hub.git_utils.save_diff_patch",
        ):
            result = fixer_node(state)

        assert result["status"] == "failed", (
            f"Expected status='failed' on timeout, got status='{result.get('status')}'"
        )

    def test_fixer_no_status_on_success(self, tmp_path):
        """Successful execution -> no 'status' key in result."""
        from ai_workflow_hub.nodes.fixer import fixer_node

        run_dir = str(tmp_path)
        state = {
            "run_dir": run_dir,
            "project_path": str(tmp_path),
            "worktree_path": str(tmp_path),
            "apply_changes": True,
            "dry_run": False,
            "fix_round": 0,
            "max_fix_rounds": 3,
            "task_title": "test task",
            "test_output": "",
            "review_result": "",
            "next_fixes": ["fix-1"],
            "allowed_fix_files": ["file.py"],
            "execution_log": "",
            "git_diff": "",
            "changed_files": [],
            "changed_files_status": {},
            "diff_line_count": 0,
        }

        fake_result = {
            "stdout": "fix applied successfully",
            "stderr": "",
            "exit_code": 0,
            "timed_out": False,
            "duration_seconds": 5.0,
            "command_preview": "claude fix",
        }

        with patch(
            "ai_workflow_hub.agent_client.run_coding_agent",
            return_value=fake_result,
        ), patch(
            "ai_workflow_hub.git_utils.collect_all_diff_info",
            return_value={
                "diff_text": "+x",
                "changed_files": ["file.py"],
                "name_status": {"file.py": "M"},
                "diff_line_count": 1,
            },
        ), patch(
            "ai_workflow_hub.git_utils.save_diff_patch",
        ):
            result = fixer_node(state)

        # On success, 'status' should NOT be in the dict
        assert "status" not in result, (
            f"Expected no 'status' key on success, got status='{result.get('status')}'"
        )


# ---------------------------------------------------------------------------
# Fix 2: run_goal skips batches already in non-restartable states
# ---------------------------------------------------------------------------

class TestGoalBatchSkip:
    """Verify run_goal skips batches with passed/running/human_required status."""

    def test_skips_passed_batch(self):
        """Batch already 'passed' -> skipped, no _execute_run call."""
        from ai_workflow_hub.goal_runner import run_goal

        goal = {
            "goal_id": "g-test-skip",
            "status": "running",
            "batches": [
                {
                    "batch_id": "b1",
                    "objective": "already done",
                    "status": "passed",
                    "allowed_files": ["a.py"],
                    "risk_level": "low",
                    "included_tasks": [],
                    "acceptance_gates": {},
                },
            ],
            "replan_count": 0,
            "max_replans": 2,
        }

        executed = []

        def fake_exec_run(**kwargs):
            executed.append(kwargs)

        with patch(
            "ai_workflow_hub.goal_runner.load_goal", return_value=goal
        ), patch(
            "ai_workflow_hub.goal_runner.update_goal_status"
        ), patch(
            "ai_workflow_hub.goal_runner.update_batch_status"
        ), patch(
            "ai_workflow_hub.goal_runner.all_batches_passed", return_value=True
        ), patch(
            # _execute_run is imported inside run_goal from .cli
            "ai_workflow_hub.cli._execute_run", side_effect=fake_exec_run
        ), patch(
            # generate_goal_report is imported inside run_goal from .goal_report
            "ai_workflow_hub.goal_report.generate_goal_report"
        ):
            result = run_goal("g-test-skip", "test-proj", backend="claude")

        # Verify no _execute_run was invoked
        assert len(executed) == 0, (
            f"_execute_run should NOT be called for passed batch, "
            f"but was called {len(executed)} time(s)"
        )

        # Verify the result marks the batch as skipped
        assert len(result["results"]) == 1
        assert result["results"][0]["status"] == "passed"
        assert "skipped" in result["results"][0]["reason"]

    def test_skips_running_batch(self):
        """Batch already 'running' -> skipped."""
        from ai_workflow_hub.goal_runner import run_goal

        goal = {
            "goal_id": "g-test-running",
            "status": "running",
            "batches": [
                {
                    "batch_id": "b1",
                    "objective": "in progress",
                    "status": "running",
                    "allowed_files": ["a.py"],
                    "risk_level": "low",
                    "included_tasks": [],
                    "acceptance_gates": {},
                },
            ],
            "replan_count": 0,
            "max_replans": 2,
        }

        executed = []

        def fake_exec_run(**kwargs):
            executed.append(kwargs)

        with patch(
            "ai_workflow_hub.goal_runner.load_goal", return_value=goal
        ), patch(
            "ai_workflow_hub.goal_runner.update_goal_status"
        ), patch(
            "ai_workflow_hub.goal_runner.update_batch_status"
        ), patch(
            "ai_workflow_hub.goal_runner.all_batches_passed", return_value=False
        ), patch(
            "ai_workflow_hub.cli._execute_run", side_effect=fake_exec_run
        ), patch(
            "ai_workflow_hub.goal_report.generate_goal_report"
        ):
            result = run_goal("g-test-running", "test-proj", backend="claude")

        assert len(executed) == 0
        assert result["results"][0]["status"] == "running"

    def test_skips_human_required_batch(self):
        """Batch with 'human_required' -> skipped, no execution."""
        from ai_workflow_hub.goal_runner import run_goal

        goal = {
            "goal_id": "g-test-hr",
            "status": "running",
            "batches": [
                {
                    "batch_id": "b1",
                    "objective": "needs human",
                    "status": "human_required",
                    "allowed_files": ["a.py"],
                    "risk_level": "high",
                    "included_tasks": [],
                    "acceptance_gates": {},
                },
            ],
            "replan_count": 0,
            "max_replans": 2,
        }

        executed = []

        def fake_exec_run(**kwargs):
            executed.append(kwargs)

        with patch(
            "ai_workflow_hub.goal_runner.load_goal", return_value=goal
        ), patch(
            "ai_workflow_hub.goal_runner.update_goal_status"
        ), patch(
            "ai_workflow_hub.goal_runner.update_batch_status"
        ), patch(
            "ai_workflow_hub.goal_runner.all_batches_passed", return_value=False
        ), patch(
            "ai_workflow_hub.cli._execute_run", side_effect=fake_exec_run
        ), patch(
            "ai_workflow_hub.goal_report.generate_goal_report"
        ):
            result = run_goal("g-test-hr", "test-proj", backend="claude")

        assert len(executed) == 0
        assert result["results"][0]["status"] == "human_required"

    def test_executes_new_or_failed_batch(self):
        """Batch without a status (or 'failed') -> still executes normally."""
        from ai_workflow_hub.goal_runner import run_goal

        # Initial goal: batch has no status key (fresh)
        goal_fresh = {
            "goal_id": "g-test-exec",
            "status": "running",
            "batches": [
                {
                    "batch_id": "b1",
                    "objective": "fresh batch",
                    "allowed_files": ["a.py"],
                    "risk_level": "low",
                    "included_tasks": [],
                    "acceptance_gates": {},
                },
            ],
            "replan_count": 0,
            "max_replans": 2,
        }

        # After execution, the second load_goal() call returns an updated goal
        # with status on the batch
        goal_after = {
            "goal_id": "g-test-exec",
            "status": "running",
            "batches": [
                {
                    "batch_id": "b1",
                    "objective": "fresh batch",
                    "status": "passed",
                    "allowed_files": ["a.py"],
                    "risk_level": "low",
                    "included_tasks": [],
                    "acceptance_gates": {},
                },
            ],
            "replan_count": 0,
            "max_replans": 2,
        }

        executed = []

        def fake_exec_run(**kwargs):
            executed.append(kwargs)

        with patch(
            "ai_workflow_hub.goal_runner.load_goal",
            side_effect=[goal_fresh, goal_after, goal_after]
        ), patch(
            "ai_workflow_hub.goal_runner.update_goal_status"
        ), patch(
            "ai_workflow_hub.goal_runner.update_batch_status"
        ), patch(
            "ai_workflow_hub.goal_runner.all_batches_passed", return_value=False
        ), patch(
            "ai_workflow_hub.cli._execute_run", side_effect=fake_exec_run
        ), patch(
            "ai_workflow_hub.goal_runner._discover_run_id", return_value="run-1"
        ), patch(
            "ai_workflow_hub.goal_report.generate_goal_report"
        ), patch(
            # verify_run_evidence is imported inside run_goal from .cli
            "ai_workflow_hub.cli.verify_run_evidence",
            return_value={
                "evidence_ok": True,
                "chain_trusted": True,
                "final_report_consistent": True,
            },
        ):
            result = run_goal("g-test-exec", "test-proj", backend="claude")

        # Verify _execute_run WAS called for the fresh batch
        assert len(executed) == 1, (
            f"Expected 1 _execute_run call, got {len(executed)}"
        )
