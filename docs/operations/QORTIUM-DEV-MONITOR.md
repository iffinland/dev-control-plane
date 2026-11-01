# Qortium Dev Monitor — P4 operations and activation

Status: **P1 read-only observer, P2 authorized control, P3 cancellation plus
queued owner messaging and P4 hardening are implemented. Default mode remains
`read_only`; owner activation is manual.** A production systemd user unit is
stored in this repository. This task did not install, enable, restart or start
it, and it did not modify the owner-local `telegram.json`.

This runbook covers the Phase P4 Telegram control surface described in the
[Qortium Dev Monitor architecture](QORTIUM-DEV-MONITOR-ARCHITECTURE.md). P4 adds
detector-classification regression fixes, lifecycle-notification redaction,
per-user and per-chat rate limits, an hourly start cap, atomic one-time
confirmation claims, job-directory symlink resistance, comprehensive
fault-injection tests and the
[real-runtime owner acceptance checklist](QORTIUM-DEV-MONITOR-P4-ACCEPTANCE.md).
It preserves the P1 read-only surface, P2 start/resume control, P3 cancel and
queued instructions, per-project admission, notification deduplication and every
security boundary.

## 1. What the monitor provides

Read-only mode (the default):

- Authorized private-chat Telegram access using numeric user and chat IDs.
- Main menu, job list, job status, project list and document browser.
- Bounded, redacted run/worker log and report previews.
- Read-only report/log downloads and allowlisted document downloads.
- Persistent polling offsets, update deduplication, opaque callback references,
  rate limiting and a sanitized SQLite audit trail.

Control mode (explicit owner configuration only):

- Registered-project selection for job start.
- Start wizard: title, prompt, mandatory acceptance criteria, timeout, optional
  branch label, exact confirmation preview and one-time confirmation.
- Fixed-shape `dev start` invocation with `--no-notify --json` and the prompt on
  standard input. The monitor never passes `--contract-file` or an authorization
  weakening flag: every monitor-started job receives the CLI's mandatory default
  completion contract. Push, protected-branch and merge authorization therefore
  remain separate owner decisions; without them a completed job is truthfully
  reported as `BLOCKED`, not `SUCCESS`.
- Resume wizard with optional instruction, explicit `--new-session`/`--force`
  toggles and one-time confirmation.
- Per-project admission locking plus global execution-guard awareness. Only one
  active monitor-managed job is admitted per project, and a running job anywhere
  is reported as global-guard busy rather than starting a doomed attempt.
- STARTED and RESUMED notifications, plus terminal relays for monitor-started
  jobs, with durable at-most-once deduplication.
- Verified cancellation of a RUNNING job through the additive `dev cancel`
  command, with a one-time confirmation, durable `CANCELLED` state and preserved
  worktree/session.
- Persistent owner instruction queue. Instructions are stored with explicit
  `queued`/`delivered` state, shown in status, and delivered exactly once per
  successful resume through `dev resume --prompt-file -`.
- Explicit New session confirmation when a job has no known OpenCode session.
- Optional local unlock passphrase using a salted scrypt hash.
- P4 controls: per-user and per-chat action rate limits, an hourly start cap,
  lifecycle-notification redaction, atomic single-use confirmations and a
  symlink-resistant job artifact boundary.

The monitor reuses the existing Workflow v3 job store and CLI plus the existing
owner-local Telegram configuration. It is not a second job manager, scheduler or
job engine.

## 2. Safety boundaries

The monitor:

- runs as an owner-controlled foreground process or an owner-installed systemd
  user service and refuses a second instance through an exclusive state lock;
- never calls `setWebhook`, opens a listener or exposes an inbound API;
- invokes only allowlisted Workflow v3 commands:
  `dev start`, `dev resume`, `dev cancel`, `dev status`, `dev report` and
  `dev logs`;
- cancels only through `dev cancel`, which revalidates the exact guard process
  identity and sends `SIGTERM` to that PID only. The monitor itself never signals
  a process and never uses a name-based kill;
- never injects text into a running OpenCode turn. Owner instructions are queued
  durably and delivered on the next resume;
- never runs `sudo`, a service manager, a package manager or a mount command;
- never restarts, stops, reconfigures, signals or writes the Qortium node, its
  service, data or logs;
- never sends a transaction, publishes to QDN or modifies a wallet;
- reads logs and reports only from validated job directories and named artifacts;
- reads documents only below explicitly configured roots using descriptor walks
  with `O_NOFOLLOW`, regular files only and size caps;
