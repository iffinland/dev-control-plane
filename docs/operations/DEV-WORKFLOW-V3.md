# Workflow v3 development jobs

Status: active operating procedure, implemented 2026-10-31.
Scope: owner-authorized autonomous development on the Debian VPS.
Related: [control-plane contract](../../AGENTS.md),
[workflow](../../WORKFLOW.md), [unattended OpenCode runbook](UNATTENDED-OPENCODE.md),
[tmux runbook](OPENCODE-TMUX-SESSIONS.md),
[OpenCode adapter](../../adapters/opencode/README.md).

## What Workflow v3 adds

Workflow v3 is a durable job layer around the existing execution guard and
OpenCode:

- `dev start`, `dev status`, `dev report`, `dev logs`, `dev resume` and additive
  `dev cancel`;
- unique job IDs, start/end timestamps, PID/process tracking and an eight-hour
  wall-clock maximum per attempt;
- persistent job status, event history, run logs and Markdown reports outside
  Git;
- explicit acceptance criteria; OpenCode exit code `0` is never treated as
  acceptance;
- detection of permission rejection, failed commands, missing dependencies,
  agent step exhaustion and incomplete implementation;
- a race-safe session-completion watchdog for runs where the OpenCode CLI stays
  alive after the final assistant message;
- detached background execution that survives SSH disconnect without tmux;
- safe resume of the same OpenCode session and working tree;
- additive, verified cancellation that signals only the job's own guard, marks
  the job `CANCELLED` and preserves the working tree and session for resume;
- optional Telegram notifications for completed, failed, blocked, timed-out and
  cancelled jobs, with credentials outside Git.

It is **not** a scheduler, daemon, timer or network listener. No job starts
itself; the owner starts it. The guard still enforces one heavyweight OpenCode
execution at a time.

## Components

| Component | Path | Purpose |
| --- | --- | --- |
| CLI | `tools/dev.py` | `dev start/status/report/logs/resume/cancel` (plus `accept`) |
| Job engine | `tools/devjob/` | Durable store, detection, notifications, worker and completion contract |
| Execution guard | `tools/opencode_guard.py` | Preflight, one-execution lock, 8-hour maximum, session-completion watchdog, safe cancellation |
| Development profile | `adapters/opencode/agents/opencode-development.md` | Unattended development permissions and hard boundaries |
| Restricted profile | `adapters/opencode/agents/opencode-unattended.md` | Existing restricted profile for non-development tasks |
| Profile installer | `tools/install_opencode_profiles.sh` | Copies/symlinks profiles into `~/.config/opencode/agents/` |
| CLI tests | `tools/test_dev_cli.py` | Integration and unit tests with a fake OpenCode |
| Cancel tests | `tools/test_dev_cancel.py` | Verified guard identity, SIGTERM, refusal and resumability with test-owned processes |
| Completion contract | `tools/devjob/contract.py` | Machine-checked task-start evidence, scoped commit, authorization, push and remote SHA |
| Project delivery policy | `tools/devjob/project_policy.py` | Validated per-project remote, GitHub repository, `agent/*` branch pattern and automatic-push authorization |
| Branch preparation | `tools/devjob/branch_prepare.py` | Pre-start checkout inspection, isolated linked worktrees for dirty owner checkouts, safe `agent/*` branch selection/creation and resume return |
| Git remote probe | `tools/devjob/git_remote.py` | Shared non-interactive Git environment, remote identity, bounded transport retry and safe failure classification for admission and completion |
| Project onboarding | `tools/devjob/onboarding.py` | GitHub URL validation, safe clone, architecture/instruction inspection, registry and acceptance-profile registration |
| Acceptance profiles | `tools/devjob/acceptance_profiles.py`, `acceptance-profiles.json` | Explicit project commands/context for the phone start flow; fail-closed discovery |
| Contract tests | `tools/test_completion_contract.py` | Contract evidence, scope, protected-branch, merge, secret-path and remote-SHA regressions |
| Monitor onboarding tests | `tools/test_dev_monitor_onboarding.py` | Telegram New project wizard, one-time confirmation, replay safety and refusal without touching existing files |
| Branch tests | `tools/test_branch_preparation.py` | Protected main, clean development branch, dirty owner checkout isolation, detached HEAD, remote mismatch, auth failure, concurrency and resume regressions |
| Remote tests | `tools/test_git_remote.py` | Real admission/completion paths through a fake SSH transport: valid key succeeds, broken auth fails safely, transient transport retries once |
| Onboarding tests | `tools/test_onboarding.py` | URL validation, safe clone, duplicate detection, no script execution, acceptance discovery, path/credential refusals |
| Policy tests | `tools/test_project_delivery_policy.py` | Multiple project remotes, missing/ambiguous/mismatched configuration, unauthorized branches and failed pushes |
| Guard tests | `tools/test_opencode_guard.py` | Timeout, cancellation, lock, PID file and safety tests |
| Permission validator | `tools/validate_agent_permissions.py` | OpenCode last-match policy checks, command matrix and limitation report |
| Permission/installer tests | `tools/test_agent_permissions.py`, `tools/test_install_profiles.py` | Profile semantics and installer safety |

Runtime state defaults to:

```text
~/.local/state/dev-control-plane/jobs/<job-id>/
```

