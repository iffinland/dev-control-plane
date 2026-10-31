# Qortium Dev Monitor — P1 operations and activation

Status: **P1 read-only observer implemented. Owner activation is manual.** A
production systemd user unit is stored in this repository. This task did not
install, enable or start it.

This runbook covers the Phase P1 read-only Telegram observer described in the
[Qortium Dev Monitor architecture](QORTIUM-DEV-MONITOR-ARCHITECTURE.md). P1 does
not start, resume, cancel or accept jobs, and it does not modify Workflow v3,
Qortium, the running node or VPS system configuration.

## 1. What P1 provides

- Authorized private-chat Telegram access using numeric user and chat IDs.
- Main menu, job list, job status, project list and document browser.
- Bounded, redacted run/worker log and report previews.
- Read-only report/log downloads and allowlisted document downloads.
- Persistent polling offsets, update deduplication, opaque callback references,
  rate limiting and a sanitized SQLite audit trail.
- Outbound-only Telegram long polling. There is no webhook, public port or HTTP
  server.
- Bounded timing diagnostics for polling, callback acknowledgement, Telegram
  calls, the Workflow v3 CLI, SQLite and document browsing. Diagnostics contain
  operation labels and durations only, never message bodies or credentials.
- An optional systemd user unit with automatic restart, duplicate-instance
  protection, a fixed working directory and graceful `SIGTERM` shutdown.

It reuses the existing Workflow v3 job store and CLI plus the existing owner-local
Telegram configuration. It is not a second job manager.

## 2. Safety boundaries

The monitor:

- runs as an owner-controlled foreground process or an owner-installed systemd
  user service and refuses a second instance through an exclusive state lock;
- never calls `setWebhook`, opens a listener or exposes an inbound API;
- never creates or mutates Workflow v3 jobs in P1;
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
  paths, user/chat IDs, tokens or exception messages into timing diagnostics.

## 3. Prerequisites

- Python 3.11+ (the verified environment uses Python 3.13).
- The control-plane checkout at `/home/iffi/dev-workspace/control-plane`.
- An owner-created Telegram bot and its token, stored outside Git.
- The owner's numeric Telegram user ID and private chat ID.
- Existing Workflow v3 state, normally under
  `$DEV_CONTROL_PLANE_STATE` or `~/.local/state/dev-control-plane`.
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
  "events": ["SUCCESS", "FAILED", "BLOCKED", "TIMEOUT"],
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
    "max_text_download_bytes": 2097152,
    "max_binary_download_bytes": 10485760,
    "allow_binary_downloads": false,
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

Timeouts are deliberately separate:

| Setting | Default | Meaning |
| --- | --- | --- |
| `poll_timeout_seconds` | `25` | Telegram `getUpdates` long-poll timeout. |
| `request_timeout_seconds` | `10` | Ordinary Bot API calls (`sendMessage`, `editMessageText`, `answerCallbackQuery`, `getMe`). It no longer inherits the long-poll timeout. |
| `document_timeout_seconds` | `60` | `sendDocument` uploads, which may be larger than a text update. |
| `slow_timing_seconds` | `1.0` | A measured operation at or above this duration is logged as `timing slow`. |

Permissions:

```bash
install -d -m 0700 ~/.config/dev-control-plane
chmod 600 ~/.config/dev-control-plane/telegram.json
```

The monitor refuses to start when the file is group/world accessible or when the
nested `monitor` object, token, numeric user allowlist or numeric chat allowlist is
missing. `require_private_chat` must remain `true`.

`docs_roots` is an explicit allowlist. Registered project report roots are added
automatically from `PROJECT-REGISTRY.md` when they exist. The whole central docs
directory is never exposed as a generic root.

## 5. Activation

These steps are intentionally manual. Choose either the systemd user service
(recommended for normal use) or an owner-controlled foreground terminal. Do not
run both at the same time; the single-instance lock refuses the second process.

