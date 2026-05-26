---
type: pattern
tags: ['backup', 'safety', 'destructive']
date: 2026-05-25
---

# Backup/Restore Pattern

## Context
All destructive actions must back up files first with stable backup_id.

## Standard
safe_backup() → backup_id + manifest + hash. safe_delete() backs up first. restore_backup(backup_id) verifies hash.

## Avoid
Destructive action without confirmed backup. Using timestamp instead of backup_id for restore.

## Evidence
See project development history. This card created from v0.1-v1.1 audit.
