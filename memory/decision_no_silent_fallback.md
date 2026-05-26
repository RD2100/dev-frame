---
type: decision
tags: ['fallback', 'transparency', 'chain']
date: 2026-05-25
---

# No Silent Fallback

## Decision
No Silent Fallback

## Why
Chain claimed "Codex thinking" while using DeepSeek HTTP fallback. Discovered in chain-truth audit.

## Consequence
backend_calls always has fallback_from + fallback_reason. chain-truth FAILS if thinking uses http_fallback.

## Revisit only if
Multi-tier fallback with different trust levels intentionally designed.
