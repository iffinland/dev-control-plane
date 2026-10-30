# Qortal platform pack

Status: **Phase 1 boundary and source reference only.** Full Qortal platform
documentation is not imported here yet.

## Canonical platform source

```text
Repository: /home/iffi/dev-workspace/projects/qortal-dev-workspace
Baseline:   main @ b8fd2f6fbfcff88c0ab9bc8fd116d5548679d2d2
Remote:     https://github.com/iffinland/qortal-dev-workspace.git
```

The Phase 0 audit established that the Qortal platform material (`agents/`,
`docs/architecture/`, `docs/workflows/`, `templates/`, `tools/`) is unchanged on
all newer remote branches. Newer work is project evidence and project context.

## Preserved evidence branches

These branches remain on the source repository and must not be deleted or
rewritten. They are evidence sources for a later import phase.

| Branch | Tip | Role |
| --- | --- | --- |
| `origin/agent/shadow-archives-webportal/owner-runtime-docs-20260913` | `72b3c4d0e8c8018bde219b4940a2da6202c6b986` | Shadow Archives owner-runtime base |
| `origin/agent/shadow-archives-webportal/homepage-test-maintenance-docs-20260915` | `6f5cf53a55b454dba67b0f4fe78d7e44e75b1187` | Homepage maintenance and phase closure |
| `origin/agent/shadow-archives/blog-publish-runtime-handoff-20261001` | `44cf3a5277f2de431b4d09ceae624c9ea8d3791b` | Blog remediation, license audit, visual correction |
| `origin/agent/qwb-qortal-web-builders/phase-4-checkpoint-docs-20260916` | `694dff049707820ab3a8440692dabfc789f251ab` | QWB phase-4 checkpoint evidence |
| `origin/agent/qwb-qortal-web-builders/documentation-backfill-20261001` | `18d04c4102a276b67cec02aaf1450c8134d64f54` | QWB curated documentation/ZIP variant |

See `/home/iffi/dev-workspace/docs/workspace/audit/AGENT-WORKSPACE-PHASE0.md` for
the full comparison. No branch was merged, switched, or imported in Phase 1.

## Current routing

- Start with the control-plane [AGENTS.md](../../AGENTS.md) and
  [WORKFLOW.md](../../WORKFLOW.md).
- Use Qortal skills only for Qortal tasks.
- Verify current Qortal source/runtime before relying on a skill or historical
  report.
- Project contexts are not yet imported. The source registry is
  [PROJECT-REGISTRY.md](../../PROJECT-REGISTRY.md).

## Deferred to a later phase

- Import of the Qortal dApp standard and task guides.
- Import of Shadow Archives and QWB project contexts and evidence.
- Deduplication between Qortal guides and Qortal skills.
- Any commit, push, deployment, QDN write or release action.
