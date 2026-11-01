# Qortal Development Knowledge Base

## Purpose

This directory is the operational knowledge base for AI-assisted Qortal
development. It supports new applications, existing-application audits,
issue-driven implementation, runtime diagnosis, QDN design, host integration,
live validation and release provenance.

The shared
[`Qortal dApp Development Standard`](../docs/architecture/qortal-dapp-development-standard.md)
is the durable cross-project standard. The files in this directory route and
apply that standard by task class.

The canonical execution contract is
[`Qortal Development Workflow v2`](../docs/workflows/workflow-v2.md). Source
ownership and document lifecycle are defined in
[`source-of-truth-and-lifecycle.md`](../docs/governance/source-of-truth-and-lifecycle.md).

## Use when

Start every substantial repository task with
[`00-SESSION-START.md`](00-SESSION-START.md). Use this README when reviewing the
guide architecture or its migration provenance.

## Do not use when

This README is not a task router and does not define a platform API. Do not load
every guide by default. Do not use legacy Qortal material as current guidance.

## Prerequisites

- Exact repository and local path.
- Current branch and working-tree state.
- Access to current Qortal source when platform behavior matters.

## Required inputs

- Owner request or GitHub issue.
- Current checked-out Qortal Core / Hub / framework sources when platform
  behavior matters.
- The matching project file, if one exists.

## Guide catalog

| Guide | Owns |
| ----- | ---- |
| [`00-SESSION-START.md`](00-SESSION-START.md) | Mandatory entry, baseline, routing |
| [`01-TASK-CLASSIFICATION.md`](01-TASK-CLASSIFICATION.md) | Primary task class |
| [`qortal-native-app-workflow.md`](qortal-native-app-workflow.md) | New Q-App/product design |
| [`qortal-architecture-and-data-integrity.md`](qortal-architecture-and-data-integrity.md) | Authority, identity, schemas, migrations |
| [`qortal-qdn-and-bridge.md`](qortal-qdn-and-bridge.md) | `qortalRequest`, host, QDN access, routing, CSP, dev mode |
| [`qdn-publication-discovery-and-scaling.md`](qdn-publication-discovery-and-scaling.md) | Publication, discovery, catalogs, N+1, caching |
| [`runtime-diagnostics-and-performance.md`](runtime-diagnostics-and-performance.md) | Runtime errors, slowness, loading states |
| [`live-qdn-validation.md`](live-qdn-validation.md) | Live host/node/QDN verification |
| [`issue-driven-audit-and-refactor.md`](issue-driven-audit-and-refactor.md) | Audit to bounded implementation issues |
| [`app-release-and-provenance.md`](app-release-and-provenance.md) | Version, artifact, publication provenance |
| [`git-generated-files-and-hygiene.md`](git-generated-files-and-hygiene.md) | Git baseline, generated files |
| [`final-report-and-owner-handoff.md`](final-report-and-owner-handoff.md) | Report shape and handoff |
| [`roles/CHATGPT.md`](roles/CHATGPT.md), [`roles/DEEPSEEK.md`](roles/DEEPSEEK.md), [`roles/CODEX.md`](roles/CODEX.md) | Thin agent overlays |

## Migration provenance

Legacy Qortal agent guidance was found in
`iffinland/iffi-vaba-mees-QORTAL/agents/` (a snapshot of an older Qortal agent
workspace). It is migration evidence only. Classification and destination:

| Legacy file | Legacy purpose | Problems for current Qortal | Action and destination |
| ----------- | -------------- | --------------------------- | ---------------------- |
| `README.md` | Reusable Qortal qApp kit index | Routed new work through assumptions, duplicated a master workflow | **Superseded** by this catalog |
| `master-workflow.md` | Orchestrate new Qortal projects | Assumed `create-qortal-app` defaults, mandatory GitHub sync, and a single legacy runtime; no audit or focused-issue path | **Merged/rewritten** into `00-SESSION-START.md`, `01-TASK-CLASSIFICATION.md` and the routed guides |
| `qapp-framework-essentials.md` | Bootstrap a Q-App with `create-qortal-app` and `qapp-core` | Partly still current, but asserted framework details without revision and omitted the host/CSP/dev-proxy reality | **Rewritten** into `qortal-native-app-workflow.md` and `qortal-qdn-and-bridge.md` |
| `qortal-runtime-performance-rules.md` | QDN readiness and UX advice | General advice only; no measured baseline or N+1 model | **Split/rewritten** into `runtime-diagnostics-and-performance.md` and `qdn-publication-discovery-and-scaling.md` |
| `project-sync-backup-workflow.md` | GitHub init plus a backup convention | Mixed reusable Git safety with owner-specific paths and automatic commit/push behavior | **Split** into `git-generated-files-and-hygiene.md`; project commands stay in project files |
| `my-new-app-vision-example.md` | Product vision template | Product questions remain useful; identity and runtime assumptions obsolete | **Merged** into `qortal-native-app-workflow.md` and `templates/PROJECT-CONTEXT.md` |

Reusable rules were re-verified against current Qortal sources before being
carried forward. Everything unverifiable was dropped.

## Related files

- [`../docs/architecture/qortal-dapp-development-standard.md`](../docs/architecture/qortal-dapp-development-standard.md)
- [`../docs/workflows/workflow-v2.md`](../docs/workflows/workflow-v2.md)
- [`../docs/governance/source-of-truth-and-lifecycle.md`](../docs/governance/source-of-truth-and-lifecycle.md)
