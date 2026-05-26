# Safety Model

## Core principle

**Default deny, explicit allow.**

All external write operations and high-risk actions are blocked by default.
No automatic push, merge, or deploy.

## Policy Gates

| Action | Default | Config Key |
|--------|---------|------------|
| Issue import | allowed | allow_issue_import |
| Issue comment | blocked | allow_issue_comment |
| Issue close | blocked | allow_issue_close |
| PR create | blocked | allow_pr_create |
| Push | blocked | allow_push |
| Merge | permanently blocked | allow_merge |
| Deploy | permanently blocked | allow_deploy |
| CI fix | blocked | allow_ci_fix |
| Branch delete | blocked | allow_branch_delete |
| Force clean | blocked | allow_worktree_force_clean |

## Denied Labels

```yaml
denied_labels:
  - production
  - security
  - deploy
```

Issues with these labels are never imported.

## Audit

All policy checks write to `runs/audit/audit-YYYYMMDD.jsonl`.
JSONL lines include: timestamp, action, allowed, result, reason.
No keys, secrets, or tokens are recorded.

## Protected Tests

Tests in `protected_tests` patterns are never deleted.
Violation → status = blocked.

## Forbidden Paths

Changes touching `forbidden_paths` trigger human_gate.
Changes to `.env`, `secrets/`, `production/` are blocked.

## Human Gate

- High risk tasks → human_gate
- Reviewer verdict: human_gate → pause
- Fix rounds exhausted → blocked
- Human must explicitly approve before changes are applied