- applies credential redaction before every outbound message, text download and
  audit detail;
- records timing labels and durations only. It never writes message text, prompts,
  passphrases, paths, user/chat IDs, tokens or exception messages into timing
  diagnostics.

## 3. Prerequisites

- Python 3.11+ (the verified environment uses Python 3.13).
- The control-plane checkout at `/home/iffi/dev-workspace/control-plane`.
- An owner-created Telegram bot and its token, stored outside Git.
- The owner's numeric Telegram user ID and private chat ID.
- Existing Workflow v3 state, normally under
  `$DEV_CONTROL_PLANE_STATE` or `~/.local/state/dev-control-plane`.
- Registered project repositories under an allowed repository root.
- Read access to the central docs tree.
- For the systemd user service: login linger is already enabled by the owner
  (`Linger=yes`). Verify with `loginctl show-user "$USER" -p Linger` if needed.

No new package install, system service, firewall rule, port or Qortium change is
required.

## 4. Configuration

Reuse `~/.config/dev-control-plane/telegram.json` so the token is not duplicated.
The existing Workflow v3 notification loader ignores the nested `monitor` object.
The monitor reads it and never rewrites it.

Example shape (placeholders only; never commit real values):

```json
{
  "enabled": true,
  "bot_token": "<owner-local token>",
  "chat_id": "<owner-local chat ID>",
  "events": ["SUCCESS", "FAILED", "BLOCKED", "TIMEOUT", "CANCELLED"],
  "timeout_seconds": 10,
  "monitor": {
    "mode": "read_only",
    "authorized_user_ids": [123456789],
    "allowed_chat_ids": [123456789],
    "require_private_chat": true,
    "poll_timeout_seconds": 25,
    "request_timeout_seconds": 10,
    "document_timeout_seconds": 60,
    "slow_timing_seconds": 1.0,
    "status_refresh_seconds": 30,
    "max_inline_chars": 3500,
    "max_actions_per_minute": 30,
    "max_actions_per_chat_per_minute": 60,
    "max_starts_per_hour": 6,
    "max_text_download_bytes": 2097152,
    "max_binary_download_bytes": 10485760,
    "allow_binary_downloads": false,
    "relay_external_final": true,
    "queue_owner_messages": true,
    "owner_message_max_chars": 4000,
    "owner_message_retention_seconds": 2592000,
    "unlock_ttl_seconds": 900,
    "admission_lock_timeout_seconds": 5,
    "lifecycle_poll_seconds": 30,
    "terminal_grace_seconds": 20,
    "control_passphrase_hash": "<optional owner-local scrypt hash>",
    "allowed_repo_roots": [
      "/home/iffi/dev-workspace/projects",
      "/home/iffi/dev-workspace/control-plane"
    ],
    "docs_roots": [
      "/home/iffi/dev-workspace/docs/workspace",
      "/home/iffi/dev-workspace/docs/references",
      "/home/iffi/dev-workspace/control-plane/docs"
    ],
    "agent_allowlist": ["opencode-development"],
    "model_allowlist": ["deepseek/deepseek-flash"]
  }
}
```

To enable control, change only `mode` to `"control"`. Control mode additionally
requires non-empty `agent_allowlist` and `model_allowlist`. The monitor refuses
to start with an invalid control configuration.

Generate the optional passphrase hash locally without echo:

```bash
python3 /home/iffi/dev-workspace/control-plane/tools/dev_monitor.py hash-passphrase
```

Paste only the printed `scrypt$...` value into `control_passphrase_hash`. The
passphrase itself must never appear in Git, monitor state, audit rows or chat.
Unlock state is held in memory for `unlock_ttl_seconds` and is cleared on monitor
restart or `/lock`.

Timeouts and control limits:

| Setting | Default | Meaning |
| --- | --- | --- |
| `poll_timeout_seconds` | `25` | Telegram `getUpdates` long-poll timeout. |
| `request_timeout_seconds` | `10` | Ordinary Bot API calls, separate from long polling. |
| `document_timeout_seconds` | `60` | `sendDocument` uploads. |
| `slow_timing_seconds` | `1.0` | A measured operation at or above this duration is logged as `timing slow`. |
| `max_actions_per_minute` | `30` | Per-user action budget in a rolling minute. |
| `max_actions_per_chat_per_minute` | `60` | Per-chat action budget, covering every authorized user in that chat. |
| `max_starts_per_hour` | `6` | Maximum admitted monitor-started jobs per rolling hour. |
| `unlock_ttl_seconds` | `900` | In-process control unlock window. |
| `admission_lock_timeout_seconds` | `5` | Per-project check-and-invoke lock wait. |
| `lifecycle_poll_seconds` | `30` | Minimum interval between lifecycle event scans. |
| `terminal_grace_seconds` | `20` | Wait before relaying an external terminal state with no notification record. |
| `queue_owner_messages` | `true` | Enable the durable owner instruction queue. |
| `owner_message_max_chars` | `4000` | Maximum length of one queued owner instruction. |
| `owner_message_retention_seconds` | `2592000` | Delete delivered instructions after 30 days. Queued instructions are never expired automatically. |

