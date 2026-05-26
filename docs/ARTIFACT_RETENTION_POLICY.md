# Artifact Retention Policy

> Default: keep everything. Dry-run first. --apply requires --yes.

## Artifact Types

| Type | Default Action | Reason |
|------|---------------|--------|
| `acceptance_fixture` | `delete_candidate` | Test goals/runs from acceptance suites; safe to clean |
| `old_acceptance_report` | `delete_candidate` | Keep latest 20; older are safe to clean |
| `real_e2e` | `keep` | Real backend was called; evidence for release |
| `recovery_evidence` | `keep` | `evidence_recovered=true` runs; post-kill recovery proof |
| `release_candidate` | `keep` | Runs referenced by release docs |
| `manual_ack` | `keep` | User explicitly ACKed real backend |
| `unknown` | `keep` | Cannot determine provenance; must not delete |

## Safety Rules

1. **Unknown → keep.** Never guess.
2. **Dry-run default.** No delete without `--apply --yes`.
3. **Real backend runs preserved.**
4. **Recovery evidence preserved.**
5. **Release candidate evidence preserved.**
6. **Acceptance fixtures are candidates.**
7. **Path traversal blocked.** Cleanup stays within project directory.

## CLI

```powershell
# Dry-run (safe, default)
python -m ai_workflow_hub.cli artifacts cleanup --dry-run

# Real delete (requires double confirmation)
python -m ai_workflow_hub.cli artifacts cleanup --apply --yes
```
