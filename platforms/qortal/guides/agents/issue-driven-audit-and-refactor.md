# Issue-Driven Audit and Refactor

## Purpose

Turn an audit of an existing Qortal application into bounded, evidence-based
implementation issues without uncontrolled rewrites.

## Use when

Use when an application needs assessment or a class of defects fixed, rather
than a single known bug.

## Do not use when

Do not use an audit to justify unrequested scope, architecture changes, or
external writes.

## Prerequisites

- Repository, local path and baseline revision.
- The matching project context.
- Current platform source for any platform claim.

## Required inputs

- Observed problems or owner goals.
- Known constraints and non-goals.
- Existing owner changes that must be preserved.

## Workflow

### 1. Establish the baseline

Record branch, revision, working-tree state, pre-existing owner changes, and the
current dependency/stack reality. Do not fix unrelated bugs silently.

### 2. Trace actual paths

Follow the real production flow for each reported problem. Identify the first
confirmed mismatch, not the most visible symptom. Separate platform-boundary
defects (Qortal contract, host, QDN) from application defects from UI defects.

### 3. Classify findings

For each finding record:

- category (architecture/authority, platform integration, performance/discovery,
  runtime, UI, dependency, hygiene, release);
- evidence and the first confirmed gate;
- severity (BLOCKER/HIGH/MEDIUM/LOW);
- whether it is in scope for the current task.

### 4. Create a parent audit issue

Summarize scope, evidence, severity, dependency map, and the proposed child
issues. Keep the parent as an index, not a mega-fix.

### 5. Create narrow implementation issues

Each child issue MUST have:

- one main problem;
- explicit scope and out-of-scope work;
- acceptance criteria;
- required validation levels;
- the files/areas it may touch.

Use [`../templates/IMPLEMENTATION-ISSUE.md`](../templates/IMPLEMENTATION-ISSUE.md)
and [`../templates/AUDIT-ISSUE.md`](../templates/AUDIT-ISSUE.md).

### 6. Order work

Order by: correctness/authority and data integrity first, then platform
integration, then performance/discovery, then UI, then hygiene. A performance
issue MUST NOT mask an authority bug.

### 7. Implement one issue

Follow [`../docs/workflows/workflow-v2.md`](../docs/workflows/workflow-v2.md).
Smallest coherent change. Preserve owner changes.

### 8. Close by evidence

Close nothing without the required evidence, and never close on agent
self-report alone. Issue closure requires explicit owner authorization.

## Mandatory rules

- Do not mix unrelated refactors into one change.
- Do not silently change documented architecture decisions.
- Do not "fix" a platform-boundary defect by adding an unverified workaround;
  trace and classify first.
- Do not widen a bounded fix because "it was nearby".
- Do not delete or rewrite owner work.

## Validation

- Baseline and preserved-change record.
- Reproduction before and after for bug-class issues.
- The routed guide's validation levels for the issue class.
- `git diff --check` and a full diff review.

## Completion criteria

- Findings are classified and severity-labelled.
- Issues are bounded and independently verifiable.
- Implemented issues have evidence for their acceptance criteria.
- Remaining findings are explicitly deferred, not hidden.

## Related files

- [`01-TASK-CLASSIFICATION.md`](01-TASK-CLASSIFICATION.md)
- [`live-qdn-validation.md`](live-qdn-validation.md)
- [`git-generated-files-and-hygiene.md`](git-generated-files-and-hygiene.md)
