---
type: decision
tags: ['architecture', 'langgraph', 'state-machine']
date: 2026-05-25
---

# LangGraph Only Does Scheduling

## Decision
LangGraph Only Does Scheduling

## Why
Separation of concerns: scheduling vs execution. LangGraph is state machine, not LLM.

## Consequence
No LLM calls from LangGraph nodes. All backend calls through codex/agent clients.

## Revisit only if
New agent type needs integration or parallel execution.
