# Agent WorkQueue Rules

## Tier Definitions

### Tier 0: Auto-Executable

Code agent executes without escalation. No backend, no destructive ops.

- Read-only checks (file existence, config parse)
- Local acceptance suites (smoke, dynamic, assertion-check, recovery-pipeline, rc-check, cleanup-safety)
- compileall, yaml parse
- Doc presence checks
- Report generation (dry-run only)

### Tier 1: Executable with Strict Acceptance

Code agent executes but reviewer should inspect results.

- Doc updates
- Index refresh
- Handoff updates
- Test fixture additions
- Low-risk script enhancements
- Report format adjustments

### Tier 2: Must Escalate

Code agent MUST NOT execute. Escalate to reviewer.

- Real backend calls
- Real Full E2E
- reviewer --apply
- cleanup --apply
- commit / push
- Delete historical artifacts
- Modify business code
- Modify production config
- Cross-module architecture changes
- Security/permission/data changes

## Escalation Signals

Stop the queue and escalate when:

| Signal | Action |
|--------|--------|
| batch exit 2 | Stop queue, escalate |
| forbidden command detected | Mark escalated |
| missing artifact | Mark failed |
| timeout (>300s) | Mark failed |
| 2+ consecutive same-type failures | Stop queue, escalate |
| report missing evidence | Escalate |
| task requirements unclear | Escalate |
| real backend needed | Escalate |
| user ACK needed | Escalate |

## Decision Table

| Queue Result | Action |
|-------------|--------|
| exit 0 (all passed) | Mark queue complete, proceed to next batch |
| exit 1 (blocked/escalated) | Generate summary, escalate to reviewer |
| exit 2 (failed) | Stop queue, escalate all failed items |

## Do NOT

- Execute Tier 2 items
- Commit or push
- Delete artifacts
- Call real backend without explicit ACK
- Modify source code without clear boundaries
- Skip verification steps
- Report PASS when checks actually failed
