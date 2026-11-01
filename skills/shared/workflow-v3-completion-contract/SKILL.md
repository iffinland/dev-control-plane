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
  checks, NUL-safe dirty-path parsing and legacy path repair.
- [`tools/devjob/evidence.py`](../../../tools/devjob/evidence.py): job-specific
  evidence initialization and the deliberately unfilled template.
- [`tools/test_completion_contract.py`](../../../tools/test_completion_contract.py):
  regression coverage.
- [`tools/devjob/project_policy.py`](../../../tools/devjob/project_policy.py) and
  [`tools/test_project_delivery_policy.py`](../../../tools/test_project_delivery_policy.py):
  validated project-scoped remote and branch policy.
- [`docs/operations/DEV-WORKFLOW-V3.md`](../../../docs/operations/DEV-WORKFLOW-V3.md):
  operating procedure and schema.
- [`examples/workflow-v3/contract.json`](../../../examples/workflow-v3/contract.json):
  reusable shape.
- [`WORKFLOW.md`](../../../WORKFLOW.md), [`GIT-AND-HANDOFF.md`](../../../GIT-AND-HANDOFF.md)
  and the current job authorization.

## Reusable contract / procedure

1. **Every new job gets the mandatory default from one project policy.** The CLI
   resolves exactly one row in `PROJECT-REGISTRY.md` for the repository and
   validates its `Git remote`, matching `GitHub repository`, `agent/*`
   development pattern and `Automatic push` flag against the checkout. The
   monitor delegates to the same CLI with `--project` and `--registry` and
   passes no weakening override. A missing, ambiguous, non-GitHub or mismatched
   remote refuses the start before a job exists; never substitute another
   project's remote or a global `dev-control-plane` default. An explicit
   `--contract-file` may add evidence/scope/authorization but may not set a
   mandatory `require` check to `false`, remove all evidence files or replace
   the validated project remote. The owner authorizes automatic push only to
   matching non-protected `agent/*` branches. Push outside that pattern,
   protected branch, merge, deploy, QDN, wallet and destructive actions default
   to false and require their own explicit authorization.
2. **Fill the automatic per-job evidence file truthfully.** A new default job
   (CLI or Telegram monitor, which delegates to the CLI) gets
   `~/.local/state/dev-control-plane/jobs/<job-id>/evidence/TASK.md`. The
   harness writes only observed metadata and leaves every required field
   `UNRECORDED`; initialization is not completion. The agent must replace each
   value with job-specific evidence and keep the `job_id` line and
   `workflow-v3-evidence` markers. Record:
   - skills discovered and their freshness/compatibility result;
   - control-plane, platform-pack and project documentation actually read;
   - capability harvest result (or explicit project-specific/no-harvest);
   - documentation updates (or explicit none).

   The contract parses the structured block and rejects placeholders, missing
   blocks, values without concrete detail and evidence whose `job_id` is another
   job. An explicit `--evidence-file` replaces automatic initialization; an
   explicit `--contract-file` keeps its own evidence list.
3. **Keep commits scoped and preserve owner work.** The default records every
   pre-existing dirty path in both `allowed_dirty_paths` and `forbidden_paths`.
   Never stage, rewrite, discard or demand cleanup of those owner changes, and
   commit only the job's declared scope. Explicit contracts may narrow
   `allowed_paths` further. A whole-tree `git diff --check` sees those owner
   edits too: the detector attributes a failed check whose warning lines all
   name recorded owner paths as a non-blocking `warning`, not a task failure.
   This is not global failure suppression. Any warning under a non-owner path,
   any mixed result, any unparsed output and any other failed test/build/
   validation/permission command still fails; intervening failures are
   recovered only by later successful evidence for the same operation, and
   `git diff --check` over the task-owned diff is the useful check. Separately,
   `opencode_guard.py check` exit `10` with the explicit
   `opencode-guard: WARN` status line is informational, not a failed command;
   the current job's own OpenCode process and load warning commonly trigger it.
   Only that check subcommand and status are exempt. A guard `REFUSE`, guard
   error/usage failure, non-zero `run`-mode exit or any other command exiting
   `10` still fails.
4. **Never merge without authorization.** A merge commit in the job range fails
   the contract unless `authorization.merge` is true.
5. **Verify delivery.** First verify the recorded policy still matches the
   checkout remote URL and branch pattern (`delivery_policy` / `branch_policy`).
   With `authorization.push` true, compare the configured remote branch SHA
   (`git ls-remote --heads <remote> <branch>`) with local `HEAD`. A mismatch or
   a failed/absent push fails. With push false, report
   `PENDING`/`handoff_sync=pending_authorization`, never success. A branch
   outside the project's `agent/*` pattern never receives automatic push;
   explicitly forcing push there fails. Missing authorization makes the job
   `BLOCKED`; a real acceptance or validation failure takes precedence and makes
   it `FAILED`.
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
`python3 tools/test_completion_contract.py`,
`python3 tools/test_project_delivery_policy.py` and
`python3 tools/test_dev_cli.py`. If the schema, check names, remote-resolution
rules or state mapping changed, update this skill and its index entry. The contract is a policy layer,
not an OS sandbox: wrappers, interpreters and SSH can do more than a command
pattern suggests.

## Validation