Permissions:

```bash
install -d -m 0700 ~/.config/dev-control-plane
chmod 600 ~/.config/dev-control-plane/telegram.json
```

The monitor refuses to start when the file is group/world accessible or when the
nested `monitor` object, token, numeric user allowlist or numeric chat allowlist is
missing. `require_private_chat` must remain `true`.

`docs_roots` is an explicit allowlist. Registered project report roots are added
automatically from [PROJECT-REGISTRY.md](../../PROJECT-REGISTRY.md) when they
exist. The whole central docs directory is never exposed as a generic root.

## 5. Activation

These steps are intentionally manual. Choose either the systemd user service
(recommended for normal use) or an owner-controlled foreground terminal. Do not
run both at the same time; the single-instance lock refuses the second process.

### 5.1 Preflight

Run the read-only check first:

```bash
python3 /home/iffi/dev-workspace/control-plane/tools/dev_monitor.py check
```

This validates config permissions, numeric allowlists, control configuration,
`getMe`, the webhook state, the project registry, document roots and monitor
state permissions. It does not start polling and it never clears a webhook
silently.

### 5.2 Switch to control (only when intended)

1. Back up the owner-local config outside Git and keep it mode `0600`.
2. Set `monitor.mode` to `"control"`.
3. Confirm `agent_allowlist` and `model_allowlist` contain only intended values.
4. Optionally add `control_passphrase_hash` from `hash-passphrase`.
5. Run `dev_monitor.py check` again.
6. Restart the monitor so the new configuration is loaded.

To return to a pure observer, set `mode` back to `"read_only"` and restart the
monitor. Running jobs are unaffected.

### 5.3 Install and activate the systemd user service

The unit is stored in this repository as
`deploy/systemd/user/qortium-dev-monitor.service`. It is not installed by the
repository and it was not enabled or started during implementation.

```bash
# Create the user unit directory if it does not exist.
install -d -m 0700 ~/.config/systemd/user

# Copy the repository unit into the owner's user unit directory.
install -m 0644 \
  /home/iffi/dev-workspace/control-plane/deploy/systemd/user/qortium-dev-monitor.service \
  ~/.config/systemd/user/qortium-dev-monitor.service

# Reload the user manager, then enable and start the service.
systemctl --user daemon-reload
systemctl --user enable --now qortium-dev-monitor.service
```

The owner already enabled login linger, so the user manager keeps running after
logout. Verify if needed:

```bash
loginctl show-user "$USER" -p Linger
```

The unit sets:

- `WorkingDirectory=/home/iffi/dev-workspace/control-plane`;
- `ExecStart=/usr/bin/python3 .../tools/dev_monitor.py run`;
- `Restart=on-failure` with a 5 second delay and a start limit of 5 attempts per
  5 minutes;
- `RestartPreventExitStatus=2 75 78` so configuration errors, a duplicate
  instance and fatal Telegram auth/conflict errors do not create a restart loop;
- `KillSignal=SIGTERM`, `KillMode=mixed` and `TimeoutStopSec=40` for graceful
  shutdown;
- `UMask=0077`, `NoNewPrivileges=true` and `PrivateTmp=true`.

The monitor handles `SIGTERM`/`SIGINT` by stopping the polling loop, releasing the
single-instance lock and exiting with status `0`. Running Workflow v3 jobs are
detached and are not affected.

### 5.4 Foreground alternative

If the service is not used, start the monitor in an owner-controlled terminal:

```bash
python3 /home/iffi/dev-workspace/control-plane/tools/dev_monitor.py run
```

Stop it with `Ctrl-C`, or from another terminal:

```bash
python3 /home/iffi/dev-workspace/control-plane/tools/dev_monitor.py stop
```

### 5.5 Service status, logs and lifecycle

