---
type: gotcha
tags: ['subprocess', 'windows', 'opencode']
date: 2026-05-25
---

# PIPE Deadlock with capture_output=True

## Problem
subprocess.run(capture_output=True) creates stdout/stderr pipes. OpenCode large stderr (ANSI progress) fills pipe buffer → deadlock.

## Fix
Replace subprocess.run(capture_output=True) with subprocess.Popen() + temp files.

## Avoid
Never use capture_output=True for long-running subprocesses with significant stderr.

## Evidence
See project development history. This card created from v0.1-v1.1 audit.
