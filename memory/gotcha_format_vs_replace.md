---
type: gotcha
tags: ['python', 'prompt', 'planner']
date: 2026-05-25
---

# .format() Crashes on LLM-Generated Braces

## Problem
PLANNER output contains { or } from markdown code blocks → .format() raises KeyError.

## Fix
Replace .format() with str.replace() for each placeholder.

## Avoid
Never use .format() or f-strings to inject LLM-generated text.

## Evidence
See project development history. This card created from v0.1-v1.1 audit.
