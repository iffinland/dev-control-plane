# Qortium Dev Monitor P4 — real-runtime owner acceptance checklist

Status: **P4 automated hardening is implemented and tested; the monitor health
check distinguishes start readiness from running-instance health. The owner also
completed the real P3 E1-E7 Telegram run through the actual authorized bot with
the isolated synthetic worker: Queue instruction, two cancellations, Resume and
exactly-once delivery into synthetic attempt #2 passed the harness's formal
verification. The temporary evidence directory was cleaned up, so no message
IDs, update IDs, timestamps, journal or report from that run are retained in this
repository. R-08, R-09 and R-10 therefore carry real-Telegram/synthetic-backend
evidence only, never production-worker verification. Menu, Refresh and monitor
service stop/start were observed during that run and are recorded only as
owner-attested observations. Real token rotation and deliberate network fault
injection remain unexecuted owner-only exceptions. No P4 production-worker
acceptance is claimed.** This document does not authorize Telegram actions, a
service restart or a live-job cancellation by an agent.

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
| **S — synthetic P3 E1-E7 (scripted)** | The P3 queue/cancel/resume acceptance harness and its automated E1-E7 tests, driven by a scripted or isolated transport and a synthetic, forced-`CANCELLED` job. | Proves the synthetic callback/queue/cancel/resume contract. Does **not** prove a real Telegram round-trip. |
| **RT/S — real Telegram with synthetic backend** | A genuine interaction with the actual authorized bot, routed through the isolated P3 worker and a synthetic job, that passed the harness's formal verification. | Proves the observed real Telegram round-trip and the synthetic backend behavior only. It does **not** prove production-worker, production-job, OpenCode or Qortium behavior. If the temporary evidence directory was cleaned, no identifiers are reconstructed. |
| **T — retained real Telegram evidence** | A sanitized journal or report retained from a real bot interaction, including message/update IDs, callback labels and timestamps. | The strongest retained live evidence. **None retained for P4.** |
| **O — owner-attested** | A dated owner statement about an observation that is not captured by retained harness evidence. | Weakest live evidence; must name what was observed and when, and must not be expanded into an unobserved guarantee. |
| **U — unexecuted live check** | A required real-runtime step that has not been performed. | Not a pass. Must remain pending in the sign-off or be recorded as an explicit exception. |

Automated tests, scripted synthetic results and real-Telegram/synthetic-backend
results must never be relabelled as production-worker or production-job evidence.
A cleaned temporary evidence directory is not permission to invent identifiers.

### 3.2 Consolidated R-01 through R-16

The "Automated / scripted" column names current repository coverage. "RT/S"
records the observed real-bot run with the isolated synthetic backend, whose
temporary evidence was cleaned. "O" records observations without retained
harness evidence. `U` means the live check remains unexecuted. No row is promoted
to production-worker, production-job or retained-journal evidence.

