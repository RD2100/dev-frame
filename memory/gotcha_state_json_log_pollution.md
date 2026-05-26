---
type: gotcha
tags: ['state', 'json', 'evidence']
date: 2026-05-25
---

# state.json Polluted with Full Log Content

## Problem
state.json used to store complete Codex stderr (ANSI codes). Unparseable, unreadable.

## Fix
State stores: path to log, hash of log. Log content stays in .log files.

## Avoid
Never put raw log output in state.json.

## Evidence
See project development history. This card created from v0.1-v1.1 audit.
