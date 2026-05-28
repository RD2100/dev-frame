"""Tests for workflow node pure functions: planner, reviewer, fixer, finalizer.

Covers: prompt builders, YAML extraction, verdict validation,
blocking node inference, failure analysis, and fixer dry-run behavior.
"""

import pytest
from ai_workflow_hub.nodes.planner import build_planner_prompt, _extract_section
from ai_workflow_hub.nodes.reviewer import (
    build_reviewer_prompt,
    _extract_review_yaml,
    _normalize_fix,
    _validate_review_verdict,
)
from ai_workflow_hub.nodes.fixer import build_fixer_prompt
from ai_workflow_hub.nodes.finalizer import (
    build_finalizer_prompt,
    _infer_blocking_node,
    _blocking_reason,
    _recommend_next_action,
    build_failure_analysis,
)


# ---------------------------------------------------------------------------
# Planner node
# ---------------------------------------------------------------------------

class TestPlannerNodePure:
    def test_build_planner_prompt_includes_task_title(self):
        state = {
            "task_title": "Fix auth bug",
            "task_description": "Users cannot login with MFA",
            "task_risk": "high",
            "current_branch": "feature/auth-fix",
            "dry_run": True,
            "project_config": {"type": "backend"},
        }
        prompt = build_planner_prompt(state)
        assert "Fix auth bug" in prompt
        assert "Users cannot login" in prompt
        assert "high" in prompt
        assert "feature/auth-fix" in prompt
        assert "dry_run: True" in prompt

    def test_build_planner_prompt_defaults(self):
        state = {"task_title": "default test"}
        prompt = build_planner_prompt(state)
        assert "default test" in prompt
        assert "medium" in prompt

    def test_extract_section_simple(self):
        text = """## Plan
Some text

## Allowed Files
- `src/auth.py`
- `tests/test_auth.py`

## Forbidden Files
- `src/config.py`
"""
        result = _extract_section(text, "Allowed Files")
        assert result == ["src/auth.py", "tests/test_auth.py"]

    def test_extract_section_empty(self):
        text = "## Allowed Files\n\n## Next"
        result = _extract_section(text, "Allowed Files")
        assert result == []

    def test_extract_section_stops_at_heading(self):
        text = "## Allowed Files\n- `a.py`\n## Forbidden"
        result = _extract_section(text, "Allowed Files")
        assert result == ["a.py"]

    def test_extract_section_items_without_backticks(self):
        text = "## Allowed Files\n- src/main.py\n- config.toml\n## End"
        result = _extract_section(text, "Allowed Files")
        assert result == ["src/main.py", "config.toml"]


# ---------------------------------------------------------------------------
# Reviewer node
# ---------------------------------------------------------------------------

