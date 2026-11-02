---
name: workflow-v3-completion-contract
description: Use when starting, reviewing or resuming any Workflow v3 development job, where mandatory task-start evidence, dirty-owner preservation, a scoped commit, authorized development-branch push and a verified remote SHA must be machine-checked rather than prompt advice.
---

# Workflow v3 Completion Contract

- Platform: `shared`
- Maturity: `candidate`
- Last checked: `2026-11-02`
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
- [`tools/devjob/branch_prepare.py`](../../../tools/devjob/branch_prepare.py) and
  [`tools/test_branch_preparation.py`](../../../tools/test_branch_preparation.py):
  pre-start checkout inspection, isolated linked worktrees for dirty owner
  checkouts, safe `agent/*` branch creation and resume return.
- [`tools/devjob/git_remote.py`](../../../tools/devjob/git_remote.py) and
  [`tools/test_git_remote.py`](../../../tools/test_git_remote.py): one canonical
  non-interactive environment for admission and completion, bounded transient
  retry, and failure classification without leaking the URL or Git stderr.
- [`tools/devjob/onboarding.py`](../../../tools/devjob/onboarding.py),
  [`tools/test_onboarding.py`](../../../tools/test_onboarding.py) and
  [`tools/test_dev_monitor_onboarding.py`](../../../tools/test_dev_monitor_onboarding.py):
  safe GitHub clone, duplicate detection, manifest-only acceptance discovery,
  registry/profile registration and Telegram one-time confirmation.
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

   **Prepare the branch before OpenCode starts.** The same `dev start` path used
   by the CLI and Telegram resolves the policy, inspects branch/`HEAD`/worktrees/
   dirty paths/remote, and either keeps a current matching `agent/*` branch or
   creates one deterministic `agent/<project>/<job-id>` branch. It never reuses
   an unrelated existing branch, resets, cleans, stashes, force-checks-out or
   rewrites history. Dirty switching, detached HEAD, unpushed local commits, a
   conflicting branch or another active job fails closed. It verifies remote
   repository identity and non-interactive auth (`GIT_TERMINAL_PROMPT=0`, SSH
   BatchMode) before any job exists; if GitHub delivery is unavailable the start
   is refused instead of spending tokens. The contract baseline, automatic-push
   authorization and remote-SHA check use the actual prepared branch, and
   resume/restart first returns to the branch recorded by the job. A dry run
   reports the planned branch without creating it. When the owner checkout is
   dirty and a switch/create would be required, create the branch in an isolated
   linked worktree (`<projects>/.worktrees/<repo>/<job-id>`) at the same published
   commit. Never switch, reset, clean, stash or commit the owner checkout. Jobs
   in the owner checkout and its worktrees share one repository identity for
   admission and locking. An explicit `--read-only` (Telegram read-only audit
   toggle) still prepares an isolated `agent/*` worktree but verifies that no
   commit, push or merge occurred; never infer read-only from task wording.
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

8. **Resolve acceptance commands, never invent them.** A phone/monitor start
   uses a verified project profile: `<repo>/.workflow/acceptance.json` first,
   then `acceptance-profiles.json` next to the project registry, keyed by
   project ID. The profile is explicit JSON with commands and optional manual
   criteria/context. A missing, malformed, empty, absolute, traversal or
   missing-file context path fails closed before `dev start`. Do not infer a
   test command from a filename, README or package manager. The profile only
   supplies criteria/context; it cannot disable the mandatory contract,
   delivery policy, branch protection, secrets checks or confirmations.
9. **Separate technical completion from functional outcome.** Technical
   completion is `VERIFIED`/`NOT VERIFIED`/`PENDING` from acceptance results and
   the contract. Functional outcome is `VERIFIED` only with explicit
   owner/manual acceptance, otherwise `NOT VERIFIED`, or `UNRESOLVED` with a
   blocker/unresolved issue. A build, test suite and pushed commit are never
   proof that the owner's underlying bug is fixed. Keep full reports/logs behind
   their optional actions.

## Freshness and compatibility gate

Before reusing this skill, read the current
[`contract.py`](../../../tools/devjob/contract.py),
[`branch_prepare.py`](../../../tools/devjob/branch_prepare.py), the job schema in
[`runner.py`](../../../tools/devjob/runner.py) and the operating doc. Run
`python3 tools/test_completion_contract.py`,
`python3 tools/test_project_delivery_policy.py`,
`python3 tools/test_branch_preparation.py`,
`python3 tools/test_dev_cli.py` and
`python3 tools/test_dev_monitor_mobile_ux.py`. If the schema, check names, remote-resolution
rules, branch-selection rules or state mapping changed, update this skill and its
index entry. The contract is a policy layer,
not an OS sandbox: wrappers, interpreters and SSH can do more than a command
pattern suggests.

## Telegram project onboarding

The control surface may accept a GitHub URL plus a task description and runtime.
On one-time confirmation it validates `github.com owner/name`, refuses duplicate
registrations and unsafe targets, stages `git clone` in a temporary sibling
(no submodules, no repository scripts executed), inspects manifests/instructions,
derives conservative acceptance commands from known manifest entries only,
writes one registry row and central profile under a state-directory lock, then
starts the first job through the normal CLI contract. A manual-only profile is
valid when no safe command is discovered; an empty profile with no manual
criterion is not. If the first start is refused, the registration remains and
the result says explicitly that no job was started.

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
- Branch-preparation tests prove protected `main` becomes a job-scoped
  `agent/*` branch, a clean matching development branch is reused, and a dirty
  tree, detached HEAD, remote mismatch, failed non-interactive auth, unpushed
  local commit, active job or held preparation lock refuses without mutation.
  Resume returns to the recorded branch; a requested existing unrelated branch is
  rejected. CLI integration proves protected-main delivery leaves `main`
  unchanged and the remote SHA equals the prepared branch HEAD.
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

## Acceptance evidence classes

When a task reports live acceptance, keep these classes separate in the matrix:

- **automated/scripted** — fake transport, fake CLI or scripted harness; proves
  code paths only;
- **real transport + synthetic backend** — an actual bot or network round-trip
  driving an isolated synthetic worker; proves the transport path, not a
  production worker or production job;
- **retained real-runtime evidence** — sanitized journal or report with IDs and
  timestamps; the strongest live evidence;
- **owner-attested** — a dated owner observation without retained harness
  evidence; record exactly what was seen and never expand it into an unobserved
  guarantee;
- **unexecuted** — keep as pending or an explicit exception, never a pass.

Cleaning a temporary evidence directory does not authorize reconstructing
identifiers. Do not promote automated, scripted or synthetic-backend results to
production-worker evidence.

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
- Using a protected branch without separate authorization, or starting on
  `main`/`master` instead of preparing the job's `agent/*` branch first.
- Reusing an unrelated existing development branch, or silently moving dirty
  work, unpushed commits or another active job's checkout onto a new branch.
- Starting a job before verifying the remote repository and non-interactive
  GitHub authentication, then discovering at completion that delivery is
  impossible.
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
default with an authorized push and verified remote SHA. It also gained a
reusable acceptance-evidence classification so automated, scripted,
real-transport/synthetic-backend, owner-attested and unexecuted results are not
collapsed into one another. It then gained safe automatic development-branch
preparation: protected or unauthorized checkouts become deterministic
job-scoped `agent/*` branches before OpenCode starts, remote identity and
non-interactive authentication are proven first, and dirty/detached/unpushed/
conflicting/active states fail closed without rewrite. Re-check after any change
to job schema, check IDs, branch-selection rules, override policy or state
mapping; update the skills index and operating docs in the same change.