| ID | Scenario | Automated / scripted synthetic coverage | Real Telegram + synthetic backend (RT/S) | Owner-attested (O) | Live status / remaining gap |
| --- | --- | --- | --- | --- | --- |
| R-01 | Authorized owner menu | `test_dev_monitor_integration.py::test_authorized_start_returns_main_menu`, `::test_help_and_unknown_commands`; `test_dev_monitor_auth.py` allowlist cases | The authorized owner navigated `/jobs` and the synthetic job view through the real bot. No retained journal or IDs. | Main menu and job navigation observed on 2026-11-01 during the P3 E1-E7 run. | Partial — real menu path observed; a dedicated `/start` and secret-exposure check was not separately captured. |
| R-02 | Unauthorized account | `test_dev_monitor_p4.py::test_unauthorized_identities_are_denied_without_job_data`; `test_dev_monitor_integration.py::test_unknown_user_gets_generic_denial_without_job_data`, `::test_unauthorized_callback_is_rejected_before_state_lookup`; `test_dev_monitor_auth.py` denial cases | none | none | U — no second real account was used. |
| R-03 | Read-only browsing | `test_dev_monitor_integration.py::test_job_list_status_logs_and_report`, `::test_document_browse_preview_and_redacted_download`; `test_dev_monitor_p4.py` document-hardening tests | The synthetic job status view was browsed through the real bot. | Refresh was pressed on the synthetic job view and its normal feedback was observed. | Partial — job view and Refresh observed; real document preview/download not exercised. |
| R-04 | Document traversal and symlink | `test_dev_monitor_p4.py::test_traversal_absolute_and_encoded_paths_are_refused`, `::test_listing_excludes_hidden_symlinks_sensitive_and_special_files`, `::test_symlink_swap_between_listing_and_open_is_refused`, `::test_symlinked_root_is_refused` | none | none | U — isolated fixtures only. |
| R-05 | Redacted download | `test_dev_monitor_p4.py::test_text_preview_and_download_are_redacted_and_source_is_unchanged`; `test_dev_monitor_integration.py::test_job_download_log` | none | none | U — no real report/document download. |
| R-06 | Start a disposable job | `test_dev_monitor_p4.py::test_start_queue_cancel_resume_with_fake_cli` (fake `dev start`, no OpenCode) | none — the P3 harness deliberately never starts OpenCode | none | U — no real start; synthetic P3 results do not prove production job delivery. |
| R-07 | Duplicate confirmation | `test_dev_monitor_p4.py::test_duplicate_update_runs_its_action_once`, `::test_confirmation_nonces_are_single_use_across_connections`, `::test_confirmation_rejects_wrong_owner_action_and_expiry`; `test_dev_monitor_integration.py` duplicate/restart cases; S: P3 `test_p3_live_acceptance.py::R07ReplayTests` (same update + same callback/new update, one nonce, one `dev cancel`, final `CANCELLED`) | none | none | S only — deterministic synthetic P3 R-07 replay is scripted-tested. A real-bot R-07 run remains U; no real double press or replayed confirmation was executed or retained. |
| R-08 | Queue an instruction | S: P3 `test_p3_live_acceptance.py::test_live_flow_queue_and_cancel_produces_verifiable_evidence`, `::test_e7_waits_for_resume_then_stops_only_after_second_cancel`; A: `test_dev_monitor_p4.py` fake-CLI queue flow | Yes — real bot Queue instruction on the synthetic job; harness formal verification passed. Evidence cleaned; no IDs/timestamps retained. | Queue flow observed during the same real-bot run. | RT/S only — proves the real Telegram queue round-trip with a synthetic backend, not production-worker delivery. |
| R-09 | Cancel only the disposable job | S: P3 E1-E7 automated cancel flow and `dev cancel` fake worker; A: `test_dev_monitor_p4.py::test_cancel_revalidates_running_state_before_signal`; `test_dev_monitor_p3.py` cancel tests | Yes — two real-bot cancellations of the synthetic job; formal verification passed. Evidence cleaned; no IDs/timestamps retained. | Cancel flow observed during the same real-bot run. | RT/S only — no production job was cancelled and production-worker cancellation is not proved. |
| R-10 | Resume and deliver once | S: P3 E7 automated two-cancellation lifecycle and exactly-once delivery test; A: `test_dev_monitor_p4.py::test_start_queue_cancel_resume_with_fake_cli` | Yes — real-bot Resume delivered the queued instruction into synthetic attempt #2 exactly once; formal verification passed. Evidence cleaned; no IDs/timestamps retained. | Resume and delivery observed during the same real-bot run. | RT/S only — proves exactly-once synthetic attempt-#2 delivery, not production-worker resume. |
| R-11 | Failed resume keeps the queue | `test_dev_monitor_p3.py::test_failed_resume_keeps_the_queue_queued`; `test_dev_monitor_p4.py` queue/resume integration | none | none | U — no real refused resume. |
| R-12 | Restart persistence | `test_dev_monitor_p4.py::test_restart_preserves_offset_seen_updates_nonces_and_queue`, `::test_notification_dedupe_survives_restart`; `test_dev_monitor_integration.py` restart cases | none | The production monitor was stopped and restarted around the P3 run, but not while a disposable job was RUNNING. | U — offset/queue/nonce/dedupe persistence across a running-job restart was not captured. |
| R-13 | Polling fault recovery | `test_dev_monitor_p4.py::test_polling_recovers_from_transient_and_rate_limit_without_losing_updates`, `::test_fatal_poll_error_stops_without_advancing_offset`, `::test_transient_action_failure_is_not_replayed`; `test_dev_monitor_integration.py` 429/transient cases | none | none | U — deliberate network fault injection remains an unexecuted owner-only exception. |
| R-14 | Token rotation | No automated real-token rotation; configuration validation rejects malformed/insecure config, but rotation itself requires the real BotFather flow | none | none | U — unexecuted owner-only exception; no token was read, printed or changed. |
| R-15 | No listener and no Qortium/VPS change | `test_dev_monitor_integration.py::test_monitor_source_has_no_listener_or_host_mutation` (static source assertion); no before/after real runtime comparison | none — the P3 run does not prove host/listener invariants | none | U — no live before/after listener/PID/config comparison was performed. |
| R-16 | Graceful shutdown | `test_dev_monitor_service_unit.py` systemd/stop contract; `test_dev_monitor_integration.py::test_stop_flag_stops_between_iterations`; `test_dev_monitor_p4.py` stop/lock cases | none | The monitor service was stopped and started through its documented service path for the P3 run. | Partial — stop/start observed; graceful exit status, lock release and running-job independence were not separately captured. |

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

