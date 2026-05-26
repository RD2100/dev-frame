---
type: gotcha
tags: ['chain-truth', 'acceptance', 'verification']
date: 2026-05-25
---

# chain-truth Passed on Failed Codex Calls

## Problem
acceptance chain-truth only checked backend_calls.backend name, not exit_code. codex_cli exit=1 was MATCH_TARGET.

## Fix
Chain-truth now checks exit_code==0 + stderr for ERROR + run status.

## Avoid
Never trust backend name without exit_code + stderr check.

## Evidence
See project development history. This card created from v0.1-v1.1 audit.
