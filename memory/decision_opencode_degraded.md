---
type: decision
tags: ['opencode', 'backend', 'degraded']
date: 2026-05-25
---

# OpenCode is Degraded Optional Backend

## Decision
OpenCode is Degraded Optional Backend

## Why
1/6 stress passed. Provider integration issues (not model).

## Consequence
Not default fallback. Explicit --backend only. degraded_optional in health.

## Revisit only if
OpenCode probe 3/3 exit=0 p95<60s.
