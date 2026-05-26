# Acceptance Report Template

## Headers

```markdown
# Acceptance Report: <suite-name>

**Time**: <ISO timestamp>
**Duration**: <elapsed seconds>s
**Project**: <project path>

## Summary
PASS=<n> BLOCKED=<n> FAILED=<n> TOTAL=<n>

## Results
| # | Flow | Status | Detail |
|---|------|--------|--------|
| 1 | config-exists | PASS | found |
| 2 | compile-check | FAILED | exit=1 |
```

## Sections

### Implementation

Static pre-flight checks:
- Project path exists
- Required config files present
- package.json / pyproject.toml / .env exists
- Directory structure valid

### Runtime

Checks that execute code:
- `python -m compileall`
- `npm run build` or equivalent
- Test runner invocation
- Backend health probe

### Explorer

UI/browser exploration. Deferred by default:
```
Explorer: not run, browser automation deferred
```

When active:
- Screenshot paths listed
- Browser console logs attached
- Page interaction results

## Verdict Rules

| Condition | Verdict |
|-----------|---------|
| Any FAILED | FAILED |
| Any BLOCKED, no FAILED | BLOCKED |
| All PASS | PASS |

## Evidence Requirements

Per Verification Gate standard:
- Command must be copy-pasteable
- Output summary with key lines, not full log
- Verdict must be PASS / BLOCKED / FAILED

Invalid:
- "Tests passed."
- "Looks correct."

Valid:
- `python -m compileall -q src` -> exit 0
- `git --version` -> git version 2.54.0.windows.1