class TestReviewerNodePure:
    def test_build_reviewer_prompt_basic(self):
        state = {
            "task_title": "Add rate limiting",
            "task_risk": "medium",
            "fix_round": 0,
            "max_fix_rounds": 3,
            "plan": "# Plan\n\n- Add middleware\n- Write tests",
            "test_output": "30 passed in 2.1s",
            "git_diff": "diff --git a/src/limit.py b/src/limit.py",
            "changed_files": ["src/limit.py", "tests/test_limit.py"],
            "changed_files_status": {"src/limit.py": "M", "tests/test_limit.py": "A"},
            "diff_line_count": 42,
            "allowed_files": ["src/limit.py", "tests/"],
            "forbidden_files": ["src/config.py"],
            "protected_tests": ["tests/regression/"],
            "constraints": {"max_changed_files": 20, "max_diff_lines": 800},
        }
        prompt = build_reviewer_prompt(state)
        assert "Add rate limiting" in prompt
        assert "M  src/limit.py" in prompt
        assert "A  tests/test_limit.py" in prompt
        assert "NEVER touch" in prompt
        assert "src/config.py" in prompt
        assert "human_gate" in prompt

    def test_build_reviewer_prompt_no_changes(self):
        state = {"task_title": "empty", "changed_files_status": {}}
        prompt = build_reviewer_prompt(state)
        assert "(no changes)" in prompt

    def test_extract_review_yaml_pass(self):
        text = """```yaml
verdict: pass
test_exit_code: 0
files_changed: 3
risk_summary: All checks passed
```"""
        result = _extract_review_yaml(text)
        assert result["verdict"] == "pass"
        assert result["test_exit_code"] == 0
        assert result["files_changed"] == 3
        assert result["risk_summary"] == "All checks passed"

    def test_extract_review_yaml_defaults(self):
        result = _extract_review_yaml("no yaml here")
        assert result["verdict"] == "fail"

    def test_extract_review_yaml_forbidden_touched(self):
        text = """```yaml
verdict: human_gate
forbidden_touched: true
```"""
        result = _extract_review_yaml(text)
        assert result["verdict"] == "human_gate"
        assert result["forbidden_touched"] is True

    def test_normalize_fix_string(self):
        assert _normalize_fix("add error handling") == "add error handling"

    def test_normalize_fix_dict(self):
        assert _normalize_fix({"file": "a.py", "reason": "crash"}) == "file: a.py; reason: crash"

    def test_normalize_fix_none(self):
        assert _normalize_fix(None) == ""

    def test_validate_verdict_tests_deleted(self):
        review = {"tests_deleted": True}
        assert _validate_review_verdict(review, {"fix_round": 0, "max_fix_rounds": 3}) == "blocked"

    def test_validate_verdict_assertions_lowered(self):
        review = {"assertions_lowered": True}
        assert _validate_review_verdict(review, {"fix_round": 0, "max_fix_rounds": 3}) == "blocked"

    def test_validate_verdict_forbidden_touched(self):
        review = {"forbidden_touched": True}
        assert _validate_review_verdict(review, {"fix_round": 0, "max_fix_rounds": 3}) == "human_gate"

    def test_validate_verdict_fail_exhausted(self):
        review = {"verdict": "fail"}
        state = {"fix_round": 3, "max_fix_rounds": 3}
        assert _validate_review_verdict(review, state) == "blocked"

    def test_validate_verdict_fail_not_exhausted(self):
        review = {"verdict": "fail"}
        state = {"fix_round": 1, "max_fix_rounds": 3}
        assert _validate_review_verdict(review, state) == "fail"

    def test_validate_verdict_pass(self):
        review = {"verdict": "pass"}
        assert _validate_review_verdict(review, {"fix_round": 0, "max_fix_rounds": 3}) == "pass"


# ---------------------------------------------------------------------------
# Fixer node
# ---------------------------------------------------------------------------

class TestFixerNodePure:
    def test_build_fixer_prompt_includes_context(self):
        state = {
            "task_title": "Fix flaky test",
            "fix_round": 1,
            "max_fix_rounds": 3,
            "test_output": "FAILED test_timeout",
            "review_result": "fail",
            "next_fixes": ["add retry", "increase timeout"],
            "allowed_fix_files": ["tests/test_api.py"],
            "git_diff": "diff --git a/tests/test_api.py",
            "ci_report": "",
        }
        prompt = build_fixer_prompt(state)
        assert "Fix flaky test" in prompt
        assert "2 / 3" in prompt
        assert "FAILED test_timeout" in prompt
        assert "add retry" in prompt
        assert "tests/test_api.py" in prompt

    def test_build_fixer_prompt_with_ci(self):
        state = {
            "task_title": "CI fix",
            "fix_round": 0,
            "max_fix_rounds": 2,
            "test_output": "",
            "review_result": "",
            "next_fixes": [],
            "allowed_fix_files": [],
            "git_diff": "",
            "ci_report": "Error: lint check failed on src/main.ts",
        }
        prompt = build_fixer_prompt(state)
        assert "CI Failure Report" in prompt
        assert "lint check failed" in prompt


# ---------------------------------------------------------------------------
# Finalizer node
# ---------------------------------------------------------------------------

