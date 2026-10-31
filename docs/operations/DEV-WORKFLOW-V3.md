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

- `dev start`, `dev status`, `dev report`, `dev logs` and `dev resume`;
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
- optional Telegram notifications for completed, failed, blocked and timed-out
  jobs, with credentials outside Git.

It is **not** a scheduler, daemon, timer or network listener. No job starts
itself; the owner starts it. The guard still enforces one heavyweight OpenCode
execution at a time.

## Components

| Component | Path | Purpose |
| --- | --- | --- |
| CLI | `tools/dev.py` | `dev start/status/report/logs/resume` (plus `accept`) |
| Job engine | `tools/devjob/` | Durable store, detection, notifications, worker |
| Execution guard | `tools/opencode_guard.py` | Preflight, one-execution lock, 8-hour maximum, session-completion watchdog, safe cancellation |
| Development profile | `adapters/opencode/agents/opencode-development.md` | Unattended development permissions and hard boundaries |
| Restricted profile | `adapters/opencode/agents/opencode-unattended.md` | Existing restricted profile for non-development tasks |
| Profile installer | `tools/install_opencode_profiles.sh` | Copies/symlinks profiles into `~/.config/opencode/agents/` |
| CLI tests | `tools/test_dev_cli.py` | Integration and unit tests with a fake OpenCode |
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

# Validate without starting a job
dev start ... --dry-run

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

## Example files

A reusable example prompt and acceptance file live under
[`examples/workflow-v3`](../../examples/workflow-v3/TASK.md):

```bash
dev start \
  --repo /home/iffi/dev-workspace/projects/example-app \
  --title "settings page save flow" \
  --prompt-file examples/workflow-v3/TASK.md \
  --acceptance-file examples/workflow-v3/acceptance.json \
  --timeout 8h
```

## Job states and acceptance

| State | Meaning |
| --- | --- |
| `RUNNING` | The detached worker is active, or state has not yet been reconciled. |
| `SUCCESS` | The guard completed the run (process exit `0`, or a confirmed session completion stopped a hung CLI), every required criterion verified, and no unresolved blocking/failure detector fired. |
| `FAILED` | A required criterion failed, an unresolved failure detector fired, or the process exited non-zero. |
| `BLOCKED` | The guard refused, an unresolved permission/dependency/marker blocked the run, or manual acceptance is pending. |
| `TIMEOUT` | The guard reached the wall-clock limit (exit code `124`). |

`SUCCESS` is computed from evidence, not from the OpenCode exit code alone. A
run that exits `0` but fails an acceptance command, reports an incomplete
implementation, or leaves a permission denial unresolved is `FAILED` or
`BLOCKED`.

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

Recovered issues remain visible in `dev status` and `report.md` with recovery
evidence. The context-aware log fallback cannot prove recovery, so it stays
conservative and treats a permission rejection as blocking.

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
dev resume <job-id> --new-session     # only when the original session is unknown
dev resume <job-id> --force           # re-run an already successful job
```

Resume reuses the same job directory, repository/worktree and OpenCode session
(`opencode run --session <id>`). It appends a new attempt and never runs Git
reset, clean, stash or checkout. If the session ID is unknown, resume refuses to
attach to a random session unless `--new-session` is explicitly requested.

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
  "events": ["SUCCESS", "FAILED", "BLOCKED", "TIMEOUT"],
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
  recoverable handoff. Do not signal Qortium or any process by name.
- To stop new work, wait for the current job or interrupt the guard only inside
  the job it owns. Do not use `pkill`, `killall` or `tmux kill-server`.

## Tests

```bash
python3 tools/test_opencode_guard.py
python3 tools/test_dev_cli.py
python3 tools/test_agent_permissions.py
python3 tools/test_install_profiles.py
python3 tools/test_detect.py
python3 tools/test_session_lifecycle.py
python3 tools/validate_agent_permissions.py --check
python3 tools/validate_control_plane.py
python3 tools/validate_skills.py
python3 tools/validate_security.py .
```

The CLI tests use a disposable fake `opencode` executable and a synthetic procfs
root, including a hung-CLI-after-`finish=stop` regression case. They include
recovered and unresolved permission rejections, recovered same-operation command
failures and unrelated successful commands that must not clear a failure. The
detection tests include the actual documentation, source/diff and failed-tool log
examples from the permissions job, plus the recovered/unresolved structured-event
matrix. `test_session_lifecycle.py` covers structured completion evidence,
active-tool safety, attempt scoping and total-vs-attempt duration reporting. The
permission tests parse the agent Markdown and exercise the last-match wildcard
model, approved tooling roots, exact directory-root matching, Qortium diagnostics
and hard boundaries; they also record the known wrapper/script limitations. They
do not start a model session, contact Telegram or touch Qortium.

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
- resume depends on OpenCode session history remaining in its SQLite store.