Override it with `DEV_CONTROL_PLANE_STATE` or `--state-dir`. Nothing is written
inside a project repository by default. If `XDG_STATE_HOME` is set, the state
root is `$XDG_STATE_HOME/dev-control-plane`.

A job directory contains:

```text
job.json             durable job state and acceptance results
events.jsonl         append-only lifecycle events
run.log              guarded OpenCode output
worker.log           worker/guard console output
child.pid.json       child PID/PGID written by the guard
completion.json      structured session-completion evidence, when detected
cancel.requested.json accepted owner cancel request, scoped to one attempt
acceptance-AC1.log   per-criterion command output
report.md            rendered Markdown report
.worker.lock         per-job worker lock
```

## Install the CLI and profile

The repository script is runnable directly:

```bash
python3 /home/iffi/dev-workspace/control-plane/tools/dev.py status --all
```

Optional user-local command (no system changes):

```bash
mkdir -p ~/.local/bin
ln -sf /home/iffi/dev-workspace/control-plane/tools/dev.py ~/.local/bin/dev
```

Install the OpenCode agent profiles (copies only missing/changed files, does not
change the interactive `build` agent or `opencode.jsonc`):

```bash
/home/iffi/dev-workspace/control-plane/tools/install_opencode_profiles.sh
```

Restart OpenCode after installing or updating an agent profile. Verify the
profile without starting a job:

```bash
opencode debug agent opencode-development
```

## Start a job

Acceptance criteria are mandatory. A criterion is either a command that the
harness runs after the agent exits, or a manual criterion that the owner must
accept explicitly.

```bash
dev start \
  --repo /home/iffi/dev-workspace/projects/example-app \
  --title "finish settings page" \
  --prompt-file /home/iffi/dev-workspace/control-plane/tasks/example/TASK.md \
  --criterion "unit tests::npm test -- --runInBand" \
  --criterion "build::npm run build" \
  --manual-criterion "owner checks the settings page in the live app" \
  --timeout 8h
```

Useful forms:

```bash
# Label::command (label optional)
dev start ... --criterion "pytest::python3 -m pytest -q"

# A JSON acceptance file: array of strings or {kind,label,command} objects
dev start ... --acceptance-file acceptance.json

# Override the automatic evidence file with owner-named evidence paths.
# Without this flag a job-specific evidence file is initialized automatically.
dev start ... --evidence-file TASK.md --evidence-file STATUS.json

# Restrict the scoped commit to exact path prefixes
dev start ... --scope src/ --scope tests/ --scope TASK.md

# Select a registered project explicitly and show its resolved policy
dev start ... --project qortal/my-app --dry-run

# Override the registry path only for an isolated copy/test
dev start ... --registry /path/to/PROJECT-REGISTRY.md --dry-run

# Explicit flags add a separately authorized action; they never replace the
# validated project remote or authorize a non-agent branch automatically.
dev start ... --authorize-push
dev start ... --authorize-protected-branch
dev start ... --authorize-merge

# Validate without starting a job (prints the mandatory default contract)
dev start ... --dry-run

# Explicit read-only audit: an isolated agent/* worktree is prepared, but the
# contract verifies that nothing was committed or pushed.
dev start ... --read-only --no-notify --criterion "manual:owner reviews the audit"

# Disable Telegram for one job
dev start ... --no-notify
```

`dev start` runs the guard preflight first. A refusal creates a `BLOCKED` job
with the refusal reason instead of starting a doomed process. The worker is
started with `start_new_session=True`, its standard streams are redirected to the
job directory and the parent CLI exits immediately. Closing SSH or Termius does
not stop the job; tmux is not required.

The default timeout and the hard maximum are both **8 hours**. Per-attempt
timestamps and exit codes are recorded in `job.json`; resume starts a new
attempt with a fresh maximum.

## Acceptance profiles for the Telegram start flow

The Telegram Dev Monitor's normal start flow derives acceptance criteria from a
verified project profile instead of asking the owner to type commands on a phone.
Resolution order:

1. `<repository>/.workflow/acceptance.json` (project-owned, preferred);
2. `acceptance-profiles.json` next to `PROJECT-REGISTRY.md`, keyed by project ID.

A profile is explicit JSON with `commands` (string or
`{label, command, timeout_seconds}` objects), optional `manual` criteria and
optional `docs`/`skills` context paths. Paths must stay inside their root.
Missing, malformed, empty or unsafe profiles fail closed before any `dev start`
invocation; the monitor never invents a test command from repository contents.
A profile with no safely discovered command may supply only a manual criterion;
a profile with neither a command nor a manual criterion is rejected.
The profile only supplies acceptance commands and discovery context. Every new
job still receives the mandatory default completion contract, the project
delivery policy and the same push/branch protections.

The normal phone flow is project -> task description -> runtime (1h, 2h, 4h or
8h) -> confirmation. Advanced options remain available for explicit criteria, a
custom timeout, a branch label or an explicit **read-only audit** toggle. A
read-only audit prepares the same isolated `agent/*` worktree but the contract
verifies that no commit, push or merge occurred. The Telegram wizard
pre-selects read-only mode when the task explicitly asks for a read-only audit
and explicitly forbids source modification; the owner can always override the
toggle, and the CLI never infers the mode from task text.

### New project from a GitHub URL

