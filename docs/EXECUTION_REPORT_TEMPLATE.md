# Execution Report Template

> For all ai-workflow-hub execution agents. Use this structure for every non-trivial task report.

```markdown
# [Task Name] Execution Report

## Executive Decision
pass / blocked / needs review

## Reviewer Index
- Changed files:
- Critical code paths:
- Tests run:
- Generated artifacts:
- Known gaps:
- Suggested review focus:

## Changes
### [Change 1]
- Files:
- What changed:
- Why:
- Verification:

### [Change 2]
...

## Evidence
- Commands:
- Output summaries:
- Report paths:

## Hard Stop Check
| Check | Result |
|-------|--------|
| Skill files modified? | yes / no |
| Memory files modified? | yes / no |
| New tools installed? | yes / no |
| Daemon started? | yes / no |
| Commit/push? | yes / no |
| Real backend called? | yes / no |

## Remaining Risks
1. [Risk 1 — what could go wrong, why it matters]
2. [Risk 2]
3. ...
```

## Field Requirements

| Field | Required | Description |
|-------|----------|-------------|
| Executive Decision | Always | `pass` (all gates met), `blocked` (cannot proceed), `needs review` (some gates need human) |
| Reviewer Index | Always | Quick scan for human reviewer: what files, what tests, what's risky |
| Changes | If code changed | Per-change breakdown with verification evidence |
| Evidence | Always | Exact commands + output summaries + artifact paths |
| Hard Stop Check | Always | 6-item checklist; any "yes" must be explained |
| Remaining Risks | Always | Max 5; each must state what could go wrong AND why it matters |

## Evidence Standard

Per `devprocess` Verification Gate:

- Command must be precise enough to copy-paste.
- Output summary must include key lines, not full log.
- Verdict must be `passed`, `failed`, or `blocked`.

Invalid:
- "Tests passed."
- "Looks correct."

Valid:
- `pytest tests/test_auth.py -v` → 12 passed, 0 failed.
- `python -m ai_workflow_hub.cli acceptance run goal` → 14/14 PASS, <5s.

## Assertion Safety Rule

Acceptance tests MUST use conditional assertions for boolean conditions.
`_pass("...", "False")` is a false positive — it records PASS when the condition failed.

Use `_assert_true(test, condition)` or explicit `if/else → _pass/_fail` instead.
Run `acceptance run assertion-check` to verify no "PASS ... False" in recent reports.
