# Migrated Qortal platform guides

Status: **migrated platform reference, checked 2026-11-01.** These files retain
the Qortal-specific task guidance, QDN/bridge contracts, architecture rules and
release procedures that previously lived only in the legacy
`iffinland/qortal-dev-workspace` repository. They are active routing references
for Qortal work, but current Qortal Core, Hub and framework source plus observed
runtime remain authoritative for implemented behavior.

## Source provenance

```text
Repository: https://github.com/iffinland/qortal-dev-workspace
Local source (read-only): /home/iffi/dev-workspace/projects/qortal-dev-workspace
Branch: main
Commit: b8fd2f6fbfcff88c0ab9bc8fd116d5548679d2d2
Imported: 2026-11-01
```

The import is a read-only copy of `agents/`, `docs/architecture/`,
`docs/governance/`, `docs/workflows/` and `templates/` from that commit. The
legacy repository was not modified, moved, reset or deleted. Project-specific
report trees (`docs/shadow-archives-webportal/`, `projects/`) were **not**
imported; they remain historical project evidence in the legacy repository.

## What is here

| Path | Use |
| --- | --- |
| [`docs/architecture/qortal-dapp-development-standard.md`](docs/architecture/qortal-dapp-development-standard.md) | Durable cross-project Qortal dApp standard and reference revisions. |
| [`agents/00-SESSION-START.md`](agents/00-SESSION-START.md) | Qortal-specific session baseline and guide routing. |
| [`agents/01-TASK-CLASSIFICATION.md`](agents/01-TASK-CLASSIFICATION.md) | Task classes and non-interchangeable evidence. |
| [`agents/qortal-native-app-workflow.md`](agents/qortal-native-app-workflow.md) | New Q-App design and implementation sequence. |
| [`agents/qortal-qdn-and-bridge.md`](agents/qortal-qdn-and-bridge.md) | `qortalRequest`, host mediation, QDN reads/writes, CSP, dev proxy. |
| [`agents/qortal-architecture-and-data-integrity.md`](agents/qortal-architecture-and-data-integrity.md) | Authority, identity, deterministic reduction, rendering safety. |
| [`agents/qdn-publication-discovery-and-scaling.md`](agents/qdn-publication-discovery-and-scaling.md) | Services, identifiers, bounded search, N+1 avoidance, caches. |
| [`agents/runtime-diagnostics-and-performance.md`](agents/runtime-diagnostics-and-performance.md) | Measured diagnosis and environment separation. |
| [`agents/live-qdn-validation.md`](agents/live-qdn-validation.md) | Live host/node/QDN validation levels and exact-resource checks. |
| [`agents/issue-driven-audit-and-refactor.md`](agents/issue-driven-audit-and-refactor.md) | Audit-to-issue workflow. |
| [`agents/app-release-and-provenance.md`](agents/app-release-and-provenance.md) | Version, artifact, publication and provenance gates. |
| [`agents/git-generated-files-and-hygiene.md`](agents/git-generated-files-and-hygiene.md) | Owner-change preservation and diff hygiene. |
| [`agents/final-report-and-owner-handoff.md`](agents/final-report-and-owner-handoff.md) | Report vocabulary and handoff fields. |
| [`docs/governance/source-of-truth-and-lifecycle.md`](docs/governance/source-of-truth-and-lifecycle.md) | Authority tiers and documentation lifecycle. |
| [`docs/workflows/workflow-v2.md`](docs/workflows/workflow-v2.md) | Prior Qortal workflow; superseded in routing by the control-plane [`WORKFLOW.md`](../../../WORKFLOW.md) but retained for domain detail. |
| [`templates/`](templates/) | Qortal-specific audit, implementation, project-context and handoff shapes retained as reference. |

The canonical control-plane task templates remain in
[`templates/`](../../../templates/). The copies here preserve their original
relative links for provenance and must not become a second active template
authority.

## Reuse rules

1. Read the current control-plane [AGENTS.md](../../../AGENTS.md) and
   [WORKFLOW.md](../../../WORKFLOW.md) first.
2. Treat these documents as Qortal-specific guidance, not Qortal Core truth.
   Re-verify platform claims against current source and runtime using the
   [Qortal platform pack](../README.md) and
   [`ENVIRONMENT.md`](../../../ENVIRONMENT.md).
3. Do not apply Qortal bridge, identity, QDN or release semantics to Qortium.
4. Preserve the recorded revision dates; a dated guide is evidence, not a live
   guarantee.
5. Project-specific files, reports and owner decisions stay with their project
   or in the central report tree. Do not add them to this directory.

## Known gaps

- Shadow Archives and QWB project contexts and report trees were not imported;
  they remain in the legacy repository and central report history.
- The imported reference revisions date from 2026-09-11. Every dependent task
  must rerun the freshness gate.
- These guides are `verified-reference`-quality summaries, not a substitute for
  reading current Qortal source.
