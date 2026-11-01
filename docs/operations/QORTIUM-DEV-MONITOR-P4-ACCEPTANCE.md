# Qortium Dev Monitor P4 — real-runtime owner acceptance checklist

Status: **P4 automated hardening is implemented and tested; the monitor health
check now distinguishes start readiness from running-instance health. Real-
Telegram owner acceptance remains pending until the owner executes this checklist
with the real bot. No real-Telegram or owner-attested P4 evidence is recorded in
this repository as of 2026-11-01.** This document does not authorize Telegram
actions, a service restart or a live-job cancellation by an agent.

| Field | Value |
| --- | --- |
| Executing agent | `DeepSeek` |
| Report/handoff writer | `DeepSeek` (same agent) |
| Executing-agent evidence | Work performed by the `deepseek/deepseek-flash` model through owner-authorized Workflow v3 jobs. The 2026-11-01 consolidation and health-semantics revision was job `20261101T160725Z-p4-monitor-health-semantics-and-374926d9`; the original P4 implementation was job `20261101T064540Z-qortium-dev-monitor-p4-hardening-72a27d10`. No second agent produced the work. |
| Artifact type | Operations / owner acceptance checklist |
| Project scope | Cross-project Workflow v3 control plane (`workspace` material) |
| Canonical path | `docs/operations/QORTIUM-DEV-MONITOR-P4-ACCEPTANCE.md` |
| Control-plane contract | [AGENTS.md](../../AGENTS.md), [WORKFLOW.md](../../WORKFLOW.md), [GIT-AND-HANDOFF.md](../../GIT-AND-HANDOFF.md) |
| Runbook | [QORTIUM-DEV-MONITOR.md](QORTIUM-DEV-MONITOR.md) |
| Architecture | [QORTIUM-DEV-MONITOR-ARCHITECTURE.md](QORTIUM-DEV-MONITOR-ARCHITECTURE.md) |

## 1. What the owner is accepting

The checklist proves the real deployed monitor still satisfies the P1-P4 safety
contract:

- only numeric allowlisted users in the configured private chat can act;
- every mutating action needs an explicit one-time confirmation;
- callback replays and duplicate updates do not repeat actions;
- credentials never appear in chat, logs, audit rows, reports or attachments;
- document browsing refuses traversal, symlinks, hidden/sensitive names, special
  files and oversize files;
- start, resume and cancel go only through the existing Workflow v3 CLI;
- queued owner instructions are delivered exactly once at the next resume;
- STARTED, RESUMED and terminal notifications are not duplicated after restart;
- polling recovers from transient Telegram failures without losing updates;
- the monitor opens no listener and never touches Qortium or VPS configuration.

## 2. Preconditions and safety rules

1. Read [QORTIUM-DEV-MONITOR.md](QORTIUM-DEV-MONITOR.md) first.
2. Confirm `monitor.mode` is the intended mode. Start with `read_only`; enable
   `control` only for a deliberate acceptance window.
3. Keep the owner-local `telegram.json` at mode `0600`. Never paste its token,
   chat ID or passphrase hash into a report, commit, chat message or terminal
   transcript.
4. Run `dev_monitor.py check --expect running` and record the sanitized output before testing. Use `--expect start` only when deliberately checking pre-start readiness; a healthy running monitor correctly reports `preflight: NOT ready`.
5. Use a disposable acceptance job and an isolated repository/worktree. Do not
   cancel or resume a real production job as part of acceptance. For a
   deterministic synthetic backend for R-08 and R-09, use the
   [P3 live Telegram acceptance harness](QORTIUM-DEV-MONITOR-P3-LIVE-ACCEPTANCE.md);
   it isolates the repository, registry, job state and fake worker, and forces
   the synthetic job to `CANCELLED`.
6. Do not install, restart, stop, reconfigure or signal the Qortium node. Do not
   change VPS networking, mounts, packages, services or firewall rules.
7. Do not run `sudo`, a service manager with mutating verbs, `crontab`, `at`, or
   a name-based process kill.