```bash
# Current service state.
systemctl --user status qortium-dev-monitor.service --no-pager

# Recent output (includes timing diagnostics).
journalctl --user -u qortium-dev-monitor.service -n 100 --no-pager

# Follow live output.
journalctl --user -u qortium-dev-monitor.service -f

# Only slow-operation and periodic timing lines.
journalctl --user -u qortium-dev-monitor.service -n 500 --no-pager | grep 'timing '

# Restart, stop and disable.
systemctl --user restart qortium-dev-monitor.service
systemctl --user stop qortium-dev-monitor.service
systemctl --user disable qortium-dev-monitor.service

# Monitor state and lock status.
python3 /home/iffi/dev-workspace/control-plane/tools/dev_monitor.py status
python3 /home/iffi/dev-workspace/control-plane/tools/dev_monitor.py status --json
```

`systemctl --user stop` is the normal service stop. The monitor's flag-file
`stop` command remains available for foreground operation. Both paths are
graceful; neither signals the Qortium node or Workflow v3 workers.

### 5.6 First owner verification

From the authorized private chat, send `/start`, `/jobs`, `/projects` and
`/docs`. Verify that unauthorized accounts receive only a generic denial. Open a
job, preview a report and browse a document.

If control mode is enabled:

1. Send `/start_job` and select a registered project.
2. Complete the wizard with a small prompt and at least one acceptance criterion.
3. Inspect the confirmation preview; press Confirm.
4. Verify that STARTED arrives once and the job appears in `/jobs`.
5. Open the job, choose Resume after it reaches a terminal state, inspect the
   preview, press Confirm resume and then Confirm.
6. Verify RESUMED arrives once and the same job ID/session is used.

Running jobs remain independent of the monitor lifecycle.

### 5.7 Run exit codes

| Code | Meaning | Service restart |
| --- | --- | --- |
| `0` | Graceful signal/flag stop. | No |
| `1` | Unexpected or non-fatal top-level failure. | Yes, bounded by start limit |
| `2` | Configuration or usage error. | No |
| `75` | Another monitor instance owns the single-instance lock. | No |
| `78` | Fatal Telegram auth/conflict error (`401`, `403`, `409`). | No |

## 6. Commands, menus and control flows

| Command | Result |
| --- | --- |
| `/start`, `/menu` | Main menu (Start job is shown only in control mode) |
| `/start_job`, `/newjob` | Start wizard for a registered project with an available repository and a valid delivery policy |
| `/jobs` | Active jobs first, then recent terminal jobs |
| `/job <reference>` | Open a job by server-side reference |
| `/status [job]` | Compact status view; latest job when omitted |
| `/resume [job]` | Resume wizard (control mode) |
| `/cancel [job]` | With no job: cancel the active wizard. With a job: verified running-job cancel flow (control mode) |
| `/queue [job]` | Queue an owner instruction for the next resume (control mode) |
| `/messages [job]` | Show queued and delivered owner instructions with delivery state |
| `/projects` | Registered projects, repository/docs availability and eligibility |
| `/docs` | Allowlisted document roots |
| `/unlock <passphrase>` | Unlock control actions when a passphrase hash is configured |
| `/lock` | Re-lock control actions |
| `/help` | Commands, active mode and safety notes |

Job actions are Refresh, Run log, Worker log, Report, Download report and, in
control mode, Resume for a resumable job, Cancel job for a RUNNING job with a live
worker, and Queue instruction for any job. Document actions are open directory,
preview text, download a redacted text copy and, only when explicitly enabled, a
confirmed binary download. Callback data contains opaque server-side references,
never paths, job IDs, prompts or user IDs.

### 6.1 Start flow

```text
/start_job
-> select registered project (server-side index)
-> title
-> prompt
-> at least one criterion: "Label::command" or "manual: text"
-> timeout (8h maximum)
-> optional branch label or /skip
-> exact confirmation preview
-> one-time Confirm
-> per-project admission lock
-> project-active and global-guard check
-> validate the project's delivery policy (Git remote, matching GitHub
   repository, agent/* branch pattern, explicit automatic-push flag)
-> dev start --project <id> --registry <path> --no-notify --json
   (prompt over stdin; no --authorize-push and no remote override)
   -> validated policy and mandatory default completion contract recorded in job.json
-> RUNNING: STARTED notification and job actions
-> BLOCKED/refusal: sanitized reason, no STARTED
```

The monitor and direct `dev start` calls resolve the same policy from
[PROJECT-REGISTRY.md](../../PROJECT-REGISTRY.md). A missing, ambiguous,
non-GitHub or mismatched remote is refused; the monitor never selects
`dev-control-plane` for a different project and never weakens the mandatory push
check. Automatic push covers only matching non-protected `agent/*` branches.