- Contract tests cover the verified path, missing evidence, uncommitted change,
  declared owner dirty paths, protected branch, unauthorized push, remote-SHA
  mismatch, unauthorized merge, secret path, out-of-scope path and invalid
  schema. They also cover exact first-path parsing, job-specific evidence
  initialization, refusal to accept the unfilled template, wrong-job evidence,
  removed initialized blocks and the narrow legacy path repair. Policy tests
  cover multiple project remotes, unknown projects, missing/ambiguous/mismatched
  remotes, non-GitHub URLs, `agent/*` matching, disabled automatic push,
  unauthorized branches and failed pushes. Detector tests cover owner-only
  whitespace warnings, genuine task whitespace failures, mixed owner/task
  output, unrelated failed commands, unparsed errors, and same-operation
  recovery versus unrelated success; an integration test proves the contract
  can stay `VERIFIED` while an owner-only warning yields `SUCCESS`, but a
  task-owned whitespace failure still yields `FAILED`.
- Default-contract tests prove every new CLI job gets the mandatory checks, a
  weak explicit contract is rejected, custom constraints survive, a monitor
  preview receives the same default, and legacy jobs remain compatible.
- `dev start ... --dry-run` prints the mandatory contract; an explicit
  `--contract-file ... --dry-run` validates the merged plan.
- A real authorized development-branch push is verified with an exact remote
  SHA, not an assumed push result.
- Owner changes outside the declared scope remain uncommitted and preserved.
- Full tests and the security validator pass before handoff.

## Dev Monitor health versus start preflight

When the Workflow v3 job was started by the Telegram Dev Monitor, do not treat a
healthy running monitor as a broken test fixture. `dev_monitor.py check`
separates the two concerns:

- default/`--expect auto` reports the running instance's health and start
  readiness; a verified live `dev_monitor.py run` lock owner is `lock: ok` and
  does not fail the check;
- `--expect running` is the strict health probe and fails when no verified
  instance is running;
- `--expect start` is the strict preflight probe and must fail while a live
  instance holds the lock because a second instance is refused;
- stale unheld lock files are reported and replaced by a start; unknown lock
  owners and competing monitor processes for one state directory fail closed.

This is read-only inspection of the lock and `/proc`; it never signals the
monitor and does not replace real-Telegram acceptance evidence. Do not relabel
synthetic or automated monitor tests as real production-job delivery.

## Known failure modes

- Treating OpenCode exit `0`, a green acceptance command or a push command exit
  `0` as delivery proof.
- Treating the initialized evidence template, its prose or an `UNRECORDED` value
  as completion evidence, or copying another job's evidence file.
- Omitting a contract file to bypass the mandatory default.
- Treating `--contract-file` as a way to disable evidence, commit or push checks.
- Marking an unauthorized push as success instead of `PENDING`, or hiding a real
  validation failure behind `BLOCKED`.
- Committing unrelated owner changes to make the tree clean.
- Treating a whole-tree `git diff --check` failure as a task failure when every
  reported path is a pre-existing owner path, or over-correcting by suppressing
  all failed commands and hiding real test/build/validation failures.
- Treating `opencode_guard.py check` exit `10` / `opencode-guard: WARN` as a
  failed command, or over-correcting by ignoring guard `REFUSE`, guard errors,
  `run`-mode non-zero exits or other commands that exit `10`.
- Parsing dirty paths with a fixed `line[3:]` after a whole-output `strip()`,
  which truncates the first path (`skills/README.md` -> `kills/README.md`).
- Using a protected branch without separate authorization.
- Hardcoding or reusing `dev-control-plane` for another project, or letting a
  missing/ambiguous policy fall back silently.
- Granting automatic push to `main`, `feature/*` or another non-`agent/*` branch.
- Letting a merge commit or out-of-scope path pass silently.
- Printing a matched secret value in a failure detail.
- Treating a healthy running Dev Monitor lock as a failed preflight, or using the
  default `check` when a strict `--expect start` or `--expect running` outcome is
  required. The lock inspection is not real-Telegram or production-job evidence.

## Non-goals

Not an authority grant, deployment/merge mechanism, QDN or wallet policy, or a
replacement for acceptance criteria and owner review. It does not protect a
remote host from an authorized command.

## Harvest / maturity update

Created 2026-11-01 with the executable contract implementation and extended the
same day to make it mandatory for every new CLI and Telegram-monitor job and to
resolve a validated project-scoped remote/automatic-push policy while preserving
legacy-job resume behavior. Later the same day it gained automatic per-job
evidence initialization, job-specific structured validation (no fabricated or
copied evidence) and NUL-safe dirty-path parsing with a narrow legacy repair.
It also gained owner-path attribution for failed whole-tree `git diff --check`
commands after a verified job was falsely classified `FAILED` solely by a
pre-existing owner skill edit. A later verified job was falsely classified
`FAILED` when `opencode_guard.py check` returned its documented warning exit
`10` because the job's own OpenCode process occupied the one-session slot; the
detector now treats only that explicit, evidenced check-mode WARN as
informational while preserving guard refusals, errors and ordinary non-zero
exits as failures.
Maturity stays `candidate` until a real job completes through the mandatory
default with an authorized push and verified remote SHA. Re-check after any
change to job schema, check IDs, override policy or state mapping; update the
skills index and operating docs in the same change.