### 5.1 Read-only preflight

Run the read-only check first:

```bash
python3 /home/iffi/dev-workspace/control-plane/tools/dev_monitor.py check
```

This validates config permissions, numeric allowlists, `getMe`, the webhook
state, the project registry, document roots and monitor state permissions. It
does not start polling and it never clears a webhook silently.

### 5.2 Install and activate the systemd user service

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

### 5.3 Foreground alternative

If the service is not used, start the monitor in an owner-controlled terminal:

```bash
python3 /home/iffi/dev-workspace/control-plane/tools/dev_monitor.py run
```

Stop it with `Ctrl-C`, or from another terminal:

```bash
python3 /home/iffi/dev-workspace/control-plane/tools/dev_monitor.py stop
```

### 5.4 Service status, logs and lifecycle

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

### 5.5 First owner verification

From the authorized private chat, send `/start`, `/jobs`, `/projects` and
`/docs`. Verify that unauthorized accounts receive only a generic denial. Open a
job, preview a report and browse a document. Running jobs remain independent of
the monitor lifecycle.

### 5.6 Run exit codes

| Code | Meaning | Service restart |
| --- | --- | --- |
| `0` | Graceful signal/flag stop. | No |
| `1` | Unexpected or non-fatal top-level failure. | Yes, bounded by start limit |
| `2` | Configuration or usage error. | No |
| `75` | Another monitor instance owns the single-instance lock. | No |
| `78` | Fatal Telegram auth/conflict error (`401`, `403`, `409`). | No |

## 6. Commands and menus

| Command | Result |
| --- | --- |
| `/start`, `/menu` | Main menu |
| `/jobs` | Active jobs first, then recent terminal jobs |
| `/job <reference>` | Open a job by server-side reference |
| `/status [job]` | Compact status view; latest job when omitted |
| `/projects` | Registered projects, repository and docs availability |
| `/docs` | Allowlisted document roots |
| `/help` | Commands, active mode and safety notes |

Job actions are Refresh, Run log, Worker log, Report, Download report and Download
log. Document actions are open directory, preview text, download a redacted text
copy and, only when explicitly enabled, a confirmed binary download. Callback data
contains opaque server-side references, never paths, job IDs, prompts or user IDs.

## 7. State and diagnostics

Monitor state is private and separate from job state:

```text
<Workflow state root>/monitor/monitor.db   # SQLite, mode 0600, WAL mode
<Workflow state root>/monitor/monitor.lock # single-instance lock
<Workflow state root>/monitor/monitor.stop # graceful stop flag
```

Use `DEV_MONITOR_STATE` to override the monitor state directory and
`--state-dir` on the CLI for a one-off override. Deleting monitor state resets UI
state and polling offsets only; Workflow v3 jobs are unaffected.

Diagnostics:

```bash
python3 tools/dev_monitor.py status
python3 tools/dev_monitor.py status --json
python3 tools/dev_monitor.py check
```

The audit table stores the timestamp, numeric user/chat/update IDs, action, job
ID, result and a short redacted detail. It never stores message bodies, prompts,
logs, tokens or environment variables.

### 7.1 Timing diagnostics

Timing data is kept in memory, bounded, and written only to the service logger
(the systemd journal when running as a service). No timing row is added to
SQLite, so diagnostics do not increase state write pressure.

Labels describe stable operations, not user content:

| Label | Area |
| --- | --- |
| `poll:getUpdates` | Long-poll request and wait |
| `ack:batch` | Callback acknowledgement pass for a polling batch |
| `telegram:getUpdates`, `telegram:sendMessage`, `telegram:editMessageText`, `telegram:answerCallbackQuery`, `telegram:sendDocument` | Individual Bot API calls |
| `update:message`, `update:callback_query` | Per-update dispatch |
| `action:command:<name>`, `action:callback:<head>` | Menu action handling, using a fixed allowlist of command/button names |
| `cli:dev_status`, `cli:dev_report` | Synchronous Workflow v3 CLI subprocess |
| `docs:list`, `docs:preview`, `docs:download` | Descriptor-based document access |
| `sqlite:set_offset`, `sqlite:claim_update`, `sqlite:record_audit`, `sqlite:hit_rate_limit`, `sqlite:prune`, `sqlite:snapshot` | Monitor state writes and reads |

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
- `cli:dev_status` or `cli:dev_report` slow points at synchronous Workflow v3
  subprocess cost.
