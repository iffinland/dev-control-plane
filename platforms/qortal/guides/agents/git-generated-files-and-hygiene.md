# Git and Generated-File Hygiene

## Purpose

Protect the working tree, keep source and generated output separate, and keep
the final diff reviewable.

## Use when

Use for every task that edits a repository, and especially before handoff.

## Do not use when

Do not use this guide to justify discarding owner work or rewriting history.

## Prerequisites

- Repository and local path.
- Current branch and revision.

## Required inputs

- `git status`, `git diff`, `git status --porcelain`.
- The project's ignore rules and build output paths.

## Workflow

### 1. Establish and preserve the baseline

Before editing, record the branch, revision and working-tree state. Treat all
pre-existing changes as user-owned. Do not revert, reset, restore, stash or
delete them unless explicitly authorized.

Destructive Git commands (`reset --hard`, `checkout --`, `restore`, forced
clean) are forbidden without explicit authorization.

### 2. Audit generated paths

Identify build output, caches and generated files (`dist/`, `build/`,
`node_modules/`, coverage, `.vite/`, generated config such as a created
`qapp-config.ts`, lockfile churn). Confirm they are ignored or intentionally
tracked.

### 3. Check tracking, not only ignore rules

A path can be ignored yet already tracked. Verify with
`git ls-files --error-unmatch <path>` where it matters.

### 4. Keep source and output separate

- Do not commit build output unless the project explicitly requires it.
- Do not commit secrets, `.env` files, keys or credentials.
- Do not commit `node_modules`.
- Do not commit report files outside the canonical report root.

### 5. Review the final diff

- `git diff --check` for whitespace/conflict errors.
- Inspect the complete diff, not just the files you remember changing.
- Confirm no unrelated file was touched.
- Confirm no owner change was overwritten.

### 6. External Git/GitHub/GDN actions

Commit, push, tag, GitHub release, QDN publication, deploy and issue mutation are
independent external writes. Each requires explicit owner authorization. Absent
authorization, stop at a clean local diff.

### 7. Backup/restore by request

Only perform backup or restore operations when explicitly requested, and never
in a way that overwrites owner work.

## Mandatory rules

- Never destroy owner changes.
- Never commit secrets or private infrastructure details.
- Never make an external write without authorization.
- A clean `git status` is not proof of a correct change; review the diff.
- Report untracked/generated files explicitly.

## Validation

- `git status --porcelain` before and after.
- `git diff --check`.
- Full diff review.
- Generated-file audit.

## Completion criteria

- Baseline and final state are both recorded.
- The diff contains only intended changes.
- No secret or unintended artifact is included.
- External action state (none/authorized) is stated in the handoff.

## Related files

- [`final-report-and-owner-handoff.md`](final-report-and-owner-handoff.md)
- [`app-release-and-provenance.md`](app-release-and-provenance.md)