Job status includes the completion-contract state and any failed or pending
check. A green build, a passing test suite or an OpenCode exit `0` is never
reported as `SUCCESS` when task-start evidence, the scoped commit, the
authorized development-branch push or the verified remote SHA is missing.

The monitor uses only the configured agent/model allowlists, a registered
repository realpath, an integer timeout capped at eight hours and argument arrays
with `shell=False`. Acceptance commands remain the one intentional shell surface:
Workflow v3 runs them with `bash` in the selected repository, and the preview
shows them before confirmation.

### 6.2 Resume flow

```text
job view -> Resume
-> preview: current state, attempt, session, blocker, options
-> optional instruction (composed and passed over stdin)
-> optional explicit New session or Force rerun toggle
-> one-time Confirm
-> per-project admission and global-guard check
-> compose base instruction + queued owner messages
-> dev resume <job-id> --prompt-file - --json (instruction over stdin)
-> RUNNING: RESUMED notification, queued messages marked delivered, same job view
```

A live RUNNING job is refused. A SUCCESS job requires the explicit Force rerun
toggle. An unknown session requires the explicit New session toggle. `--force`
and `--new-session` are never added silently. The composed instruction is passed
over standard input, not the process argument list. Queued messages are marked
delivered only after Workflow v3 accepts the resume; a failed resume keeps them
queued.

### 6.3 Cancel flow

```text
job view -> Cancel job (only RUNNING with a live worker)
-> preview: exact job, attempt, worker/guard PIDs, safety explanation
-> one-time Confirm
-> per-project admission lock
-> dev cancel <job-id> --json
-> Workflow v3 re-verifies /proc/<guard-pid>/cmdline
-> durable cancel.requested.json + cancel_requested event
-> SIGTERM to that exact guard PID only
-> guard stops only its created child process group
-> CANCELLED, acceptance commands skipped, worktree and session preserved
-> Resume remains available
```

The monitor never sends a signal itself and never escalates to a name-based kill.
If the guard survives the bounded grace period, Workflow v3 reports
`cancel_status: pending` and the monitor shows that result. A terminal job cannot
be cancelled. If the worker has already disappeared, Workflow v3 reconciles the
job without sending a signal.

### 6.4 Queued owner instructions

- `Queue instruction` or `/queue [job]` stores one text instruction in monitor
  SQLite with `delivery_state=queued`.
- While the job is RUNNING the UI states explicitly that delivery happens on the
  next resume, not live.
- `Resume` preview lists pending instructions. Confirm shows how many will be
  included.
- The composed prompt contains the owner's base instruction plus a clearly
  delimited owner-follow-up block and the instruction to preserve the working
  tree and not expand scope.
- On a successful resume each included message becomes `delivered` with a
  `delivered_attempt`; a second resume does not include it again.
- A failed or refused resume leaves the messages `queued` and records a short
  redacted error.
- `/messages [job]` shows queued and delivered instructions and their delivery
  attempts. Delivered instructions are pruned after the configured retention.
- A job with no known OpenCode session still requires the explicit New session
  toggle; queued instructions do not bypass that safety rule.

### 6.5 Notifications and deduplication

- STARTED is sent on the first worker/attempt start.
- RESUMED is sent on `resume_requested` or a resumed attempt, once per resume
  count.
- Terminal notifications, including `CANCELLED`, are sent once per
  job/state/attempt.
- Monitor-started jobs use `--no-notify`; the monitor sends their terminal relay.
- CLI-started jobs keep the existing Workflow v3 terminal notification as
  authoritative. The monitor does not duplicate a sent notification and does not
  silently retry a failed one.
- Notification keys are claimed in durable monitor state before sending, so a
  restart, replayed event or duplicate callback cannot resend the same message.
- Historical terminal jobs older than one hour are not replayed when the monitor
  state is first initialized.

## 7. State and diagnostics

Monitor state is private and separate from job state:

```text
<Workflow state root>/monitor/monitor.db          # SQLite, mode 0600, WAL mode
<Workflow state root>/monitor/monitor.lock        # single-instance lock
<Workflow state root>/monitor/monitor.stop        # graceful stop flag
<Workflow state root>/monitor/locks/              # per-project admission locks
```