Control mode also exposes **New project** (`/newproject [GitHub URL]`). The
owner supplies a GitHub URL, a first-task description and a runtime. On the
one-time confirmation the monitor:

1. accepts only a `github.com owner/name` HTTPS or SSH identity and refuses
   embedded credentials, local paths and `file://` URLs;
2. detects an existing registration or checkout and never overwrites it;
3. stages a `git clone` in a temporary sibling and moves it into place only on
   success (no submodules, no repository scripts executed);
4. inspects manifests and instruction files, detects the likely platform and
   derives conservative acceptance commands from known manifest entries only;
5. writes one registry row (matching GitHub remote, `agent/*`, automatic push)
   and one central acceptance profile, under a state-directory lock;
6. reloads the registry and starts the first job immediately, using the normal
   mandatory contract and branch preparation.

If onboarding succeeds but the first start is refused (for example the global
guard is busy), the project remains registered and the message reports that the
job was not started.

## Result summary versus functional proof

`dev status` and the Telegram job view distinguish:

- technical completion (`VERIFIED`/`NOT VERIFIED`/`PENDING`) from acceptance
  commands and the completion contract;
- functional outcome (`VERIFIED` only with explicit owner/manual acceptance,
  otherwise `NOT VERIFIED`, or `UNRESOLVED` with unresolved issues).

A green build, passing tests and a pushed SHA are technical evidence. They are
not reported as proof that the user's underlying bug is fixed. Full reports and
logs remain available separately.

## Example files

A reusable example prompt, acceptance file and completion contract live under
[`examples/workflow-v3`](../../examples/workflow-v3/TASK.md):

```bash
dev start \
  --repo /home/iffi/dev-workspace/projects/example-app \
  --title "settings page save flow" \
  --prompt-file examples/workflow-v3/TASK.md \
  --acceptance-file examples/workflow-v3/acceptance.json \
  --contract-file examples/workflow-v3/contract.json \
  --timeout 8h
```

## Executable completion contract

Acceptance commands prove that the requested behavior works. In addition, every
**new** Workflow v3 job receives a mandatory completion contract. There is no
start surface—including `dev start` and the Telegram Dev Monitor—that can omit
it. A passing test suite or OpenCode exit `0` therefore cannot by itself produce
`SUCCESS`.

The default contract automatically records the job's real branch and starting
`HEAD`, resolves the remote from the project's validated delivery policy, and
treats every pre-existing dirty owner path as both `allowed_dirty_paths` and
`forbidden_paths`. Owner work is preserved and is never staged, rewritten,
discarded or required to be cleaned. Dirty paths are read with NUL-safe porcelain
output, so the first record is never truncated (`skills/README.md` cannot become
`kills/README.md`). Jobs created before that fix are evaluated with a narrow
one-character-truncation repair, recorded in the contract result; no additional
path is allowed.

### Automatic per-job evidence initialization

A new default job—whether started by `dev start` or the Telegram Dev Monitor,
which delegates to the same CLI—receives one job-specific evidence file:

```text
~/.local/state/dev-control-plane/jobs/<job-id>/evidence/TASK.md
```

The harness records only facts it can observe at start: job ID, title,
repository, branch, base SHA, project and contract source. Every required
task-start field is written as `UNRECORDED`. Initialization is **not**
completion, approval or proof of work, and the harness never fills a required
field.

The job prompt names the file and requires the executing agent to replace each
`UNRECORDED` value with truthful, job-specific evidence from the work actually
performed:

- skills searched/loaded, including platform, maturity and freshness result;
- the control-plane, platform-pack and project documentation actually read;
- the capability-harvest result, or an explicit project-specific/no-harvest;
- documentation updates, or an explicit statement that none were needed.

The evidence file lives outside the project working tree, so it never dirties the
repository and never becomes part of the job's scoped commit. The development
agent profile allows editing only the `jobs/*/evidence/**` subtree; job records
and all other runtime state remain read-only. Use `--evidence-file` only when the
owner deliberately supplies evidence paths instead of the automatic job file.

The contract parses the `workflow-v3-evidence` block and requires the `job_id`
line to match the current job. It fails when a required value is missing,
`UNRECORDED`/placeholder-like, too short, or lacks the expected concrete detail;
it also fails if an initialized block is removed. Evidence copied from another
job is therefore rejected rather than silently accepted by the older free-text
marker scan. The report shows the evidence path and any legacy path repair.

### Project-scoped delivery policy

Before creating a job, both `dev start` and the Telegram Dev Monitor resolve
exactly one row in [PROJECT-REGISTRY.md](../../PROJECT-REGISTRY.md) for the
repository. The row supplies four delivery columns:

| Column | Requirement |
| --- | --- |
| `Git remote` | An existing remote name in the checkout, for example `origin` or the control plane's `dev-control-plane`. |
| `GitHub repository` | `owner/name`; the configured remote URL must normalise to this exact GitHub repository. |
| `Development branch pattern` | Must stay inside `agent/*`. |
| `Automatic push` | `yes`/`no`; explicit owner grant for automatic delivery. |

The owner authorizes automatic push only when the policy is valid, the remote
URL matches, the current branch matches `agent/*`, and the branch is not
protected. `main`/`master`/`trunk`, merges, tags, releases, deployment, QDN
writes, wallet transactions and server changes are never implied. A missing,
ambiguous, non-GitHub or mismatched remote is refused before a job exists. There
is no global `dev-control-plane` fallback: that remote is valid only for the
control-plane row that explicitly configures it.

