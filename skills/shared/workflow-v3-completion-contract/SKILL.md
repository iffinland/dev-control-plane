---
name: workflow-v3-completion-contract
description: Use when starting, reviewing or resuming any Workflow v3 development job, where mandatory task-start evidence, dirty-owner preservation, a scoped commit, authorized development-branch push and a verified remote SHA must be machine-checked rather than prompt advice.
---

# Workflow v3 Completion Contract

- Platform: `shared`
- Maturity: `candidate`
- Last checked: `2026-11-01`
- Owner: shared capability library

## Use when

Use when any new Workflow v3 job—started by `dev start` or the Telegram Dev
Monitor—must prove task-start skill discovery, freshness verification,
documentation loading, capability harvest, documentation updates, a scoped
commit, an authorized development-branch push and the remote SHA before it can
reach `SUCCESS`. Also use when reviewing an explicit `--contract-file`, preserving
legacy jobs on resume, or reporting contract status truthfully.

## Do not use when

Do not use the contract to grant authority or to replace acceptance tests.
Do not apply it to protected branches, merges, deployment, QDN writes, wallet
transactions or destructive operations unless those are separately authorized.
Do not use it as an OS sandbox. Do not bypass it for a new job by omitting a
contract file, and do not add a retroactive contract to a legacy job during
resume.

## Authoritative evidence

- [`tools/devjob/contract.py`](../../../tools/devjob/contract.py): executable
  checks.
- [`tools/test_completion_contract.py`](../../../tools/test_completion_contract.py):
  regression coverage.
- [`docs/operations/DEV-WORKFLOW-V3.md`](../../../docs/operations/DEV-WORKFLOW-V3.md):
  operating procedure and schema.
- [`examples/workflow-v3/contract.json`](../../../examples/workflow-v3/contract.json):
  reusable shape.
- [`WORKFLOW.md`](../../../WORKFLOW.md), [`GIT-AND-HANDOFF.md`](../../../GIT-AND-HANDOFF.md)
  and the current job authorization.

## Reusable contract / procedure

1. **Every new job gets the mandatory default.** The CLI builds it from the
   real branch, starting `HEAD`, `TASK.md` evidence and the `dev-control-plane`
   remote. The monitor delegates to the same CLI and passes no weakening
   override. An explicit `--contract-file` may add evidence/scope/authorization
   but may not set a mandatory `require` check to `false` or remove all evidence
   files; the loader rejects such a file before a job starts. Push, protected
   branch, merge, deploy, QDN, wallet and destructive actions default to false
   and require their own explicit authorization (`--authorize-push`, a contract
   file field, or the corresponding owner decision).
2. **Record task-start evidence in a durable file** (TASK/STATUS or the job
   report) using explicit labels:
   - skills discovered and their freshness/compatibility result;
   - control-plane, platform-pack and project documentation read;
   - capability harvest result (or explicit project-specific/no-harvest);
   - documentation updates (or explicit none).
3. **Keep commits scoped and preserve owner work.** The default records every
   pre-existing dirty path in both `allowed_dirty_paths` and `forbidden_paths`.
   Never stage, rewrite, discard or demand cleanup of those owner changes, and
   commit only the job's declared scope. Explicit contracts may narrow
   `allowed_paths` further.
4. **Never merge without authorization.** A merge commit in the job range fails
   the contract unless `authorization.merge` is true.
5. **Verify delivery.** With `authorization.push` true, compare the configured
   remote branch SHA (`git ls-remote --heads <remote> <branch>`) with local
   `HEAD`. A mismatch fails. With push false, report
   `PENDING`/`handoff_sync=pending_authorization`, never success. Missing
   authorization makes the job `BLOCKED`; a real acceptance or validation
   failure takes precedence and makes it `FAILED`.
6. **Protect secrets.** Reject secret-bearing paths (`.env`, keys, wallet, seed,
   mnemonic, keystore, credentials) and recognized secret-like diff patterns.
   Never print the matched value. The repository Git hook remains an independent
   content-level scanner.
7. **Fail honestly and keep status truthful.** Contract `FAILED` => job
   `FAILED`; contract `PENDING` => job `BLOCKED`; required acceptance failures
   remain `FAILED` even when authorization is also pending. A new job with a
   missing or skipped mandatory contract cannot succeed. Status and reports must
   show the contract source (`default`/`file`), required flag, state and every
   failed/pending check. Cancelled/timed-out/refused runs skip the contract and
   remain resumable. Legacy jobs keep their recorded state and resume without a
   retroactive contract. Contract success never turns a failed acceptance
   criterion into success.

## Freshness and compatibility gate

Before reusing this skill, read the current
[`contract.py`](../../../tools/devjob/contract.py), the job schema in
[`runner.py`](../../../tools/devjob/runner.py) and the operating doc. Run
`python3 tools/test_completion_contract.py` and
`python3 tools/test_dev_cli.py`. If the schema, check names or state mapping
changed, update this skill and its index entry. The contract is a policy layer,
not an OS sandbox: wrappers, interpreters and SSH can do more than a command
pattern suggests.

## Validation

- Contract tests cover the verified path, missing evidence, uncommitted change,
  declared owner dirty paths, protected branch, unauthorized push, remote-SHA
  mismatch, unauthorized merge, secret path, out-of-scope path and invalid
  schema.
- Default-contract tests prove every new CLI job gets the mandatory checks, a
  weak explicit contract is rejected, custom constraints survive, a monitor
  preview receives the same default, and legacy jobs remain compatible.
- `dev start ... --dry-run` prints the mandatory contract; an explicit
  `--contract-file ... --dry-run` validates the merged plan.
- A real authorized development-branch push is verified with an exact remote
  SHA, not an assumed push result.
- Owner changes outside the declared scope remain uncommitted and preserved.
- Full tests and the security validator pass before handoff.

## Known failure modes

- Treating OpenCode exit `0`, a green acceptance command or a push command exit
  `0` as delivery proof.
- Omitting a contract file to bypass the mandatory default.
- Treating `--contract-file` as a way to disable evidence, commit or push checks.
- Marking an unauthorized push as success instead of `PENDING`, or hiding a real
  validation failure behind `BLOCKED`.
- Committing unrelated owner changes to make the tree clean.
- Using a protected branch without separate authorization.
- Letting a merge commit or out-of-scope path pass silently.
- Printing a matched secret value in a failure detail.

## Non-goals

Not an authority grant, deployment/merge mechanism, QDN or wallet policy, or a
replacement for acceptance criteria and owner review. It does not protect a
remote host from an authorized command.

## Harvest / maturity update

Created 2026-11-01 with the executable contract implementation and extended the
same day to make it mandatory for every new CLI and Telegram-monitor job while
preserving legacy-job resume behavior. Maturity stays `candidate` until a real
job completes through the mandatory default with an authorized push and verified
remote SHA. Re-check after any change to job schema, check IDs, override policy
or state mapping; update the skills index and operating docs in the same change.
