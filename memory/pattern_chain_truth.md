---
type: pattern
tags: ['chain-truth', 'verification', 'audit']
date: 2026-05-25
---

# Chain Truth Verification Pattern

## Context
Every run must prove actual thinking/execution chain, not claim from config.

## Standard
Check: chain-evidence.json, exit_code, stderr ERROR scan, run status, model mapping. Only passed runs with exit=0 on all thinking nodes = MATCH_TARGET.

## Avoid
Only checking backend name. Missing exit_code or stderr checks.

## Evidence
See project development history. This card created from v0.1-v1.1 audit.