- `docs:*` slow points at a large or slow document directory.
- `sqlite:*` slow points at state storage.
- `poll:getUpdates` near the configured long-poll timeout is normal when no
  update arrived.

Ordinary Telegram calls are bounded by `request_timeout_seconds` rather than the
long-poll timeout. The previous implementation reused `poll_timeout + 10` for
every call, which could stall a menu edit for up to 35 seconds. Callback
acknowledgements remain capped at 5 seconds and the whole batch is acknowledged
before any read-only action runs.

SQLite uses WAL mode and `synchronous=NORMAL` so the owner's read-only `status`
command does not block the monitor writer. The polling offset and last-poll time
are written in one transaction instead of two separate commits.

## 8. Troubleshooting

| Symptom | Action |
| --- | --- |
| `409 Conflict` | Another poller or webhook is active. Stop the other poller or clear the webhook explicitly; never leave two pollers running. |
| `401 Unauthorized` | Correct the owner-local token; never print it into chat, logs or Git. The service does not restart on this exit code. |
| Config refused | Set mode `0600` and add non-empty numeric user/chat allowlists. |
| Service does not start | Run `systemctl --user status ...` and `journalctl --user -u ... -n 100 --no-pager`; then run `dev_monitor.py check`. |
| Service restart loop | The unit refuses restart for exit codes `2`, `75` and `78`. Check `systemctl --user status`; repeated other failures hit `StartLimitBurst=5` in 5 minutes. |
| `75` duplicate instance | Stop the foreground monitor or the other service instance first. Only one process may hold the lock. |
| No updates | Check `dev_monitor.py check`, confirm the bot was started, and inspect the stored offset with `dev_monitor.py status`. |
| Menu feels slow | Search the journal for `timing slow` and read the label. Compare `telegram:*`, `cli:*`, `docs:*` and `sqlite:*` lines before changing anything. |
| Status is stale | Workflow v3 status reconciles a missing worker; refresh the job view. |
| Document refused | Absolute paths, `..`, backslashes, percent encodings, hidden names, symlinks and sensitive names are refused by design. |
| Binary download refused | Keep `allow_binary_downloads` false unless the owner explicitly needs binary documents; enabled binary downloads require per-file confirmation. |
| Duplicate lifecycle messages | P1 does not send lifecycle notifications; final-only Workflow v3 behaviour is unchanged. |

## 9. Validation

The P1 tests use fake Telegram transports and isolated fixtures. They never
contact production Telegram and never start a real OpenCode session:

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
python3 tools/test_dev_monitor_integration.py
```

The unit can be syntax-checked without installing it:

```bash
systemd-analyze verify deploy/systemd/user/qortium-dev-monitor.service
```

The full control-plane release gate remains:

```bash
python3 tools/validate_control_plane.py
python3 tools/validate_skills.py
python3 tools/validate_security.py --self-test
python3 tools/validate_security.py .
python3 tools/validate_agent_permissions.py --check
```

## 10. Deferred to later phases

- P2: start/resume wizards, per-project admission, STARTED/RESUMED notifications,
  optional local unlock.
- P3: additive `dev cancel`, additive `dev resume --prompt-file -` and queued
  owner instructions.
- P4: real-runtime acceptance matrix, incident runbook hardening and any binary
  document policy change.

P1 deliberately exposes no start, resume, cancel, accept or owner-message action.
