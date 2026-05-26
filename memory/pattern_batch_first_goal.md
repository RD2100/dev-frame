---
type: pattern
tags: ['goal', 'batch', 'risk-domain']
date: 2026-05-25
---

# Batch-First Goal Pattern

## Context
Goals broken into batches by risk_domain. Same-domain merged, cross-domain separate.

## Standard
Each batch: allowed_files (REQUIRED), acceptance_gates (REQUIRED), rollback_plan (REQUIRED). Destructive domain → human_required. Batch passed = evidence+chain+report+diff all ok.

## Avoid
Missing allowed_files or acceptance_gates silently accepted.

## Evidence
See project development history. This card created from v0.1-v1.1 audit.
