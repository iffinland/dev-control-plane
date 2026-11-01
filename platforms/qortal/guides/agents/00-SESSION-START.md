# Qortal Development Session Start

## Universal coordination (2026-09-13)

Read `/home/iffi/VsCodec-Projects/AI-Orchestration/AGENTS.md` first.
It owns shared roles (including Codex Local orchestration), agent branches,
GitHub handoff and reference freshness. This workspace retains platform-specific
execution and evidence rules. Older role summaries below are platform overlays;
they do not override that shared coordination contract.

## Purpose

Provide the mandatory entry point for every substantial Qortal task: establish
the baseline, classify the work, load only the relevant guides, and define
evidence and stopping conditions before any change.

## Use when

Use at the start of any new or resumed Qortal task in this environment.

## Do not use when

Do not use this as a substitute for the routed guide that owns the task class.
Do not restate platform rules here; they live in the standard and guides.

## Prerequisites

- Exact repository and local path.
- Current branch and working-tree state.
- The matching `projects/<project>.md`, when one exists.

## Required inputs

- Owner request or issue.
- The observable outcome and exit criterion.
- Any platform behavior the task depends on.

## Mandatory baseline

Before changing anything:

1. record the repository and local path;
2. record `git status` and the current revision;
3. identify pre-existing owner changes and treat them as user-owned;
4. identify the project context file;
5. identify which platform sources are current and relevant.

If the working tree contains owner changes, do not overwrite, revert or delete
them.

## Task classification

Classify with [`01-TASK-CLASSIFICATION.md`](01-TASK-CLASSIFICATION.md) and name
one primary class. Do not load every guide.

## Routing table

| Task involves | Primary guide |
| ------------- | ------------- |
| New Q-App / product design | [`qortal-native-app-workflow.md`](qortal-native-app-workflow.md) |
| Authority, identity, data integrity, schemas, migrations | [`qortal-architecture-and-data-integrity.md`](qortal-architecture-and-data-integrity.md) |
| `qortalRequest`, bridge, host, QDN access, routing, CSP, dev mode | [`qortal-qdn-and-bridge.md`](qortal-qdn-and-bridge.md) |
| Publication, discovery, catalogs, N+1, caching, scaling | [`qdn-publication-discovery-and-scaling.md`](qdn-publication-discovery-and-scaling.md) |
| Runtime errors, slowness, loading states, performance | [`runtime-diagnostics-and-performance.md`](runtime-diagnostics-and-performance.md) |
| Live host/node/QDN verification | [`live-qdn-validation.md`](live-qdn-validation.md) |
| Issue-driven audit and refactor | [`issue-driven-audit-and-refactor.md`](issue-driven-audit-and-refactor.md) |
| Release, version, artifact, provenance | [`app-release-and-provenance.md`](app-release-and-provenance.md) |
| Git baseline, generated files, hygiene | [`git-generated-files-and-hygiene.md`](git-generated-files-and-hygiene.md) |
| Final report and owner handoff | [`final-report-and-owner-handoff.md`](final-report-and-owner-handoff.md) |

## Authoritative source order

1. current Qortal Core source/rendered behavior;
2. current host (Hub / gateway) source for host behavior;
3. current framework (`qapp-core`, `qapp-templates`) source;
4. verified runtime behavior with recorded node/host/revision;
5. current project source and tests;
6. this workspace's guidance;
7. official Qortal docs (source wins on conflict);
8. historical reports.

Legacy `Qortal/qortal-ui` and legacy project-local `agents/` material are not
authority.

## Workflow

1. Establish the baseline and preserve owner changes.
2. Classify the task and name one primary class.
3. Read the matching project context.
4. Read only the routed guide(s).
5. Read the acting agent's role overlay.
6. Define objective, scope, out-of-scope work, acceptance criteria, required
   validation layers, and stop conditions.
7. Execute per [`../docs/workflows/workflow-v2.md`](../docs/workflows/workflow-v2.md).
8. Self-audit, remediate in-scope BLOCKER/HIGH findings, and hand off with the
   report path.

## Mandatory rules

- One primary objective and one exit criterion per task.
- Evidence before implementation; no presumed root cause.
- Validation layers are not interchangeable.
- Unknown platform behavior MUST be verified or declared blocking.
- No external writes without explicit authorization.
- Keep verified fact, inference, unknown and owner decision separate.
- Do not promote project-specific facts into global guides.

## Validation

- Scope and task class are explicit.
- Necessary sources and guides were read; irrelevant guides were not.
- Baseline and validation are recorded.
- The exit criterion is satisfied; remaining owner/host work controls status.
- The self-audit was completed for substantial work.
- Final status matches the evidence.

## Completion criteria

- One primary class is named and routed correctly.
- Required evidence layers were either completed or explicitly reported as
  missing.
- The report exists under the canonical root and its absolute path is
  disclosed.

## Related files

- [`01-TASK-CLASSIFICATION.md`](01-TASK-CLASSIFICATION.md)
- [`README.md`](README.md)
- [`../docs/architecture/qortal-dapp-development-standard.md`](../docs/architecture/qortal-dapp-development-standard.md)
- [`../docs/workflows/workflow-v2.md`](../docs/workflows/workflow-v2.md)
- [`final-report-and-owner-handoff.md`](final-report-and-owner-handoff.md)