P2 adds durable tables for wizards, notification deduplication and lifecycle
event cursors. P3 adds `owner_messages` with explicit `queued`/`delivered` state,
`delivered_at`, `delivered_attempt` and a short redacted error. P4 uses the
`rate_limits` table for per-user, per-chat and hourly-start budgets and claims
confirmation nonces atomically. Owner instructions are private monitor state;
they are never written to the audit table.

Use `DEV_MONITOR_STATE` to override the monitor state directory and
`--state-dir` on the CLI for a one-off override. Deleting monitor state resets UI
state, wizards and notification cursors only; Workflow v3 jobs are unaffected.

Diagnostics:

```bash
python3 tools/dev_monitor.py status
python3 tools/dev_monitor.py status --json
python3 tools/dev_monitor.py check
```

The audit table stores the timestamp, numeric user/chat/update IDs, action, job
ID, result and a short redacted detail. It never stores message bodies, prompts,
passphrases, logs, tokens or environment variables.

### 7.1 Timing diagnostics

Timing data is kept in memory, bounded, and written only to the service logger
(the systemd journal when running as a service). No timing row is added to
SQLite, so diagnostics do not increase state write pressure.

Labels describe stable operations, not user content:

| Label | Area |
| --- | --- |
| `poll:getUpdates` | Long-poll request and wait |
| `ack:batch` | Callback acknowledgement pass for a polling batch |
| `telegram:*` | Individual Bot API calls |
| `update:message`, `update:callback_query` | Per-update dispatch |
| `action:command:<name>`, `action:callback:<head>` | Menu action handling, using a fixed allowlist of command/button names |
| `action:wizard:text` | Wizard text-step validation |
| `cli:dev_status`, `cli:dev_report`, `cli:dev_start`, `cli:dev_resume` | Synchronous Workflow v3 CLI subprocess |
| `admission:check_and_invoke` | Per-project check-and-invoke critical section |
| `lifecycle:poll` | STARTED/RESUMED/terminal event scan |
| `docs:list`, `docs:preview`, `docs:download` | Descriptor-based document access |
| `sqlite:*` | Monitor state writes and reads |

A sample slow-event line:

```text
monitor: timing slow label=telegram:editMessageText duration_ms=2140.7 outcome=ok
```

A periodic summary is emitted every 60 seconds or 200 samples, whichever comes
first:

```text
monitor: timing summary samples=214 slow=3 top=telegram:getUpdates=avg25010.2ms/max25112.0ms/n=12, ...
```

These lines contain no token, chat ID, message content, path or exception text.
Use them to distinguish the actual bottleneck:

- `telegram:*` slow points at network/API latency.
- `cli:*` slow points at synchronous Workflow v3 subprocess cost.
- `admission:*` slow points at lock contention.
- `lifecycle:*` slow points at job event-store reads.
- `docs:*` slow points at a large or slow document directory.
- `sqlite:*` slow points at state storage.
- `poll:getUpdates` near the configured long-poll timeout is normal when no
  update arrived.

SQLite uses WAL mode and `synchronous=NORMAL` so the owner's read-only `status`
command does not block the monitor writer. The polling offset and last-poll time
are written in one transaction instead of two separate commits.

## 8. Troubleshooting