### Automatic development branch preparation

Before OpenCode starts, and before a job record is created, the shared
`dev start` path (used by both the CLI and the Telegram monitor) inspects the
actual repository: current branch, `HEAD`, linked worktrees, dirty paths, remote
URL and the project-level instructions. It then:

- keeps the current branch when it is already a clean `agent/*` branch matching
  the project policy (the existing development-branch path);
- otherwise creates one deterministic job-scoped branch,
  `agent/<project>/<job-id>`, from the current commit when the checkout is on
  `main`/`master`/`trunk`, another protected branch or an unauthorized branch;
- accepts an explicitly requested `agent/*` branch only when it does not already
  exist or is the current branch. It never reuses an unrelated existing branch;
- checks the configured remote repository identity and performs a non-interactive
  `git ls-remote` authentication/probe with `GIT_TERMINAL_PROMPT=0` and SSH
  BatchMode for SSH remotes. Existing credential helpers and SSH keys remain in
  use; no credential is copied, printed or added, and the remote URL is not
  changed. A clearly transient transport error is retried once; authentication,
  transport, host-key and timeout failures are classified without echoing the URL
  or Git stderr. Concrete transport evidence takes precedence over Git's generic
  "Could not read from remote repository" suffix, which is appended after a reset
  as well as after a real authentication failure. The completion contract uses
  the same canonical probe, so admission and post-run remote-SHA verification
  cannot disagree about the environment.
- when the owner checkout has uncommitted changes and a branch switch/create
  would be required, creates the job branch in an isolated linked worktree under
  `<projects>/.worktrees/<repo>/<job-id>` at the same published commit. The owner
  checkout, its branch and every modification stay untouched. Clean checkouts
  continue to switch in place. Resume returns to the recorded branch and worktree.

Branch preparation fails closed, without resetting, cleaning, stashing,
force-checking-out or rewriting anything, when:

- an isolated worktree cannot be created safely (for example its path already
  exists); the owner checkout is still never reset, cleaned or stashed;
- `HEAD` is detached;
- the current branch is not synchronized with its remote (including unpushed
  local commits such as a historical local `main` commit);
- another RUNNING job is using the same repository or another startup holds the
  repository preparation lock;
- the remote repository identity mismatches the registry or non-interactive
  authentication/transport fails.

If GitHub delivery is unavailable, the start is refused with an actionable owner
message instead of spending tokens on a job that cannot satisfy its mandatory
completion contract. A dry run reports the branch that would be prepared but
does not create it. Resume and restart first return to the branch recorded by
the job, then reuse the recorded contract baseline and verify the remote SHA
against that actual branch. `--authorize-protected-branch` remains an explicit
owner opt-out from automatic branch replacement; it does not grant any other
authorization.

```bash
# The default contract is created automatically; --dry-run prints it.
dev start ... --dry-run

# The project policy authorizes the push; --authorize-push is not required for
# a matching agent/* branch.
dev start ... --dry-run

# The monitor delegates to the same CLI, passing the project ID and registry
# path, and never passes a weakening or remote-selecting override.

# An explicit file may add evidence/scope/authorization. It may not replace the
# validated project remote.
dev start ... --contract-file contract.json --dry-run
```

An explicit `--contract-file` may customize only within owner policy. It may add
evidence files, tighten `allowed_paths`, add `forbidden_paths` or explicitly
authorize an action; it may **not** set a mandatory `require` check to `false` or
remove all evidence files. The harness rejects such a file before a job starts.

The contract is a JSON object. A reusable example is
[`examples/workflow-v3/contract.json`](../../examples/workflow-v3/contract.json).

```json
{
  "version": 1,
  "branch": "agent/example-app/settings-page",
  "base_sha": "<verified base SHA>",
  "remote": "origin",
  "evidence_files": ["TASK.md", "STATUS.json"],
  "allowed_paths": ["src/", "tests/", "TASK.md", "STATUS.json"],
  "allowed_dirty_paths": [],
  "require": {
    "skill_discovery": true,
    "freshness": true,
    "documentation_loading": true,
    "capability_harvest": true,
    "documentation_updates": true,
    "clean_tree": true,
    "commit": true,
    "no_merge_commits": true,
    "push": true
  },
  "authorization": {
    "push": true,
    "protected_branch": false,
    "merge": false,
    "deploy": false,
    "qdn_write": false,
    "wallet_transaction": false,
    "destructive": false
  }
}
```

The `remote` must equal the validated project policy remote; an explicit file
that tries to use another remote is rejected. The default contract already
enables every mandatory check, so an explicit file that omits `require` still
gets them. The resolved policy is stored in the job's contract snapshot, so a
resume evaluates the same remote and branch pattern that the job was created
with. At job completion the harness evaluates the contract in the job repository
and records the result in `job.json`, `dev status`, the monitor job status and
`report.md`:

