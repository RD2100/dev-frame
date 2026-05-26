---
type: decision
tags: ['backend', 'claude', 'architecture']
date: 2026-05-25
---

# Claude is Primary Coding Backend

## Decision
Claude is Primary Coding Backend

## Why
Claude 6/6 stress passed (1.0), OpenCode 1/6 (0.17).

## Consequence
OpenCode = degraded_optional. No auto fallback.

## Revisit only if
OpenCode probe 3/3 exit=0 p95<60s.
