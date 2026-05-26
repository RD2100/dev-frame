---
type: pattern
tags: ['run-verify', 'evidence', 'chain']
date: 2026-05-25
---

# Run Verify Tri-State Pattern

## Context
verify_run_evidence() is shared by run verify CLI and goal_runner.

## Standard
Three independent checks: evidence_ok, chain_trusted, final_report_consistent. Used by both CLI and runner.

## Avoid
Mixing "evidence missing" with "chain not trusted". Duplicating verify logic in multiple places.

## Evidence
See project development history. This card created from v0.1-v1.1 audit.