| Check | What must be evidenced |
| --- | --- |
| `skill_discovery` | The job-specific evidence records the skills searched/loaded, or explicitly that no skill applied. |
| `freshness` | The evidence records the skill/freshness compatibility result and the source revision checked. |
| `documentation_loading` | The evidence names the control-plane/platform/project documentation actually read. |
| `capability_harvest` | The evidence records the reusable result or an explicit project-specific/no-harvest result. |
| `documentation_updates` | The evidence records the documentation changed or explicitly that none was needed. |
| `evidence_identity` | An auto-initialized evidence block names the current job ID; another job's or copied evidence fails. |
| `branch` / `protected_branch` | The current branch matches the actually prepared contract branch and is not a protected branch without explicit authorization. |
| `delivery_policy` / `branch_policy` | The recorded project policy still matches the actual remote URL and the current branch is inside its `agent/*` pattern. |
| `clean_tree` | The job's changes are committed; declared pre-existing owner paths may stay dirty. |
| `read_only` | Only when requested (CLI flag, Telegram toggle or the wizard's conservative pre-selection for an explicit read-only audit): delivery is not required, but the evaluator still verifies that no commit after the base SHA and no push occurred. A read-only job that commits fails the contract. |
| `commit` / `scoped_paths` | At least one commit exists after `base_sha`, and every changed path is inside `allowed_paths`. |
| `no_merge_commits` | No merge commit exists unless `authorization.merge` is true. |
| `sensitive_paths` / `diff_secrets` | No `.env`, key/keystore/wallet/seed path or recognized secret pattern is committed. Unmatched values are never printed. |
| `remote_sha` | When `authorization.push` is true, the configured remote branch SHA equals local `HEAD`. When false, the result is `PENDING` (`handoff_sync=pending_authorization`), not a silent success. |

A contract `FAILED` makes the job `FAILED`. A contract `PENDING` (for example a
required but unauthorized push) makes the job `BLOCKED`. A required acceptance
or validation failure takes precedence over a pending authorization, so a
genuine failure is never hidden behind `BLOCKED`. Contract checks never grant
authority; each external action still requires its own explicit `authorization`
flag. A new job whose mandatory contract is missing, skipped or not verified
cannot reach `SUCCESS`, even when OpenCode exits `0` with a green test suite.

The contract is evaluated after the acceptance commands and before the final
state is computed. Cancelled, timed-out and guard-refused runs skip it and
remain resumable. Jobs created before the mandatory rule have no recorded
contract; they retain legacy behavior on status and resume rather than being
retroactively failed or granted a new contract.

## Job states and acceptance

| State | Meaning |
| --- | --- |
| `RUNNING` | The detached worker is active, or state has not yet been reconciled. |
| `SUCCESS` | The guard completed the run (process exit `0`, or a confirmed session completion stopped a hung CLI), every required criterion verified, the mandatory completion contract verified, and no unresolved blocking/failure detector fired. |
| `FAILED` | A required criterion failed, an unresolved failure detector fired, or the process exited non-zero. |
| `BLOCKED` | The guard refused, an unresolved permission/dependency/marker blocked the run, manual acceptance is pending, or a required external action still lacks explicit authorization. |
| `TIMEOUT` | The guard reached the wall-clock limit (exit code `124`). |
| `CANCELLED` | An owner cancel request was verified and delivered to the job's own guard; acceptance commands are skipped and the job remains resumable. |

`SUCCESS` is computed from evidence, not from the OpenCode exit code alone. A
run that exits `0` but fails an acceptance command, reports an incomplete
implementation, leaves a permission denial unresolved, has no git commit, or
fails/pends the mandatory completion contract is `FAILED` or `BLOCKED`.

Detected signals include:

- permission rejection / auto-rejection / approval requirement;
- failed command, build or test output and non-zero exit records;
- missing command, module, package or dependency;
- maximum/step-limit exhaustion;
- explicit incomplete or not-implemented statements, and `BLOCKED:` markers;
- required acceptance criteria that did not verify (recorded as incomplete).

Detection prefers structured OpenCode tool events from
`opencode export <session-id>`. The export is parsed in memory and is not written
to the job directory; only short sanitized issue excerpts are retained. Events
are filtered to the current attempt, so a resolved error from an earlier attempt
does not re-block a resumed job.

Structured events preserve order so an intermediate failure can be classified
as recovered:

- a permission rejection followed by successful tool activity is a `warning`
  and does not block; a rejection with no later success remains `blocked`;
- a failed command is recovered only when a later successful command performs
  the same operation (for example a scoped retry of `git diff --check`);
- missing dependencies, step exhaustion, incomplete implementation and
  `BLOCKED:` markers are never auto-recovered;
- required acceptance criteria remain independent and authoritative. A recovered
  error never turns a failed criterion into success.

A failed whole-tree `git diff --check` is additionally attributed against the
pre-existing owner paths recorded in the job's contract snapshot. If every
whitespace warning in its output names a declared owner path, the result is a
`warning` explaining that the check reported only pre-existing owner changes; it
does not recover or mask a task failure. A whitespace warning under any other
path stays `failed`, and the same owner paths do not suppress failed tests,
builds, validation commands or permission failures. Unparsed output, a
non-`git diff --check` command, or a job without recorded owner paths keeps the
normal failure classification. Owner dirt remains preserved and uncommitted, so
`git diff --check` run over the whole worktree is not evidence about the job's
own diff; use the scoped task diff for that check.

`opencode_guard.py check` exit `10` (`EXIT_WARN`) is an informational preflight
result, not a failed command. The guard returns it for a documented warning such
as RAM/disk headroom, load above the warning threshold, or the one-session limit
being occupied by this job's own OpenCode process. The detector treats it as
informational only when the command is the guard's `check` subcommand and the
output contains the explicit `opencode-guard: WARN` status line. A guard
`REFUSE` (exit `20`), a guard error/usage failure, a non-zero `run`-mode exit or
any other command exiting `10` still fails. The guard's informational process
line can include the job title and prompt text, so the check-mode status line and
subcommand are the evidence; prompt words are not treated as failures.

Recovered issues remain visible in `dev status` and `report.md` with recovery
evidence. The context-aware log fallback cannot prove same-operation recovery, so
it stays conservative; the owner-path attribution above also applies to its
failed `git diff --check` blocks. The fallback treats other permission rejections
as blocking.

When structured export is unavailable, the detector parses the default OpenCode
console log with runtime context. It inspects failed tool blocks and explicit
runtime error lines, not arbitrary file content. Documentation, source code,
read/edit output and git diff text are not treated as permission or dependency
failures merely because they contain phrases such as "permission denied" or
"is not installed". The acceptance commands and the job report remain
authoritative.

## Session completion and hung CLI

OpenCode 1.19.5 can leave `opencode run` alive after a resumed session has
already produced its final assistant message. The guard therefore does not rely
on process exit alone. It watches the same structured session state used by
detection (`opencode export <session-id>`) and treats the agent turn as complete
only when all of these hold:

- the newest message created during the current attempt is an assistant message
  with `finish=stop` and no error;
- no tool part created during that attempt is `pending` or `running`;
- the session has been quiescent for the idle window; and
- two consecutive observations agree, with a fresh export immediately before the
  process group is stopped.

Only then does the guard stop the process group it created, and it records
`completion.json`. The guard returns success for that attempt; the worker still
runs every required acceptance criterion and failure detector. **`finish=stop`
alone is never success**, and a stop message from an earlier attempt is ignored.

If an active tool call or newer work appears between observations, the guard
keeps waiting instead of terminating the process. A run that never produces a
confirmed completion still ends as `TIMEOUT` at the wall-clock limit.

The watcher poll/idle/confirmation windows default to 5/20/5 seconds. They can be
overridden for controlled tests with `DEV_SESSION_POLL_SECONDS`,
`DEV_SESSION_IDLE_SECONDS` and `DEV_SESSION_CONFIRM_SECONDS`. The session id is
known for a resume; for a new job the guard discovers it by exact session title
(the job title plus job id).

## Inspect, report and follow logs

```bash
dev status                       # latest job
dev status <job-id>
dev status --all
dev status <job-id> --json

dev report <job-id>              # prints and rewrites report.md
dev logs <job-id> -n 200         # run.log
dev logs -f <job-id>             # follow until interrupted
dev logs <job-id> --worker       # worker/guard console log
```

`dev status` reports both clocks explicitly: **total job elapsed** from the
job's first start (fixed at `ended_at` once terminal) and **current/last attempt
elapsed** from that attempt's own start. Resuming a job adds a new attempt, so the
attempt duration is normally shorter than the total. `dev status --json` exposes
`elapsed_seconds`, `duration_seconds`, `attempt_elapsed_seconds`,
`attempt_duration_seconds`, `total_attempt_seconds` and `attempt_number`.

If a `RUNNING` job's worker has disappeared, `dev status` reconciles it to
`FAILED` with a `worker_lost` issue and records a notification. `dev resume`
then continues the job.

## Resume without discarding work

```bash
dev resume <job-id>
dev resume <job-id> --timeout 8h
dev resume <job-id> --prompt "Continue from the failing test; do not reset the tree."
dev resume <job-id> --prompt-file -   # read a long instruction from stdin
dev resume <job-id> --new-session     # only when the original session is unknown
dev resume <job-id> --force           # re-run an already successful job
```

Resume reuses the same job directory, repository/worktree and OpenCode session
(`opencode run --session <id>`). It appends a new attempt and never runs Git
reset, clean, stash or checkout. If the session ID is unknown, resume refuses to
attach to a random session unless `--new-session` is explicitly requested.

## Cancel without discarding work

```bash
dev cancel <job-id>
dev cancel <job-id> --json
dev cancel <job-id> --grace 30
```

Cancellation is deliberately narrow:

1. The job must be `RUNNING` with a live worker.
2. The recorded guard PID is revalidated against `/proc/<pid>/cmdline`: it must
   be `opencode_guard.py run` for this exact job, log path or session title.
3. PID 1, the caller's process group and detected Qortium processes are refused.
4. A durable `cancel.requested.json` marker and an append-only `cancel_requested`
   event are written before the signal.
5. `SIGTERM` is sent to that exact guard PID only. The guard uses its existing
   safe child-process-group termination. No name-based kill is used.
6. The worker observes the marker, skips acceptance commands, writes
   `CANCELLED` plus a report, and preserves the working tree and session. If the
   worker is already gone, `dev cancel` reconciles or finalizes a matching
   cancellation itself. If the guard survives the bounded grace period, the
   command reports `cancel_status: pending` and does not escalate.
7. `dev resume <job-id>` continues the same job, worktree and session like any
   other terminal attempt. An old cancel marker never applies to a new attempt.

A cancelled job is not deleted. The cancel marker is durable evidence and is
scoped to one attempt number. `dev status` reports `CANCELLED` and
`cancelled_at`.

## Manual acceptance

For manual criteria, inspect the evidence and then record acceptance:

```bash
dev accept <job-id> --all-manual --note "checked staging UI"
dev accept <job-id> --criterion AC3
```

Only manual criteria can be accepted this way. Command criteria must still pass.

## Telegram notifications

Notifications are optional and use a credential file outside Git:

```text
~/.config/dev-control-plane/telegram.json
```

Override the path with `DEV_TELEGRAM_CONFIG`. Example shape (replace values with
the owner's real credentials, never commit them):

```json
{
  "enabled": true,
  "bot_token": "<configured outside Git>",
  "chat_id": "<configured outside Git>",
  "events": ["SUCCESS", "FAILED", "BLOCKED", "TIMEOUT", "CANCELLED"],
  "timeout_seconds": 10
}
```

Recommended file mode is `0600`. The loader warns if the file is group/world
accessible. Environment overrides are also supported:

```text
DEV_TELEGRAM_ENABLED
DEV_TELEGRAM_BOT_TOKEN
DEV_TELEGRAM_CHAT_ID
DEV_TELEGRAM_CONFIG
```

Credentials are never written to `job.json`, logs, reports or Git. Notification
failures are recorded as sanitized reasons and never change the job result. Final
messages report `duration (total)` and `duration (attempt #N)` separately so a
resumed job is not misread as one continuous attempt. Use `--no-notify` for a
single job.

## Permissions and security

The development profile is
[`adapters/opencode/agents/opencode-development.md`](../../adapters/opencode/agents/opencode-development.md).
It allows normal development in `/home/iffi/dev-workspace/**`: project edits,
project-local dependency installation, builds/tests, Git commit/push/PR, SSH,
QDN publish/update, Qortal API calls, authorized development-wallet operations
and live application tests. Approved tooling roots also include Workflow v3
state (`/home/iffi/.local/state/dev-control-plane`), the OpenCode installation
(`/home/iffi/.opencode`), `/tmp/opencode` and the OpenCode tool-output cache. It
also permits read-only diagnostics of the VPS and the running Qortium node. It
declares explicit allow/deny rules so unattended work does not wait for routine
permission prompts. Do not use `--auto`.

`external_directory` is a separate OpenCode check. Last matching rule wins, and
a `/**` pattern does not match the directory root itself. Approved roots
therefore appear with and without the trailing glob. Unknown external paths
remain denied; credential directories (`~/.ssh`, `~/.config`, `~/.gnupg`,
`~/.aws`, `~/.kube`, `~/.docker`) and the OpenCode auth file stay denied. Job
state is readable but not editable by the agent.

Hard boundaries:

- no Qortium node/service/configuration/database/data/log/JAR mutation, restart,
  stop or signal;
- no VPS system-configuration change, mutating service-manager operation,
  reboot/shutdown, mount/network/kernel change or global package install;
- no `sudo`/`su`, `kill`/`pkill`/`killall`, `tmux kill-server`, or
  `opencode serve/web/acp`;
- no force-push, branch merge, release or deployment;
- no package-registry publication; QDN publishing is allowed only within the
  job's authorization;
- read-only Qortium file access goes through the `read` tool; shell mutation
  commands, redirection and `edit` operations on the Qortium paths are denied;
- Qortium wallet JSON, wallet directories, seed, mnemonic and keystore files are
  denied to the file tools and common shell read forms.

Qortium paths are no longer denied by a broad substring rule. A command that
merely mentions `qortium-data` (for example a documentation search or a test)
is allowed; commands that mutate, move, copy or redirect into the protected paths
are denied. As documented in
[OpenCode permission semantics](OPENCODE-PERMISSIONS.md), these patterns are
policy, not an OS sandbox.

The profile intentionally allows `ssh` because normal development and read-only
remote diagnostics need it. That is not a remote isolation control: an SSH
command can run anything the remote account can run. Remote safety is governed
by the job authorization and the control-plane contract.

The profile also allows `qortal` commands for QDN/development-wallet work and
permits read-only Qortium diagnostics through `systemctl status`, `journalctl`,
`ps`, `service ... status` and the `read` tool. It keeps the Qortium node
process, JAR and paths out of shell writes.

### Permission semantics and limitations

OpenCode evaluates permission patterns with **last matching rule wins**; bash
rules match each parsed shell command. Without `--auto`, an `ask` decision is
auto-rejected in a non-interactive run. The full model, the development policy
and the remaining bypasses are documented in
[OpenCode permission semantics](OPENCODE-PERMISSIONS.md).

Permission patterns are **not** an OS sandbox. Shell wrappers, interpreters,
scripts, SSH sessions, copied binaries and remote commands can do more than the
visible pattern suggests. The guard independently refuses to start a second
heavyweight OpenCode execution, reads Qortium only to report PID/RSS, and
terminates only the process group it created. Owner authorization, Git hooks,
branch protection and review remain authoritative.

Validate a profile change before installing it:

```bash
python3 tools/validate_agent_permissions.py --check
python3 tools/test_agent_permissions.py
tools/install_opencode_profiles.sh --check
```

Never use a development permission to modify the live Qortium node or VPS system
configuration.

## Recovery and stop conditions

- `TIMEOUT` or step exhaustion: preserve the working tree and session, then
  `dev resume`.
- `BLOCKED` due to permission/dependency: fix the environment or task scope,
  then resume. The job retains the blocking evidence.
- Worker disappeared: `dev status` reconciles it; resume continues.
- Resource WARN/REFUSE from the guard: stop starting new work and write a
  recoverable handoff. A check-mode `WARN` caused by this job's own OpenCode
  process is informational and does not fail the job, but do not start another
  heavy session; a `REFUSE` or guard error remains blocking/failing. Do not
  signal Qortium or any process by name.
- To stop new work, wait for the current job or interrupt the guard only inside
  the job it owns. Do not use `pkill`, `killall` or `tmux kill-server`.

## Tests

```bash
python3 tools/test_opencode_guard.py
python3 tools/test_branch_preparation.py
python3 tools/test_git_remote.py
python3 tools/test_onboarding.py
python3 tools/test_dev_monitor_onboarding.py
python3 tools/test_dev_cli.py
python3 tools/test_completion_contract.py
python3 tools/test_project_delivery_policy.py
python3 tools/test_agent_permissions.py
python3 tools/test_install_profiles.py
python3 tools/test_detect.py
python3 tools/test_session_lifecycle.py
python3 tools/validate_agent_permissions.py --check
python3 tools/validate_control_plane.py
python3 tools/validate_skills.py
python3 tools/validate_security.py .
```

The CLI tests use a disposable fake `opencode` executable, a temporary Git
repository and remote, and a synthetic procfs root, including a
hung-CLI-after-`finish=stop` regression case. They prove that a new job without
push authorization ends `BLOCKED` with a `PENDING` contract, that the default
contract is mandatory, that a project's own remote is used instead of a global
default, that pre-existing owner files are preserved, that a weak
`--contract-file` is rejected, and that an explicit contract may customize while
keeping mandatory checks. Branch-preparation tests cover protected `main`,
clean `agent/*` reuse, dirty trees, detached HEAD, remote mismatch, failed
non-interactive authentication, unpushed local commits, active repositories,
the repository lock, requested-branch collision and resume; CLI integration also
proves a protected-main start creates and delivers a job-scoped branch while
leaving `main` unchanged. The policy tests additionally cover multiple project
remotes, unregistered/missing/ambiguous/mismatched remotes, non-GitHub URLs,
unauthorized branches, disabled automatic push and a failed push. They also include recovered and unresolved permission
rejections, recovered same-operation command failures and unrelated successful
commands that must not clear a failure. Owner-path attribution is covered on
both the structured and console paths: a whole-tree whitespace check naming only
pre-existing owner files becomes a non-blocking warning, while a task-owned
whitespace warning, a mixed owner/task result, an unparsed error, or any other
failed command still fails even when the completion contract verifies. Guard
check-mode regressions prove that `opencode-guard: WARN` with exit `10` (including
the job's own heavyweight process and load warning) is informational on both the
structured and console paths, while `REFUSE`, guard errors, `run`-mode exit `10`
and ordinary non-zero commands still fail. The detection tests include the actual
documentation, source/diff and failed-tool log examples from the permissions job,
plus the recovered/unresolved structured-event matrix. `test_session_lifecycle.py` covers structured completion evidence,
active-tool safety, attempt scoping and total-vs-attempt duration reporting. The
permission tests parse the agent Markdown and exercise the last-match wildcard
model, approved tooling roots, exact directory-root matching, Qortium diagnostics
and hard boundaries; they also record the known wrapper/script limitations. The
completion-contract tests cover default/override policy, legacy-job compatibility
and truthful state mapping; the monitor facade test proves a monitor preview gets
the same mandatory default. Additional regressions cover NUL-safe dirty-path
parsing (including the former `skills/README.md` -> `kills/README.md`
truncation), automatic per-job evidence initialization, per-job evidence
identity, refusal to fabricate unfilled evidence, and removal of the initialized
evidence block. They do not start a model session, contact Telegram
or touch Qortium.

## Known limits

- one heavyweight OpenCode job at a time (guard lock);
- job attempts are bounded by 8 hours each, not a single cumulative 8-hour cap;
- no recurring scheduler, timer or auto-dispatch;
- a deliberately daemonized child can escape the guard process group;
- permission patterns are not a sandbox;
- structured detection depends on `opencode export` remaining available for the
  session; the context-aware log parser is the fallback;
- session completion also depends on `opencode export`; if export is unavailable
  the guard falls back to the wall-clock timeout rather than guessing, and
  completion detection is limited to sessions whose id or exact title is known;
- generic non-execution tool errors (for example a 404 web fetch) are ignored
  unless they indicate a permission or dependency problem; execution-tool
  failures remain detectable, with same-operation retries classified as
  recovered warnings;
- Telegram delivery depends on the owner's network and bot configuration;
- OpenCode upgrades can change agent/permission or output semantics;
- resume depends on OpenCode session history remaining in its SQLite store;
- isolated worktrees are deliberately retained for resume and are not removed
  automatically; an owner may remove a finished job's clean worktree explicitly;
- onboarding accepts only GitHub repositories and never executes a project's own
  test command during discovery; the first execution happens as a normal
  acceptance/agent step after the job starts.
