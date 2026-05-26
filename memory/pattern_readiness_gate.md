---
type: pattern
tags: ['codex', 'readiness', 'apply-gate']
date: 2026-05-25
---

# Codex Readiness Gate Pattern

## Context
apply must check Codex is actually working before allowing real code changes.

## Standard
Gate: 3/3 probe exit=0, p95<60s, auth+proxy, stderr clean. Cache 10min in runs/codex-readiness/latest.json. Block apply if not ready.

## Avoid
Only checking auth+proxy, not actual probe results.

## Evidence
See project development history. This card created from v0.1-v1.1 audit.
