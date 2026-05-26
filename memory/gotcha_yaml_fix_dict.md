---
type: gotcha
tags: ['yaml', 'reviewer', 'parsing']
date: 2026-05-25
---

# YAML Parses "fix_1: text" as Dict Not String

## Problem
LLM output "fix_1: description" → YAML parses as {fix_1: "description"} (dict), not string → Pydantic crash.

## Fix
_normalize_fix() converts dict items to k:v strings.

## Avoid
Always normalize YAML list items from LLM output.

## Evidence
See project development history. This card created from v0.1-v1.1 audit.
