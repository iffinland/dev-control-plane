# Qortium Dev Monitor — P1 operations and activation

Status: **P1 read-only observer implemented. Manual owner activation is required.**

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

It reuses the existing Workflow v3 job store and CLI plus the existing owner-local
Telegram configuration. It is not a second job manager and it does not run a
background service.

## 2. Safety boundaries

The monitor:

- runs as the owner's foreground process and refuses a second instance;
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
  audit detail.

## 3. Prerequisites

- Python 3.11+ (the verified environment uses Python 3.13).
- The control-plane checkout at `/home/iffi/dev-workspace/control-plane`.
- An owner-created Telegram bot and its token, stored outside Git.
- The owner's numeric Telegram user ID and private chat ID.
- Existing Workflow v3 state, normally under
  `$DEV_CONTROL_PLANE_STATE` or `~/.local/state/dev-control-plane`.
- Read access to the central docs tree.

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

## 5. Manual activation steps (owner action)

These steps are intentionally manual. P1 implementation did not start a bot
process, register a webhook or change any service.

1. Create or choose the Telegram bot and keep it in private-chat use only.
2. Add the nested `monitor` object to the owner-local `telegram.json` and set the
   real numeric user and chat IDs. Keep `mode` at `read_only`.
3. Set permissions to `0600` on the config file and `0700` on its directory.
4. Confirm no webhook is configured for the bot. The monitor fails closed on a
   `409 Conflict` or a configured webhook; it never clears a webhook silently.
5. Run the read-only check:

   ```bash
   python3 /home/iffi/dev-workspace/control-plane/tools/dev_monitor.py check
   ```

   This validates config permissions, numeric allowlists, `getMe`, the webhook
   state, the project registry, document roots and monitor state permissions. It
   does not start polling.

6. Start the monitor in an owner-controlled terminal or tmux session:

   ```bash
   python3 /home/iffi/dev-workspace/control-plane/tools/dev_monitor.py run
   ```

   This is the only supported start action. Do not install it as a system
   service. Do not start a second copy; the single-instance lock refuses it.

7. From the authorized private chat, send `/start`, `/jobs`, `/projects` and
   `/docs`. Verify that unauthorized accounts receive only a generic denial.
8. Stop gracefully with `/home/iffi/dev-workspace/control-plane/tools/dev_monitor.py stop`
   or `Ctrl-C` in the foreground terminal. Running Workflow v3 jobs are detached
   and are not affected.

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
<Workflow state root>/monitor/monitor.db   # SQLite, mode 0600
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

## 8. Troubleshooting

| Symptom | Action |
| --- | --- |
| `409 Conflict` | Another poller or webhook is active. Stop the other poller or clear the webhook explicitly; never leave two pollers running. |
| `401 Unauthorized` | Correct the owner-local token; never print it into chat, logs or Git. |
| Config refused | Set mode `0600` and add non-empty numeric user/chat allowlists. |
| No updates | Check `dev_monitor.py check`, confirm the bot was started, and inspect the stored offset with `dev_monitor.py status`. |
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
python3 tools/test_dev_monitor_integration.py
```

The full control-plane release gate remains:

```bash
python3 tools/validate_control_plane.py
python3 tools/validate_skills.py
python3 tools/validate_security.py --self-test
python3 tools/validate_security.py .
```

## 10. Deferred to later phases

- P2: start/resume wizards, per-project admission, STARTED/RESUMED notifications,
  optional local unlock.
- P3: additive `dev cancel`, additive `dev resume --prompt-file -` and queued
  owner instructions.
- P4: real-runtime acceptance matrix, incident runbook hardening and any binary
  document policy change.

P1 deliberately exposes no start, resume, cancel, accept or owner-message action.