8. Before and after the matrix, record the Qortium PID/RSS and listening
   sockets. They must be unchanged except for normal process activity.

Useful read-only preflight:

```bash
cd /home/iffi/dev-workspace/control-plane
python3 tools/dev_monitor.py check --expect running
python3 tools/dev_monitor.py check --expect start
python3 tools/dev_monitor.py status --json
systemctl --user status qortium-dev-monitor.service --no-pager || true
journalctl --user -u qortium-dev-monitor.service -n 50 --no-pager || true
ps -o pid,rss,args -p "$(pgrep -f 'Qortium.jar' | head -n1)" || true
ss -ltnp | grep -E 'qortium|dev-monitor|python' || true
```

`pgrep` above is read-only PID discovery for `ps`; never use a name-based kill.
If the service is not installed, the foreground runbook path applies.

## 3. Acceptance matrix and evidence status

### 3.1 Evidence classes

Every row distinguishes what is actually proved:

| Class | Meaning | Trust level |
| --- | --- | --- |
| **A — automated** | Isolated unit, integration or fault-injection tests using a fake Telegram transport, fake Workflow v3 CLI, temporary SQLite state and/or test-owned helper processes. No real bot, token, production job or service is used. | Proves code paths only. Never proves real Telegram delivery, real OpenCode work, VPS state or production-job semantics. |
| **S — synthetic P3 E1-E7** | The already verified P3 queue/cancel/resume acceptance harness and its automated E1-E7 tests. They exercise the real monitor router, authorization, callback handling, confirmation nonces and renderers against a scripted or isolated transport and a synthetic, forced-`CANCELLED` job. | Proves the synthetic callback/queue/cancel/resume contract. Does **not** prove real production-job delivery, real OpenCode execution, real Qortium behavior or every P4 row. A real-bot P3 run is still owner-only and is not recorded here. |
| **T — real Telegram observed** | Sanitized journal/evidence produced by an actual owner interaction with the real bot (message IDs, update IDs, button/callback labels). | The only class that can prove real Telegram round-trips. **None recorded for P4.** |
| **O — owner-attested** | A dated owner statement about an observation that is not otherwise captured by the harness. | Weakest live evidence; must name what was observed and when. **None recorded for P4.** |
| **U — unexecuted live check** | A required real-runtime step that has not been performed. | Not a pass. Must remain pending in the sign-off. |

Automated tests and synthetic P3 results must never be relabelled as real
Telegram or production-job evidence.

### 3.2 Consolidated R-01 through R-16

The "Automated / synthetic" column names current repository coverage. The
"Real Telegram" and "Owner-attested" columns are deliberately empty until the
owner performs the interaction and records sanitized evidence. `U` means the
live check is unexecuted.