| Symptom | Action |
| --- | --- |
| `409 Conflict` | Another poller or webhook is active. Stop the other poller or clear the webhook explicitly; never leave two pollers running. |
| `401 Unauthorized` | Correct the owner-local token; never print it into chat, logs or Git. The service does not restart on this exit code. |
| Config refused | Set mode `0600`, add non-empty numeric user/chat allowlists, and in control mode add non-empty agent/model allowlists. |
| Control action refused | The monitor is read-only, or a passphrase is configured and the chat has not run `/unlock`. |
| Start refused: project busy | A job is running in that project. Wait for it to finish and start again. The monitor queues owner instructions for a job, not new starts; there is no scheduler. |
| Start refused: global guard busy | Another heavyweight execution is running. The existing guard allows one at a time; wait for it to finish. |
| Start refused: BLOCKED | Workflow v3 guard preflight refused. Read the sanitized blocker; no STARTED is sent. |
| Resume refused: live RUNNING | The job has a live worker. Inspect it instead of starting a duplicate attempt. |
| Resume refused: unknown session | Enable the explicit New session toggle after confirming session continuity is being abandoned. |
| Resume refused: already SUCCESS | Enable the explicit Force rerun toggle only if another attempt is intended. |
| Duplicate STARTED/RESUMED | Inspect `event_cursors` and `notification_log`; delete monitor state only, never job state. |
| Service does not start | Run `systemctl --user status ...` and `journalctl --user -u ... -n 100 --no-pager`; then run `dev_monitor.py check`. |
| `75` duplicate instance | Stop the foreground monitor or the other service instance first. Only one process may hold the lock. |
| No updates | Check `dev_monitor.py check`, confirm the bot was started, and inspect the stored offset with `dev_monitor.py status`. |
| Menu feels slow | Search the journal for `timing slow` and read the label. Compare `telegram:*`, `cli:*`, `admission:*`, `lifecycle:*`, `docs:*` and `sqlite:*` lines before changing anything. |
| Status is stale | Workflow v3 status reconciles a missing worker; refresh the job view. |
| Document refused | Absolute paths, `..`, backslashes, percent encodings, hidden names, symlinks and sensitive names are refused by design. |
| Cancel refused | The job is not RUNNING with a live worker, or the guard identity no longer matches. Inspect `/status`; never signal by name. |
| Cancel pending | Workflow v3 sent SIGTERM to the verified guard but it survived the grace period. No escalation is attempted; inspect status or retry `/cancel <job>`. |
| Instruction is not live | Queued instructions are delivered only on the next resume by design. Open Resume to deliver them. |
| Queued instruction remains queued | The resume was refused or failed. Fix the refusal and resume again; the queue is preserved. |
| `Rate limit exceeded` | The per-user or per-chat action budget was reached. Wait for the rolling minute to pass; do not raise the limit just to bypass an unexpected burst. |
| `start rate limit reached` | The hourly monitor-start cap was reached. Wait, or change `max_starts_per_hour` deliberately and restart the monitor. |

## 9. Validation

The P1-P4 tests use fake Telegram transports, an isolated fake `dev` CLI and
test-owned child processes. They never contact production Telegram and never
start a real OpenCode session:

```bash
python3 tools/test_dev_monitor_redact.py
python3 tools/test_dev_monitor_auth.py
python3 tools/test_dev_monitor_projects.py
python3 tools/test_dev_monitor_documents.py
python3 tools/test_dev_monitor_jobs.py
python3 tools/test_dev_monitor_api.py
python3 tools/test_dev_monitor_state.py
python3 tools/test_dev_monitor_timings.py
python3 tools/test_dev_monitor_service_unit.py
python3 tools/test_dev_monitor_admission.py
python3 tools/test_dev_monitor_lifecycle.py
python3 tools/test_dev_monitor_control.py
python3 tools/test_dev_monitor_p3.py
python3 tools/test_dev_monitor_integration.py
python3 tools/test_dev_monitor_p4.py
python3 tools/test_dev_cancel.py
```

The P4 suite adds isolated authorization/replay/rate-limit tests, trusted-root
document fuzzing, symlink-swap and special-file tests, cross-boundary redaction
checks, restart persistence, Telegram polling fault injection, notification
dedupe after restart, atomic confirmation claims and a fake-CLI
start/queue/cancel/resume integration flow. It also contains the detector
regression that keeps a `FileNotFoundError` for a test fixture from being
classified as `missing_dependency` while real missing commands/modules remain
blocking.

The complete automated gate is:

```bash
python3 -m unittest discover -s tools -p 'test_*.py' -q
python3 tools/validate_control_plane.py
python3 tools/validate_skills.py
python3 tools/validate_security.py --self-test
python3 tools/validate_security.py .
python3 tools/validate_agent_permissions.py --check
```

The P4 tests use fake Telegram transports, a fake `dev` CLI, test-owned child
processes and isolated temporary state. No test contacts production Telegram,
starts a real OpenCode session, cancels a live job or signals a Qortium process.

The unit can be syntax-checked without installing it:

```bash
systemd-analyze verify deploy/systemd/user/qortium-dev-monitor.service
```

## 10. Deferred to later phases

- P4 real-runtime acceptance remains pending until the owner executes the
  [owner acceptance checklist](QORTIUM-DEV-MONITOR-P4-ACCEPTANCE.md). Automated
  hardening, detector corrections and fault-injection tests are implemented.
- P5: optional read-only latest assistant message, richer queues and search.

P4 does not expose manual acceptance, live prompt injection, arbitrary process
signals or scheduler behaviour. OpenCode exit code 0 is never treated as
acceptance; Workflow v3 criteria remain authoritative.

## 11. P4 owner acceptance

