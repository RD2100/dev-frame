# Zero-Config Quick Start

## One command

```bash
cd your-project
aihub do "describe what you want changed"
```

That's it. The system will:

1. Auto-detect your project (Python / Node / Android)
2. Auto-register it
3. Create a task
4. Run a dry-run plan
5. Show what would change

No config required. No manual setup.

## Apply changes

```bash
aihub do --apply "describe what you want changed"
```

You'll be asked to confirm. Changes happen in an isolated worktree, not your main code.

Skip confirmation:

```bash
aihub do --apply --yes "describe what you want changed"
```

## Safety

- Dry-run by default — no code is modified without `--apply`
- High risk tasks (auth, payment, deploy) are blocked with human gate
- All external actions (push, PR, merge, deploy) are blocked by default
- Changes happen in isolated git worktrees