| ID | Scenario | Automated / synthetic coverage | Real Telegram evidence (T) | Owner-attested (O) | Live status |
| --- | --- | --- | --- | --- | --- |
| R-01 | Authorized owner menu | `test_dev_monitor_integration.py::test_authorized_start_returns_main_menu`, `::test_help_and_unknown_commands`; `test_dev_monitor_auth.py` allowlist cases | none recorded | none recorded | U — not executed with the real bot |
| R-02 | Unauthorized account | `test_dev_monitor_p4.py::test_unauthorized_identities_are_denied_without_job_data`; `test_dev_monitor_integration.py::test_unknown_user_gets_generic_denial_without_job_data`, `::test_unauthorized_callback_is_rejected_before_state_lookup`; `test_dev_monitor_auth.py` denial cases | none recorded | none recorded | U — no second real account used |
| R-03 | Read-only browsing | `test_dev_monitor_integration.py::test_job_list_status_logs_and_report`, `::test_document_browse_preview_and_redacted_download`; `test_dev_monitor_p4.py` document-hardening tests | none recorded | none recorded | U — production previews not exercised |
| R-04 | Document traversal and symlink | `test_dev_monitor_p4.py::test_traversal_absolute_and_encoded_paths_are_refused`, `::test_listing_excludes_hidden_symlinks_sensitive_and_special_files`, `::test_symlink_swap_between_listing_and_open_is_refused`, `::test_symlinked_root_is_refused` | none recorded | none recorded | U — isolated fixtures only |
| R-05 | Redacted download | `test_dev_monitor_p4.py::test_text_preview_and_download_are_redacted_and_source_is_unchanged`; `test_dev_monitor_integration.py::test_job_download_log` | none recorded | none recorded | U — no real report/document download |
| R-06 | Start a disposable job | `test_dev_monitor_p4.py::test_start_queue_cancel_resume_with_fake_cli` (fake `dev start`, no OpenCode) | none recorded | none recorded | U — no real start; synthetic P3 results do not prove real job delivery |
| R-07 | Duplicate confirmation | `test_dev_monitor_p4.py::test_duplicate_update_runs_its_action_once`, `::test_confirmation_nonces_are_single_use_across_connections`, `::test_confirmation_rejects_wrong_owner_action_and_expiry`; `test_dev_monitor_integration.py` duplicate/restart cases | none recorded | none recorded | U — no real double button press |
| R-08 | Queue an instruction | S: P3 `test_p3_live_acceptance.py::test_live_flow_queue_and_cancel_produces_verifiable_evidence`, `::test_e7_waits_for_resume_then_stops_only_after_second_cancel`; A: `test_dev_monitor_p4.py` fake-CLI queue flow | none recorded | none recorded | U — synthetic/scripted only; real P3 live run not recorded |
| R-09 | Cancel only the disposable job | S: P3 E1-E7 automated cancel flow and `dev cancel` fake worker; A: `test_dev_monitor_p4.py::test_cancel_revalidates_running_state_before_signal`; `test_dev_monitor_p3.py` cancel tests | none recorded | none recorded | U — no live production or synthetic job was cancelled by this job |
| R-10 | Resume and deliver once | S: P3 E7 automated two-cancellation lifecycle and exactly-once delivery test; A: `test_dev_monitor_p4.py::test_start_queue_cancel_resume_with_fake_cli` | none recorded | none recorded | U — synthetic only; no real resume/delivery |
| R-11 | Failed resume keeps the queue | `test_dev_monitor_p3.py::test_failed_resume_keeps_the_queue_queued`; `test_dev_monitor_p4.py` queue/resume integration | none recorded | none recorded | U — no real refused resume |
| R-12 | Restart persistence | `test_dev_monitor_p4.py::test_restart_preserves_offset_seen_updates_nonces_and_queue`, `::test_notification_dedupe_survives_restart`; `test_dev_monitor_integration.py` restart cases | none recorded | none recorded | U — monitor was not restarted |
| R-13 | Polling fault recovery | `test_dev_monitor_p4.py::test_polling_recovers_from_transient_and_rate_limit_without_losing_updates`, `::test_fatal_poll_error_stops_without_advancing_offset`, `::test_transient_action_failure_is_not_replayed`; `test_dev_monitor_integration.py` 429/transient cases | none recorded | none recorded | U — no owner-approved network fault |
| R-14 | Token rotation | No automated real-token rotation; configuration validation rejects malformed/insecure config, but rotation itself requires the real BotFather flow | none recorded | none recorded | U — owner-only; not executed and no token was read or changed |
| R-15 | No listener and no Qortium/VPS change | `test_dev_monitor_integration.py::test_monitor_source_has_no_listener_or_host_mutation` (static source assertion); no before/after real runtime comparison | none recorded | none recorded | U — no live before/after listener/PID/config comparison was performed |
| R-16 | Graceful shutdown | `test_dev_monitor_service_unit.py` systemd/stop contract; `test_dev_monitor_integration.py::test_stop_flag_stops_between_iterations`; `test_dev_monitor_p4.py` stop/lock cases | none recorded | none recorded | U — no service stop or flag-file stop was performed |

Row-level rule: a failing live security row (authorization, redaction,
traversal/symlink, cancel identity or duplicate side effect) blocks acceptance
even when every automated test passes. Conversely, green automated tests do not
promote an unexecuted live row to pass.

### 3.3 Health-check semantics used by this checklist

