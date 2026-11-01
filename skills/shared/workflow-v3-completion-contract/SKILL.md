---
name: workflow-v3-completion-contract
description: Use when starting or reviewing a Workflow v3 development job and its task-start evidence, scoped commits, authorized push and verified remote SHA must be machine-checked rather than prompt advice.
---

# Workflow v3 Completion Contract

- Platform: `shared`
- Maturity: `candidate`
- Last checked: `2026-11-01`
- Owner: shared capability library

## Use when

Use when an owner-authorized Workflow v3 job must prove task-start skill
discovery, freshness verification, documentation loading, capability harvest,
documentation updates, a scoped commit, an authorized development-branch push and
the remote SHA before it can reach `SUCCESS`.

## Do not use when

Do not use the contract to grant authority or to replace acceptance tests.
Do not apply it to protected branches, merges, deployment, QDN writes, wallet
transactions or destructive operations unless those are separately authorized.
Do not use it as an OS sandbox.

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

1. **Start with explicit authorization.** The task records repository, branch,
   base SHA, allowed paths, remote and each external action. Push, protected
   branch, merge, deploy, QDN, wallet and destructive actions default to false.
2. **Record task-start evidence in a durable file** (TASK/STATUS or the job
   report) using explicit labels:
   - skills discovered and their freshness/compatibility result;
   - control-plane, platform-pack and project documentation read;
   - capability harvest result (or explicit project-specific/no-harvest);
   - documentation updates (or explicit none).
3. **Keep commits scoped.** Commit only declared paths. Do not rewrite owner
   changes or include unrelated dirty files. Declare pre-existing owner paths in
   `allowed_dirty_paths` so they remain preserved rather than bundled.
4. **Never merge without authorization.** A merge commit in the job range fails
   the contract unless `authorization.merge` is true.
5. **Verify delivery.** With `authorization.push` true, compare the configured
   remote branch SHA (`git ls-remote --heads <remote> <branch>`) with local
   `HEAD`. A mismatch fails. With push false, report
   `PENDING`/`handoff_sync=pending_authorization`, never success.
6. **Protect secrets.** Reject secret-bearing paths (`.env`, keys, wallet, seed,
   mnemonic, keystore, credentials) and recognized secret-like diff patterns.
   Never print the matched value. The repository Git hook remains an independent
   content-level scanner.
7. **Fail honestly.** Contract `FAILED` => job `FAILED`; contract `PENDING` =>
   job `BLOCKED`. Cancelled/timed-out/refused runs skip the contract and remain
   resumable. Contract success never turns a failed acceptance criterion into
   success.

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

- Contract tests cover verified, missing evidence, uncommitted change, declared
  owner dirty paths, protected branch, unauthorized push, remote-SHA mismatch,
  unauthorized merge, secret path, out-of-scope path and invalid schema.
- `dev start --contract-file ... --dry-run` validates the plan.
- A real authorized development-branch push is verified with an exact remote
  SHA, not an assumed push result.
- Owner changes outside the declared scope remain uncommitted and preserved.
- Full tests and the security validator pass before handoff.

## Known failure modes

- Treating OpenCode exit `0`, a green acceptance command or a push command exit
  `0` as delivery proof.
- Marking an unauthorized push as success instead of `PENDING`.
- Committing unrelated owner changes to make the tree clean.
- Using a protected branch without separate authorization.
- Letting a merge commit or out-of-scope path pass silently.
- Printing a matched secret value in a failure detail.

## Non-goals

Not an authority grant, deployment/merge mechanism, QDN or wallet policy, or a
replacement for acceptance criteria and owner review. It does not protect a
remote host from an authorized command.

## Harvest / maturity update

Created 2026-11-01 with the executable contract implementation. Maturity is
`candidate` until at least one real development job completes through the
contract with an authorized push and verified remote SHA. Re-check after any
change to job schema, check IDs or state mapping; update the skills index and
operating docs in the same change.
