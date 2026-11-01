# Qortal platform pack

Status: **boundary and source reference, plus condensed candidate notes
(2026-10-31) and migrated Qortal task guides (2026-11-01).** Current Qortal
source and runtime remain authoritative; the migrated guides are routing and
reference material, not platform truth.

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

## Condensed reference notes

These notes were added for legacy dApp audit and repair. They are
**candidate, third-party-derived references**, not platform authority and not a
full documentation import.

| Document | Use |
| --- | --- |
| [`references/q-app-host-compatibility.md`](references/q-app-host-compatibility.md) | Host/bridge/QDN checks for legacy audits, with unverified and conflicting claims called out. |
| [`references/legacy-app-audit-checklist.md`](references/legacy-app-audit-checklist.md) | Inventory, compatibility matrix, defect reproduction, regression and release-readiness checklist. |
| [`references/source-adoption-analysis.md`](references/source-adoption-analysis.md) | What was adopted, rejected or left unverified from the supplied sources, and Qortal vs Qortium applicability. |

Load the
[`qortal-legacy-dapp-audit-repair`](../../skills/qortal/legacy-dapp-audit-repair/SKILL.md)
skill for the reusable audit procedure. Load the detailed notes only when the
task needs host-level detail. Check the version pins against current source and
runtime first.

## Migrated Qortal task guides (2026-11-01)

The Qortal-specific standard, session routing, QDN/bridge contract, authority
rules, discovery/scaling, runtime diagnostics, live validation and release
provenance guides were migrated read-only from
`iffinland/qortal-dev-workspace` at
`b8fd2f6fbfcff88c0ab9bc8fd116d5548679d2d2`. Start at
[`guides/README.md`](guides/README.md), which records provenance, contents and
remaining gaps.

These guides retain the Qortal platform boundary and task-level detail. They do
not replace current Core/Hub/framework source or a real-host validation layer.
Qortal project-specific report trees were not imported.

## Current routing

- Start with the control-plane [AGENTS.md](../../AGENTS.md) and
  [WORKFLOW.md](../../WORKFLOW.md).
- Use Qortal skills only for Qortal tasks.
- For an older app affected by platform evolution, start with
  [`qortal-legacy-dapp-audit-repair`](../../skills/qortal/legacy-dapp-audit-repair/SKILL.md),
  then load only the capability-specific skills the inventory requires.
- Verify current Qortal source/runtime before relying on a skill, reference note
  or historical report.
- Project contexts are not yet imported. The source registry is
  [PROJECT-REGISTRY.md](../../PROJECT-REGISTRY.md).

## Deferred to a later phase

- Import of Shadow Archives and QWB project contexts and evidence; they remain
  historical evidence in the legacy repository and central report history.
- Promotion of condensed reference notes and migrated guides to
  `verified-runtime` platform documentation after current source/runtime
  confirmation.
- Any deployment, QDN write or release action.
