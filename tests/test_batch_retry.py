"""Stage 5: Goal runner per-batch retry with configurable max attempts.

When a batch fails (error, evidence gap, scope violation), the runner
retries the same batch up to max_batch_retries times before giving up.
"""

import pytest
from unittest.mock import patch


# ---------------------------------------------------------------------------
# Per-batch retry tests
# ---------------------------------------------------------------------------

class TestGoalBatchRetry:
    def test_retries_failed_batch_once_by_default(self):
        """Failed batch is retried one more time before recording failure."""
        from ai_workflow_hub.goal_runner import run_goal

        # Batch with max_batch_retries in goal config
        goal_initial = {
            "goal_id": "g-test-retry",
            "status": "running",
            "max_batch_retries": 1,
            "batches": [
                {
                    "batch_id": "b1",
                    "objective": "flaky batch",
                    "allowed_files": ["a.py"],
                    "risk_level": "low",
                    "status": "planned",
                    "included_tasks": [],
                    "acceptance_gates": {},
                },
            ],
            "replan_count": 0,
            "max_replans": 2,
        }

        # After 2nd attempt: batch passes
        goal_after = {
            "goal_id": "g-test-retry",
            "status": "running",
            "max_batch_retries": 1,
            "batches": [
                {
                    "batch_id": "b1",
                    "objective": "flaky batch",
                    "allowed_files": ["a.py"],
                    "risk_level": "low",
                    "status": "passed",
                    "batch_retry_count": 1,
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
            side_effect=[
                goal_initial,  # first load
                goal_initial,  # after first attempt fails -> still initial
                goal_after,    # after second attempt passes
                goal_after,    # final status check
            ]
        ), patch(
            "ai_workflow_hub.goal_runner.update_goal_status"
        ), patch(
            "ai_workflow_hub.goal_runner.update_batch_status"
        ), patch(
            "ai_workflow_hub.goal_runner.all_batches_passed", return_value=True
        ), patch(
            "ai_workflow_hub.cli._execute_run", side_effect=fake_exec_run
        ), patch(
            "ai_workflow_hub.goal_runner._discover_run_id",
            side_effect=["", "run-retry-1"]
        ), patch(
            "ai_workflow_hub.goal_report.generate_goal_report"
        ), patch(
            "ai_workflow_hub.cli.verify_run_evidence",
            return_value={
                "evidence_ok": True,
                "chain_trusted": True,
                "final_report_consistent": True,
            },
        ):
            result = run_goal("g-test-retry", "test-proj", backend="claude")

        # _execute_run should have been called twice (initial + retry)
        assert len(executed) == 2, (
            f"Expected 2 execution attempts (initial + retry), got {len(executed)}"
        )

    def test_exhausts_retries_then_records_failure(self):
        """When max retries are exhausted, batch is recorded as failed."""
        from ai_workflow_hub.goal_runner import run_goal

        goal = {
            "goal_id": "g-test-exhaust",
            "status": "running",
            "max_batch_retries": 2,
            "batches": [
                {
                    "batch_id": "b1",
                    "objective": "always fails",
                    "allowed_files": ["a.py"],
                    "risk_level": "low",
                    "status": "planned",
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
            side_effect=[goal, goal, goal, goal, goal]
        ), patch(
            "ai_workflow_hub.goal_runner.update_goal_status"
        ), patch(
            "ai_workflow_hub.goal_runner.update_batch_status"
        ), patch(
            "ai_workflow_hub.goal_runner.all_batches_passed", return_value=False
        ), patch(
            "ai_workflow_hub.cli._execute_run", side_effect=fake_exec_run
        ), patch(
            "ai_workflow_hub.goal_runner._discover_run_id", return_value=""
        ), patch(
            "ai_workflow_hub.goal_report.generate_goal_report"
        ):
            result = run_goal("g-test-exhaust", "test-proj", backend="claude")

        # 1 initial + 2 retries = 3 total
        assert len(executed) == 3, (
            f"Expected 3 execution attempts (1 initial + 2 retries), got {len(executed)}"
        )
        assert result["results"][0]["status"] == "failed"

    def test_zero_retries_means_no_retry(self):
        """When max_batch_retries is 0, batch fails immediately."""
        from ai_workflow_hub.goal_runner import run_goal

        goal = {
            "goal_id": "g-test-noretry",
            "status": "running",
            "max_batch_retries": 0,
            "batches": [
                {
                    "batch_id": "b1",
                    "objective": "fails once",
                    "allowed_files": ["a.py"],
                    "risk_level": "low",
                    "status": "planned",
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
            side_effect=[goal, goal, goal]
        ), patch(
            "ai_workflow_hub.goal_runner.update_goal_status"
        ), patch(
            "ai_workflow_hub.goal_runner.update_batch_status"
        ), patch(
            "ai_workflow_hub.goal_runner.all_batches_passed", return_value=False
        ), patch(
            "ai_workflow_hub.cli._execute_run", side_effect=fake_exec_run
        ), patch(
            "ai_workflow_hub.goal_runner._discover_run_id", return_value=""
        ), patch(
            "ai_workflow_hub.goal_report.generate_goal_report"
        ):
            result = run_goal("g-test-noretry", "test-proj", backend="claude")

        assert len(executed) == 1
        assert result["results"][0]["status"] == "failed"

    def test_retries_on_evidence_failure(self):
        """Batch retries when evidence check fails (not just exec_error)."""
        from ai_workflow_hub.goal_runner import run_goal

        goal_initial = {
            "goal_id": "g-test-ev",
            "status": "running",
            "max_batch_retries": 1,
            "batches": [
                {
                    "batch_id": "b1",
                    "objective": "evidence gap",
                    "allowed_files": ["a.py"],
                    "risk_level": "low",
                    "status": "planned",
                    "included_tasks": [],
                    "acceptance_gates": {},
                },
            ],
            "replan_count": 0,
            "max_replans": 2,
        }

        goal_after = {
            "goal_id": "g-test-ev",
            "status": "running",
            "max_batch_retries": 1,
            "batches": [
                {
                    "batch_id": "b1",
                    "objective": "evidence gap",
                    "allowed_files": ["a.py"],
                    "risk_level": "low",
                    "status": "passed",
                    "batch_retry_count": 1,
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
            side_effect=[goal_initial, goal_initial, goal_after, goal_after]
        ), patch(
            "ai_workflow_hub.goal_runner.update_goal_status"
        ), patch(
            "ai_workflow_hub.goal_runner.update_batch_status"
        ), patch(
            "ai_workflow_hub.goal_runner.all_batches_passed", return_value=True
        ), patch(
            "ai_workflow_hub.cli._execute_run", side_effect=fake_exec_run
        ), patch(
            "ai_workflow_hub.goal_runner._discover_run_id",
            side_effect=["run-1", "run-2"]
        ), patch(
            "ai_workflow_hub.goal_report.generate_goal_report"
        ), patch(
            "ai_workflow_hub.cli.verify_run_evidence",
            side_effect=[
                {"evidence_ok": False, "chain_trusted": False, "final_report_consistent": False},
                {"evidence_ok": True, "chain_trusted": True, "final_report_consistent": True},
            ]
        ):
            result = run_goal("g-test-ev", "test-proj", backend="claude")

        assert len(executed) == 2
