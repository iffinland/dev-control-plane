# Final Report and Owner Handoff

## Purpose

Define the required structure and honesty rules for the final report and owner
handoff.

## Use when

Use at the end of every substantial task.

## Do not use when

Do not use the report to claim work that was not performed or evidence that was
not collected.

## Prerequisites

- The task objective and exit criterion.
- The validation actually performed.
- The final working-tree state.

## Required inputs

- Files changed.
- Validation results.
- Unavailable checks.
- External actions performed or not performed.
- The saved report path.

## Status vocabulary

Report exactly one:

- `COMPLETE` — objective met, all required layers verified.
- `PASS WITH OWNER VALIDATION REQUIRED` — automated work verified; a named owner
  or real-host check remains.
- `CHANGES REQUIRED` — in-scope implementation or validation failed.
- `ESCALATE TO CODEX` — high-risk, repeated-failure, or independent-audit case.
- `BLOCKED` — required evidence or authority unavailable.
- `NOT VERIFIED` — a named layer was not reached.

## Workflow

1. Confirm the objective and exit criterion.
2. Re-state the evidence for each required layer, with the environment.
3. List files changed.
4. List validation executed and its results.
5. List checks that were not run and why.
6. Perform and record the adversarial self-audit.
7. Record external-action state.
8. Save the report to the canonical path and disclose it.

## Report fields

- Task and objective.
- Status and why.
- Baseline and preserved changes.
- Files changed.
- What was verified, and by which layer/environment.
- What was not verified.
- Adversarial self-audit findings and remediation.
- Remaining risks and follow-up.
- Unresolved unknowns and owner decisions.
- Git status.
- Commit state (committed? no).
- Push state (pushed? no).
- Exact absolute report path.

## Mandatory rules

- The final response MUST state the exact absolute report path.
- MUST NOT claim a report exists unless the file exists on disk.
- MUST NOT claim a live/host validation that did not happen.
- MUST NOT hide an unavailable check.
- MUST NOT claim external actions that were not authorized or performed.
- MUST NOT present inference as verification.

## Validation

- The report file exists at the stated path.
- The status matches the evidence.
- Every "verified" claim names its layer and environment.
- Unresolved items are listed.

## Completion criteria

- Status is truthful.
- Report path is exact.
- Owner next actions are explicit.
- No unresolved in-scope BLOCKER/HIGH remains.

## Related files

- [`../docs/workflows/report-storage-policy.md`](../docs/workflows/report-storage-policy.md)
- [`../templates/OWNER-HANDOFF.md`](../templates/OWNER-HANDOFF.md)
- [`git-generated-files-and-hygiene.md`](git-generated-files-and-hygiene.md)