Use the dedicated
[real-runtime owner acceptance checklist](QORTIUM-DEV-MONITOR-P4-ACCEPTANCE.md).
It expands the P3 cancel/queue smoke checks into R-01 through R-16 and covers
authorization, replay, redaction, traversal/symlink resistance, restart
persistence, polling fault recovery, token rotation and the no-listener /
no-Qortium-change invariant.

The P3 smoke path still applies inside that checklist:

1. Confirm `dev cancel` refuses a completed job:
   `python3 tools/dev.py cancel <terminal-job-id>` returns a sanitized error and
   sends no signal.
2. Start a small control-mode job from Telegram. Open the job and verify
   `Cancel job` and `Queue instruction` appear only while permitted.
3. Queue an instruction while the job is RUNNING. The reply must say it will be
   delivered on the next resume, not live.
4. Cancel the job from the job view. Confirm that only that job's guard stops,
   `CANCELLED` is shown once, and the working tree is unchanged.
5. Resume the cancelled job. The preview must list the queued instruction; the
   confirmation must show it included. After resume, `/messages <job>` must show
   it as delivered at the new attempt.
6. Cause a second failed or refused resume and verify any newly queued
   instruction stays queued rather than being lost.
7. Resume a job whose OpenCode session ID is unknown. Workflow v3 and the monitor
   must refuse until the owner explicitly enables New session.
8. Restart the monitor during a running job. The job must continue, and no
   duplicate STARTED/RESUMED/terminal notification may be sent.

## 12. Incident response and credential rotation

### 12.1 Telegram account or token compromise

1. Remove the affected numeric user ID or chat ID from the owner-local config.
2. Rotate the bot token with BotFather and update
   `~/.config/dev-control-plane/telegram.json` at mode `0600`.
3. Restart the monitor through its documented path, then run
   `dev_monitor.py check` and confirm no webhook is configured.
4. Review the sanitized audit rows (`action`, `result`, numeric IDs and job ID
   only). Do not paste message bodies, prompts or tokens into a report.
5. Inspect affected jobs with `dev status`. Cancel only through the verified
   `dev cancel` flow and only a job the owner intends to stop.
6. Do not modify Qortium, VPS networking, mounts, packages or system services
   during incident response.

### 12.2 Suspected secret exposure

1. Rotate the exposed credential at its source first.
2. Search job logs, reports, monitor audit rows and documentation for the
   redacted marker and the original value. Do not copy the value into a report.
3. Fix the source, add a redaction regression fixture, and run
   `python3 tools/test_dev_monitor_p4.py` and
   `python3 tools/test_dev_monitor_redact.py`.
4. Record a sanitized incident note under the central workspace validation tree.

### 12.3 Lost or stolen device

1. Revoke the Telegram session externally and remove the device.
2. Remove the user/chat IDs from config and rotate the bot token.
3. Review jobs and monitor state; preserve evidence before deleting anything.
4. Delete only monitor state if necessary. Never delete or rewrite Workflow v3
   job state to hide an incident.

### 12.4 Telegram outage, `401`, `409` or repeated `429`

| Symptom | Action |
| --- | --- |
| `401`/`403` | Treat as fatal configuration/auth failure. Fix the owner-local token; the service exits `78` and does not hot-loop. |
| `409 Conflict` | Another poller or a webhook is active. Stop the other poller or clear the webhook explicitly; never run two pollers. |
| Repeated `429` | Honor `retry_after`, confirm only one monitor instance holds the lock, and inspect for a duplicate poller. |
| Timeouts / `5xx` | The monitor backs off with jitter and keeps the offset unmoved, so the unhandled update is retried. |
| Service crash loop | Run `check`, inspect the journal, and verify the single-instance lock. Do not use a name-based kill. |

### 12.5 Monitor or state corruption

1. Stop the monitor through the flag/service path.
2. Back up the private state directory if evidence is needed.
3. Delete only the monitor database, lock or stop flag. Workflow v3 job state is
   separate and must not be deleted.
4. Start the monitor and run `check`; confirm jobs are still visible.
5. Never modify `/home/iffi/qortium-preview/**`, `/home/iffi/qortium-data/**` or
   the Qortium service as part of monitor recovery.

### 12.6 Routine rotation and upgrade

1. Run the full automated gate before deploying new monitor code.
2. Stop the monitor, update the repository, run `check`, then start it again.
   Running jobs are detached and unaffected.
3. Rotate a token only while the monitor is stopped; verify the new identity with
   `check` before resuming polling.
4. Keep `allow_binary_downloads` false unless a separate owner decision and
   per-file confirmation policy is in place.
5. Leave `auto_start_queued` false; the monitor is not a scheduler.