### 3.4 Remaining safe operator checklist

Owner-only actions. An agent must not execute them. Use only the authorized
private chat, prefer a disposable synthetic job, and never use a production job,
real wallet data, the Qortium node or a deliberately sensitive production file
as a test input.

Preflight (read-only):

```bash
cd /home/iffi/dev-workspace/control-plane
python3 tools/dev_monitor.py check --expect running
python3 tools/dev_monitor.py status --json
ps -o pid,rss,args -p "$(pgrep -f 'Qortium.jar' | head -n1)" || true
ss -ltnp | grep -E 'qortium|dev-monitor|python' || true
```

Record the application SHA, monitor version, sanitized check output, Qortium
PID/RSS and listener list before starting. `pgrep` is read-only PID discovery;
never use a name-based kill.

| Step | Safe action | Expected outcome | Evidence capture | Stop / rollback |
| --- | --- | --- | --- | --- |
| 1. Baseline | Run the preflight above. | The running monitor is healthy; no unexpected listener or Qortium change. | Sanitized check output, Qortium PID/RSS, listener list, UTC time. | `check --expect running` fails or Qortium/listener state is unexpected: stop, do not test. |
| 2. R-01 / R-03 menu and Refresh | Send `/start`, `/jobs`; open the disposable synthetic job; press Refresh twice on an unchanged view. | Menu and job view open; mode is visible; no token, chat ID or path leaks; Refresh gives explicit feedback rather than silence. | Sanitized command/button labels, timestamps and result; no credentials. | Any secret or unexpected data appears: revert to `read_only` and stop. |
| 3. R-02 unauthorized account | Only with an owner-controlled second Telegram account not in the allowlist, send `/start`, `/jobs` and press a stale callback. Never automate an unauthorized real account. | Generic `Access denied.` only; no job, project, path or configuration data. | Sanitized denial text and timestamp. | Any data disclosure: stop and record a failed security row. |
| 4. R-03 / R-05 document redaction | Browse an existing harmless document; preview and download it. Do not create a secret-bearing production file. | Text is redacted; the source hash and metadata are unchanged; no secret appears. | Sanitized preview/download result and before/after file hash. | Any unredacted secret: stop and record a failed security row. |
| 5. R-04 traversal and symlink | Try absolute, `..`, backslash and percent-encoded paths. If needed, create one disposable symlink under the docs root and remove it afterwards. | Every attempt is refused; no file outside the trusted root is read. | Sanitized refusal result and timestamp. | Any successful escape: stop and record a failed security row. |
| 6. R-07 confirmation replay | Prefer a fixture prepared with the P3 harness `--mode r07`: press the cancel confirmation once and leave the poller running; the harness replays the exact callback itself. For a manual real-bot check, on the disposable synthetic job only, press the same confirmation button twice or replay a stale callback. | The action runs once; the duplicate is acknowledged without a second side effect; only one `dev cancel` invocation and one consumed nonce exist. | Sanitized messages, journal replay records, invocation count and observed state. | A second side effect: stop and record a failed security row. |
| 7. R-08 / R-09 / R-10 retention (optional) | Re-run the P3 harness with `--mode e7` if a retained journal is desired. Queue one instruction, cancel, Resume, then cancel again. | Synthetic job only; exactly one queued instruction delivered into attempt #2; two cancellations; final state `CANCELLED`, never `SUCCESS`. | Retained private `telegram-journal.jsonl`, `verify` output and timestamp. If the original run's directory was already cleaned, record only "observed, formal verification passed, evidence not retained" and invent nothing. | Any production job, duplicate delivery or `SUCCESS`: stop and keep the failure record. |
| 8. R-11 failed resume | With a disposable synthetic job, queue an instruction and attempt a resume that is deliberately refused. | The instruction remains `[queued]`; nothing is delivered or lost. | Sanitized refusal and queued state. | A lost or duplicated instruction: stop and record a failure. |
| 9. R-12 restart persistence | With a disposable synthetic job RUNNING, restart only the monitor via its documented path. | The job continues; no duplicate STARTED/RESUMED/terminal message; offset, queue and confirmations survive. | Sanitized pre/post status, message counts and UTC time. | If Qortium is touched or messages duplicate: stop and record a failure. |
| 10. R-13 fault injection | Only if the owner deliberately injects a safe network fault; otherwise leave this as an unexecuted exception. | Polling backs off and recovers without losing updates or replaying an in-handler action. | Sanitized observed behavior and recovery time. | Any lost or replayed action: stop and record a failure. |
| 11. R-14 token rotation | Owner-only BotFather rotation, owner config update at `0600`, monitor restart, `check`. Never paste the token. | Old token fails cleanly; new token works after restart; no token in logs, chat, audit or reports. | Only "rotated and verified" plus timestamp; no token or hash. | Old token still works or a token appears: stop and record a failure. This job did not execute rotation. |
| 12. R-15 / R-16 host invariants and shutdown | Re-run the preflight; stop/start the monitor through its documented service or flag path. | No new monitor listener; Qortium PID/RSS and VPS configuration unchanged; graceful exit, released lock, unaffected jobs. | Before/after sanitized comparison, exit/status output, UTC time. | Any Qortium/VPS change or forced shutdown: stop and record a failure. Never use a name-based kill. |