class TestFinalizerNodePure:
    def test_build_finalizer_prompt_basic(self):
        state = {
            "run_id": "run-001",
            "project_name": "test-project",
            "project_id": "proj-1",
            "task_title": "Refactor DB layer",
            "task_id": "task-abc",
            "task_risk": "medium",
            "dry_run": False,
            "current_branch": "feature/db",
            "status": "passed",
            "plan": "# Plan",
            "execution_log": "Ran migrations",
            "test_output": "All tests passed",
            "review_result": "pass",
            "review_summary": "LGTM",
            "changed_files": ["src/db.py"],
            "diff_line_count": 25,
            "dangerous_change": False,
            "human_required": False,
        }
        prompt = build_finalizer_prompt(state)
        assert "run-001" in prompt
        assert "test-project" in prompt
        assert "Refactor DB layer" in prompt
        assert "apply" in prompt
        assert "feature/db" in prompt

    def test_infer_blocking_node_executor_timeout(self):
        state = {
            "error_message": "Connection timeout",
            "backend_calls": {
                "executor": {"timed_out": True, "exit_code": -1},
            },
        }
        assert _infer_blocking_node(state) == "executor"

    def test_infer_blocking_node_human_gate(self):
        state = {"human_required": True, "error_message": ""}
        assert _infer_blocking_node(state) == "human_gate"

    def test_infer_blocking_node_reviewer_blocked(self):
        state = {"review_result": "blocked", "error_message": ""}
        assert _infer_blocking_node(state) == "reviewer"

    def test_infer_blocking_node_fixer_exhausted(self):
        state = {
            "fix_round": 3,
            "max_fix_rounds": 3,
            "error_message": "",
        }
        assert _infer_blocking_node(state) == "fixer"

    def test_infer_blocking_node_tester_failed(self):
        state = {
            "test_exit_code": 1,
            "error_message": "",
            "fix_round": 0,
            "max_fix_rounds": 3,
        }
        assert _infer_blocking_node(state) == "tester"

    def test_blocking_reason_each_node(self):
        assert "failed or timed out" in _blocking_reason({}, "executor")
        assert "exhausted" in _blocking_reason({}, "fixer")
        assert "blocked the run" in _blocking_reason({}, "reviewer")
        assert "review required" in _blocking_reason({}, "human_gate")
        assert "tests failed" in _blocking_reason({}, "tester")

    def test_recommend_next_action_each_node(self):
        assert "OpenCode" in _recommend_next_action({}, "executor")
        assert "human intervention" in _recommend_next_action({}, "fixer")
        assert "review.md" in _recommend_next_action({}, "reviewer")
        assert "human-gate.md" in _recommend_next_action({}, "human_gate")
        assert "test-output.md" in _recommend_next_action({}, "tester")

    def test_build_failure_analysis_failed(self):
        state = {
            "status": "failed",
            "run_id": "run-001",
            "task_title": "Test task",
            "task_id": "task-abc",
            "project_name": "proj",
            "review_result": "pass",
            "human_required": False,
            "error_message": "executor failed",
            "changed_files": [],
            "diff_line_count": 0,
            "test_exit_code": -1,
            "review_summary": "",
            "next_fixes": [],
            "dangerous_change": False,
            "fix_round": 0,
            "max_fix_rounds": 3,
            "run_dir": "/tmp",
            "backend_calls": {},
        }
        report = build_failure_analysis(state)
        assert "# Failure Analysis" in report
        assert "run-001" in report
        assert "Test task" in report
        assert "executor failed" in report

    def test_build_failure_analysis_includes_blocking_node(self):
        state = {
            "status": "blocked",
            "run_id": "run-002",
            "task_title": "T",
            "task_id": "t-1",
            "project_name": "p",
            "review_result": "blocked",
            "human_required": False,
            "error_message": "",
            "changed_files": [],
            "diff_line_count": 0,
            "test_exit_code": -1,
            "review_summary": "forbidden paths",
            "next_fixes": [],
            "dangerous_change": False,
            "fix_round": 0,
            "max_fix_rounds": 3,
            "run_dir": "/tmp",
            "backend_calls": {},
        }
        report = build_failure_analysis(state)
        assert "reviewer" in report
        assert "blocked the run" in report
