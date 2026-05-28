"""Stage 2 Batch A tests: state transition guard + atomic evidence writes."""

import json
import tempfile
from pathlib import Path

import pytest

from ai_workflow_hub.task_queue import (
    add_task,
    mark_task_finished,
    mark_task_running,
)
from ai_workflow_hub.run_store import save_run_file, save_run_json


# ---------------------------------------------------------------------------
# Fix 1: mark_task_running() terminal-state guard
# ---------------------------------------------------------------------------

class TestMarkTaskRunningGuard:
    """Verify `mark_task_running()` blocks re-marking terminal-status tasks."""

    def test_terminal_state_blocks_running(self):
        """A finished (passed) task must not be re-marked running."""
        # Create a task, start it, finish it
        task_id = add_task("test-proj", "guard-test", "verify terminal guard")
        assert mark_task_running(task_id, "run-1") is True
        assert mark_task_finished(task_id, "passed", "run-1") is True

        # Now try to mark it running again -- must fail
        result = mark_task_running(task_id, "run-2")
        assert result is False, (
            "mark_task_running on a passed task must return False"
        )

        # Verify status is still "passed"
        from ai_workflow_hub.task_queue import find_task
        task = find_task(task_id)
        assert task is not None
        assert task["status"] == "passed", (
            f"Expected status 'passed', got '{task['status']}'"
        )

    def test_running_to_running_idempotent(self):
        """Calling mark_task_running on already-running task must return False."""
        task_id = add_task("test-proj", "idempotent-test", "already running")
        assert mark_task_running(task_id, "run-a") is True
        # Second call should be denied (already running)
        assert mark_task_running(task_id, "run-b") is False

        # Status should still be "running"
        from ai_workflow_hub.task_queue import find_task
        task = find_task(task_id)
        assert task is not None
        assert task["status"] == "running"


# ---------------------------------------------------------------------------
# Fix 2: Atomic evidence writes
# ---------------------------------------------------------------------------

class TestAtomicEvidenceWrites:
    """Verify `save_run_file` and `save_run_json` write valid, readable data."""

    def test_save_run_file_roundtrip(self):
        """save_run_file writes content that can be read back correctly."""
        with tempfile.TemporaryDirectory() as tmp:
            filepath = save_run_file(tmp, "test.txt", "hello evidence world")
            read_back = Path(filepath).read_text(encoding="utf-8")
            assert read_back == "hello evidence world"
            # Assert no .tmp residue
            assert not Path(filepath + ".tmp").exists()

    def test_save_run_json_roundtrip(self):
        """save_run_json writes valid JSON that can be read back correctly."""
        data = {"key": "value", "nested": {"a": 1}, "list": [1, 2, 3]}
        with tempfile.TemporaryDirectory() as tmp:
            filepath = save_run_json(tmp, "test.json", data)
            with open(filepath, encoding="utf-8") as f:
                read_back = json.load(f)
            assert read_back == data
            # Assert no .tmp residue
            assert not Path(filepath + ".tmp").exists()

    def test_save_run_json_special_types(self):
        """save_run_json handles non-serializable types via default=str."""
        from datetime import datetime, timezone
        data = {"ts": datetime(2026, 5, 26, tzinfo=timezone.utc)}
        with tempfile.TemporaryDirectory() as tmp:
            filepath = save_run_json(tmp, "ts.json", data)
            with open(filepath, encoding="utf-8") as f:
                read_back = json.load(f)
            # datetime is serialized as ISO string
            assert "2026-05-26" in read_back["ts"]

    def test_save_run_file_overwrite(self):
        """save_run_file correctly overwrites an existing file."""
        with tempfile.TemporaryDirectory() as tmp:
            save_run_file(tmp, "over.txt", "v1")
            save_run_file(tmp, "over.txt", "v2")
            read_back = Path(tmp, "over.txt").read_text(encoding="utf-8")
            assert read_back == "v2"
            # Should also have cleaned up .tmp
            assert not Path(tmp, "over.txt.tmp").exists()

    def test_save_run_json_overwrite(self):
        """save_run_json correctly overwrites an existing file."""
        with tempfile.TemporaryDirectory() as tmp:
            save_run_json(tmp, "over.json", {"v": 1})
            save_run_json(tmp, "over.json", {"v": 2})
            with open(Path(tmp, "over.json"), encoding="utf-8") as f:
                read_back = json.load(f)
            assert read_back == {"v": 2}
            assert not Path(tmp, "over.json.tmp").exists()
