---
type: gotcha
tags: ['windows', 'encoding', 'subprocess']
date: 2026-05-25
---

# Windows .cmd Files Require shell=True

## Problem
On Windows, codex/opencode are .cmd files. subprocess.run(["opencode"]) with shell=False → FileNotFoundError.

## Fix
Use shell=True or full path to .cmd file.

## Avoid
Always test subprocess calls on Windows with actual .cmd files.

## Evidence
See project development history. This card created from v0.1-v1.1 audit.