`dev_monitor.py check` now reports two separate concerns:

- **running-instance health** — is the holder of `monitor.lock` a verified live
  `dev_monitor.py run` process, with no competing monitor process targeting the
  same state directory?
- **start preflight** — could a new monitor safely acquire the lock now?

A legitimate healthy running instance is reported as `lock: ok` and the default
`check` passes. It is simultaneously `preflight: NOT ready`, because starting a
second instance must remain refused. Use `--expect running` for a strict health
probe and `--expect start` for a strict preflight probe. A stale lock file is
reported but does not block a new start; an unknown lock owner or competing
instances fail closed. See the runbook for exact output and exit behavior.

## 4. Evidence capture

Store a short sanitized record under the central workspace validation tree:

```text
/home/iffi/dev-workspace/docs/workspace/validation/
```

Include:

- exact application commit SHA and monitor version;
- `dev_monitor.py check` output (sanitized);
- each R-row result, timestamp and short observation;
- before/after Qortium PID/RSS and listener comparison;
- any owner-only step that could not be executed and why;
- no tokens, chat IDs, passphrases, prompts, private paths or raw logs.

Do not copy the owner-local `telegram.json` or monitor SQLite database into Git or
a report.

## 5. Sign-off

| Field | Value |
| --- | --- |
| Owner | |
| Date / time (UTC) | |
| Application SHA | |
| Monitor version | |
| Mode (`read_only` / `control`) | |
| Rows passed | |
| Rows failed or not executed | |
| Reason for any exception | |
| Rollback performed? | |
| Remaining risk accepted? | |

A failed security row (authorization, redaction, traversal/symlink, cancel
identity, duplicate side effect) blocks acceptance. Revert `monitor.mode` to
`read_only`, stop the monitor through its documented path, and record the failure
without modifying Qortium or VPS configuration.

## 6. Optional `control_passphrase_hash` assessment

**Decision: recommended for control mode; not enabled or changed by this job.**
Read-only mode does not need it. The owner should add a strong, unique
`control_passphrase_hash` before a long-lived or high-consequence `control`
activation, and must keep the owner-local config at mode `0600`.

What it improves:

- It adds a local second factor beyond the numeric Telegram user/chat allowlist,
  so a stolen or already-authenticated Telegram session alone cannot start,
  resume, cancel or accept a job.
- Only a salted scrypt hash is stored. The monitor verifies the passphrase in
  memory and keeps a short-lived per-user/per-chat unlock marker; nothing about
  the passphrase is written to monitor state, audit rows, reports or logs.
- Unlock is time-bounded by `unlock_ttl_seconds` (default 900 seconds) and is
  cleared on monitor restart or `/lock`.

Operational consequences and residual risks:

- The owner sends `/unlock <passphrase>` through the Telegram chat. Telegram and
  the client may retain that message in chat history, so the passphrase must be
  unique, not reused from another service and treated as exposed to the chat
  medium. The monitor cannot delete Telegram history.
- A lost passphrase requires generating a new hash with
  `dev_monitor.py hash-passphrase` and updating the owner-local config; there is
  no recovery from monitor state.
- Unlock state is in process memory and is lost on every restart. A restarted
  monitor is locked again even if it was unlocked before.
- The hash protects the control-action boundary, not a compromised host. A local
  attacker who can read the owner config or process memory is outside this
  control's threat model.
- Failed unlocks are subject to the existing per-user/per-chat action rate limits,
  but there is no permanent lockout. The passphrase must still be strong.
- Synthetic and automated tests prove hashing, malformed-hash rejection, unlock
  expiry and redaction boundaries; they do not prove the owner's real chat
  handling of the passphrase.

No owner authentication setting, token, chat ID or passphrase was read, printed,
changed or committed by this job.

## 7. Current evidence verdict

As of 2026-11-01, the automated and synthetic layers are green, the health-check
semantics are corrected and covered, and the R-matrix is consolidated. The
real-Telegram (T) and owner-attested (O) columns are empty, and every live row
remains `U`. The owner must perform and record the live checks before sign-off.