Common rollback: set `monitor.mode` back to `read_only`; stop the monitor through
its documented service or flag path; restore the owner config from its private
backup if it changed; run `dev_monitor.py check`; remove only disposable test
jobs, documents and symlinks. Do not restart, stop or reconfigure Qortium, and do
not change VPS settings.

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

For the already observed real-bot E1-E7 run whose temporary directory was
cleaned, record only "observed; harness formal verification passed; temporary
evidence not retained". Do not reconstruct unavailable message IDs, update IDs,
timestamps or reports, and do not present RT/S evidence as production-worker
evidence.

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
| Rows passed with retained evidence | |
| Rows observed as RT/S or owner-attested | |
| Rows failed, unexecuted or explicit exceptions | |
| Reason for any exception | |
| Rollback performed? | |
| Remaining risk accepted? | |

A failed security row (authorization, redaction, traversal/symlink, cancel
identity, duplicate side effect) blocks acceptance. Revert `monitor.mode` to
`read_only`, stop the monitor through its documented path, and record the failure
without modifying Qortium or VPS configuration. Real token rotation and deliberate
network fault injection remain explicit unexecuted exceptions until the owner
performs them.

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

As of 2026-11-01, the automated and scripted-synthetic layers are green, the
health-check semantics are corrected and covered, and the R-matrix distinguishes
each evidence class. R-08, R-09 and R-10 have genuine real-Telegram interaction
with the isolated synthetic backend and passed the harness's formal verification;
their temporary evidence was cleaned, so no message IDs, timestamps or reports are
retained. Menu, Refresh and monitor service stop/start were observed and remain
owner-attested observations only. The retained real-Telegram (T) column is empty.
Every other live row remains `U`, with real token rotation and deliberate network
fault injection recorded as explicit unexecuted owner-only exceptions. This is
not production-worker acceptance; the owner must perform and record the remaining
safe checks before sign-off.
