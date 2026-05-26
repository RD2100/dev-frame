---
type: pattern
tags: ['backend_calls', 'schema', 'evidence']
date: 2026-05-25
---

# backend_calls Standard Schema

## Context
Every node must record backend call in standardized format with 16+ fields.

## Standard
Standard: backend, requested_model, effective_model, exit_code, timed_out, duration, fallback_from, fallback_reason, auth_mode, provider, trusted_for_status, tokens_used, stdout/stderr log paths and hashes.

## Avoid
Missing requested_model/effective_model split or missing fallback_from when http_fallback used.

## Evidence
See project development history. This card created from v0.1-v1.1 audit.
