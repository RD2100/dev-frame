---
type: gotcha
tags: ['codex', 'chatgpt', 'model']
date: 2026-05-25
---

# ChatGPT Auth Does Not Accept gpt-5.5-codex

## Problem
Codex ChatGPT auth rejects "gpt-5.5-codex" → model not supported. HTTP fallback also rejects it.

## Fix
Map gpt-5.5-codex → gpt-5.5 when auth_mode=chatgpt. Store requested_model + effective_model.

## Avoid
Always record both model names in backend_calls.

## Evidence
See project development history. This card created from v0.1-v1.1 audit.
