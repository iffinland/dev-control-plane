# Qortium Dev Monitor P4 — final real-runtime owner acceptance report

Status: **P4 automated hardening is implemented and tested. The owner has now
performed the real-Telegram P3 synthetic E1-E7 run and the R-07 confirmation-
replay run through the actual authorized bot with the isolated synthetic worker.
Both passed the harness's formal verification. The owner also observed the
unauthorized-account denial, workspace README browsing, and a redacted README
download on Android. The temporary synthetic evidence directories were cleaned,
so this report intentionally contains no reconstructed message IDs, update IDs,
timestamps, journals or reports. R-07 through R-10 remain real-Telegram /
synthetic-backend evidence only; no production-worker or production-job
acceptance is claimed. Real token rotation, deliberate network-fault injection,
production-worker cancellation and host-invariant comparisons remain unexecuted
or explicit exceptions.** This document does not authorize Telegram actions, a
service restart or a live-job cancellation by an agent.

| Field | Value |
| --- | --- |
| Executing agent | `DeepSeek` (`deepseek/deepseek-flash`) |
| Report/handoff writer | `DeepSeek` (same agent) |
| Executing-agent evidence | Work performed by the `deepseek/deepseek-flash` model through owner-authorized Workflow v3 jobs. The original P4 implementation was job `20261101T064540Z-qortium-dev-monitor-p4-hardening-72a27d10`; the evidence consolidation was `20261101T163605Z-p4-security-acceptance-evidence-0db52673`; the R-07 harness mode was added in commit `6efcd2a`; this final acceptance report was produced by job `20261101T180615Z-finalize-p4-security-acceptance-360188a1`. No second agent produced the work. |
| Artifact type | Operations / final owner acceptance report |
| Project scope | Cross-project Workflow v3 control plane (`workspace` material); the monitor observes registered projects but does not modify Qortium, the VPS, services, credentials or wallets |
| Application/code revision under acceptance | `/home/iffi/dev-workspace/control-plane`, branch `agent/control-plane/workflow-v3-20261031`, code base `6efcd2a1bb782910bd2e33b0f6711912f36b5e74`. The documentation commit produced by this report and its verified remote SHA are recorded in `tasks/orchestration/qortium-dev-monitor-p4-final-acceptance-20261101/STATUS.json` and the job evidence file. |
| Monitor version | `0.4.0-p4` |
| Canonical path | `docs/operations/QORTIUM-DEV-MONITOR-P4-ACCEPTANCE.md` |
| Control-plane contract | [AGENTS.md](../../AGENTS.md), [WORKFLOW.md](../../WORKFLOW.md), [GIT-AND-HANDOFF.md](../../GIT-AND-HANDOFF.md) |
| Runbook | [QORTIUM-DEV-MONITOR.md](QORTIUM-DEV-MONITOR.md) |
| Architecture | [QORTIUM-DEV-MONITOR-ARCHITECTURE.md](QORTIUM-DEV-MONITOR-ARCHITECTURE.md) |
| P3 live harness | [QORTIUM-DEV-MONITOR-P3-LIVE-ACCEPTANCE.md](QORTIUM-DEV-MONITOR-P3-LIVE-ACCEPTANCE.md) |

## 1. What the owner is accepting

The acceptance evidence proves that the deployed monitor satisfies the P1-P4
safety contract to the extent recorded in the matrix below:

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

Acceptance is not blanket production-worker acceptance. The owner has proved
specific real-Telegram/synthetic-backend flows and specific owner-observed
surfaces. The rows that remain unexecuted are listed as partial, unexecuted or
explicit exceptions in §4 and §8.

## 2. Scope and evidence boundary

The monitor is a cross-project Workflow v3 control surface, not Qortium node
software. Its real-Telegram tests used the P3 harness's isolated repository,
temporary registry, synthetic job and deterministic fake Workflow v3 CLI. The
synthetic job is forced to `CANCELLED`; it can never become `SUCCESS` or `FAILED`.
The harness does not start OpenCode, invoke a paid model, cancel a production
job, modify the owner's production config, modify the production registry, or
write to the live monitor or job store.

Therefore:

- **RT/S** rows prove a genuine Telegram round-trip plus synthetic-backend
  behavior. They do not prove a production worker, production job, OpenCode
  execution or Qortium behavior.
- **O** rows record what the owner observed but did not retain as a sanitized
  harness journal. They are not expanded into unobserved guarantees.
- **A** and **S** rows prove code paths only.
- **T** (retained real-Telegram evidence) is empty for P4. The cleaned temporary
  directories are not a reason to invent identifiers or timestamps.

## 3. Preconditions and safety rules

1. Read [QORTIUM-DEV-MONITOR.md](QORTIUM-DEV-MONITOR.md) first.
2. Confirm `monitor.mode` is the intended mode. Start with `read_only`; enable
   `control` only for a deliberate acceptance window.
3. Keep the owner-local `telegram.json` at mode `0600`. Never paste its token,
   chat ID or passphrase hash into a report, commit, chat message or terminal
   transcript.
4. Run `dev_monitor.py check --expect running` and record the sanitized output
   before testing. Use `--expect start` only when deliberately checking pre-start
   readiness; a healthy running monitor correctly reports `preflight: NOT ready`.
5. Use a disposable acceptance job and an isolated repository/worktree. Do not
   cancel or resume a real production job as part of acceptance. For R-07, R-08
   and R-09, use the [P3 live Telegram acceptance harness](QORTIUM-DEV-MONITOR-P3-LIVE-ACCEPTANCE.md).
6. Do not install, restart, stop, reconfigure or signal the Qortium node. Do not
   change VPS networking, mounts, packages, services or firewall rules.
7. Do not run `sudo`, a service manager with mutating verbs, `crontab`, `at`, or
   a name-based process kill.
8. Before and after the matrix, record the Qortium PID/RSS and listening sockets.
   They must be unchanged except for normal process activity.

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

## 4. Acceptance matrix and evidence status

### 4.1 Evidence classes

| Class | Meaning | What it proves |
| --- | --- | --- |
| **A — automated** | Isolated unit, integration or fault-injection tests using a fake Telegram transport, fake Workflow v3 CLI, temporary SQLite state and/or test-owned helper processes. No real bot, token, production job or service is used. | Code paths only. Never real Telegram delivery, real OpenCode work, VPS state or production-job semantics. |
| **S — synthetic P3 E1-E7/R-07 (scripted)** | The P3 queue/cancel/resume acceptance harness and its automated tests, driven by a scripted or isolated transport and a synthetic, forced-`CANCELLED` job. | The synthetic callback/queue/cancel/resume and confirmation-replay contract. Does **not** prove a real Telegram round-trip. |
| **RT/S — real Telegram with synthetic backend** | A genuine interaction with the actual authorized bot, routed through the isolated P3 worker and a synthetic job, that passed the harness's formal verification. | The observed real Telegram round-trip and the synthetic backend behavior only. It does **not** prove production-worker, production-job, OpenCode or Qortium behavior, and the cleaned temporary directory leaves no retained identifiers. |
| **T — retained real Telegram evidence** | A sanitized journal or report retained from a real bot interaction, including message/update IDs, callback labels and timestamps. | The strongest retained live evidence. **None retained for P4.** |
| **O — owner-attested** | A dated owner statement about an observation that is not captured by retained harness evidence. | Weakest live evidence; it names what was observed and must not be expanded into an unobserved guarantee. |
| **U — unexecuted live check** | A required real-runtime step that has not been performed. | Not a pass. It remains pending or is recorded as an explicit exception. |

Automated tests, scripted synthetic results and real-Telegram/synthetic-backend
results must never be relabelled as production-worker or production-job evidence.
A cleaned temporary evidence directory is not permission to invent identifiers.

### 4.2 Consolidated R-01 through R-16

The "Automated / scripted" column names current repository coverage. "RT/S"
records the observed real-bot runs with the isolated synthetic backend, whose
temporary evidence was cleaned. "O" records owner observations without retained
harness evidence. "U" means the live check remains unexecuted. No row is promoted
to production-worker, production-job or retained-journal evidence.

| ID | Scenario | Automated / scripted synthetic coverage | Real Telegram + synthetic backend (RT/S) | Owner-attested (O) | Final status / remaining gap |
| --- | --- | --- | --- | --- | --- |
| R-01 | Authorized owner menu | `test_dev_monitor_integration.py::test_authorized_start_returns_main_menu`, `::test_help_and_unknown_commands`; `test_dev_monitor_auth.py` allowlist cases | The authorized owner navigated `/jobs` and the synthetic job view through the real bot. No retained journal or IDs. | Main menu and job navigation observed on 2026-11-01. | **PARTIAL (O)** — real menu/job path observed; a dedicated `/start` and secret-exposure check was not separately captured. |
| R-02 | Unauthorized account | `test_dev_monitor_p4.py::test_unauthorized_identities_are_denied_without_job_data`; `test_dev_monitor_integration.py::test_unknown_user_gets_generic_denial_without_job_data`, `::test_unauthorized_callback_is_rejected_before_state_lookup`; `test_dev_monitor_auth.py` denial cases | none | An owner-controlled second Telegram account received only the generic `Access denied.` for `/start`, `/menu` and `/jobs` on 2026-11-01; no job, project, path or configuration data was reported. | **PASS (O) for the observed commands** — the three read commands were denied without observed job data. A stale-callback denial was not separately exercised, and no retained transcript exists. |
| R-03 | Read-only browsing | `test_dev_monitor_integration.py::test_job_list_status_logs_and_report`, `::test_document_browse_preview_and_redacted_download`; `test_dev_monitor_p4.py` document-hardening tests | The synthetic job status view was browsed through the real bot. | The workspace README preview and browsing worked on 2026-11-01; Refresh was pressed on the synthetic job view and its normal feedback was observed. | **PARTIAL (O)** — real document preview/browsing and job-view Refresh observed; log/report surfaces and full pagination were not separately captured, and no transcript was retained. |
| R-04 | Document traversal and symlink | `test_dev_monitor_p4.py::test_traversal_absolute_and_encoded_paths_are_refused`, `::test_listing_excludes_hidden_symlinks_sensitive_and_special_files`, `::test_symlink_swap_between_listing_and_open_is_refused`, `::test_symlinked_root_is_refused` | none | none | **U** — isolated fixtures only; no live traversal or symlink attempt was performed. |
| R-05 | Redacted download | `test_dev_monitor_p4.py::test_text_preview_and_download_are_redacted_and_source_is_unchanged`; `test_dev_monitor_integration.py::test_job_download_log` | none | `README.redacted.md` was downloaded and opened on Android on 2026-11-01. The owner did not manually demonstrate that secret material was removed, and did not independently compare the source file hash before/after. | **PARTIAL (O)** — redacted-artifact delivery observed; redaction correctness and source invariance are not independently proved, so this row is not a full pass. |
| R-06 | Start a disposable job | `test_dev_monitor_p4.py::test_start_queue_cancel_resume_with_fake_cli` (fake `dev start`, no OpenCode) | none — the P3 harness deliberately never starts OpenCode | none | **U** — no real start; synthetic P3 results do not prove production job delivery or OpenCode execution. |
| R-07 | Duplicate confirmation | `test_dev_monitor_p4.py::test_duplicate_update_runs_its_action_once`, `::test_confirmation_nonces_are_single_use_across_connections`, `::test_confirmation_rejects_wrong_owner_action_and_expiry`; `test_dev_monitor_integration.py` duplicate/restart cases; S: P3 `test_p3_live_acceptance.py::R07ReplayTests` (same update + same callback/new update, one nonce, one `dev cancel`, final `CANCELLED`) | The owner's isolated R-07 synthetic replay run passed formal verification: exactly one cancellation, two rejected/deduplicated replay attempts (same-update and same-callback/new-update), final `CANCELLED`, successful cleanup and the monitor active afterwards. Evidence cleaned; no IDs/timestamps retained. | The same R-07 replay result was owner-observed. | **PASS (RT/S)** — the real Telegram callback replay could not produce a second side effect against the synthetic backend. This is not proof of a production-worker double-press or production cancellation. |
| R-08 | Queue an instruction | S: P3 `test_p3_live_acceptance.py::test_live_flow_queue_and_cancel_produces_verifiable_evidence`, `::test_e7_waits_for_resume_then_stops_only_after_second_cancel`; A: `test_dev_monitor_p4.py` fake-CLI queue flow | The owner's real-Telegram synthetic E1-E7 run passed formal verification, including the queued instruction. Evidence cleaned; no IDs/timestamps retained. | Queue flow observed during the same real-bot run. | **PASS (RT/S)** — proves the real Telegram queue round-trip with a synthetic backend, not production-worker delivery. |
| R-09 | Cancel only the disposable job | S: P3 E1-E7 automated cancel flow and `dev cancel` fake worker; A: `test_dev_monitor_p4.py::test_cancel_revalidates_running_state_before_signal`; `test_dev_monitor_p3.py` cancel tests | The owner's real-Telegram synthetic E1-E7 run passed formal verification, including two cancellations of the synthetic job. Evidence cleaned; no IDs/timestamps retained. | Cancel flow observed during the same real-bot run. | **PASS (RT/S) for the synthetic job** — no production job was cancelled and production-worker cancellation is not proved; that remains an explicit exception. |
| R-10 | Resume and deliver once | S: P3 E7 automated two-cancellation lifecycle and exactly-once delivery test; A: `test_dev_monitor_p4.py::test_start_queue_cancel_resume_with_fake_cli` | The owner's real-Telegram synthetic E1-E7 run passed formal verification: the queued instruction was delivered exactly once into synthetic attempt #2 through Resume. Evidence cleaned; no IDs/timestamps retained. | Resume and delivery observed during the same real-bot run. | **PASS (RT/S)** — proves exactly-once synthetic attempt-#2 delivery, not production-worker resume or delivery. |
| R-11 | Failed resume keeps the queue | `test_dev_monitor_p3.py::test_failed_resume_keeps_the_queue_queued`; `test_dev_monitor_p4.py` queue/resume integration | none | none | **U** — no real or synthetic live refused-resume run was performed. |
| R-12 | Restart persistence | `test_dev_monitor_p4.py::test_restart_preserves_offset_seen_updates_nonces_and_queue`, `::test_notification_dedupe_survives_restart`; `test_dev_monitor_integration.py` restart cases | none | The production monitor was stopped and restarted around the P3/R-07 runs, but not while a disposable job was `RUNNING`. | **U for the guarantee** — offset/queue/nonce/dedupe persistence across a running-job restart was not captured. Stop/start alone is not a pass for R-12. |
| R-13 | Polling fault recovery | `test_dev_monitor_p4.py::test_polling_recovers_from_transient_and_rate_limit_without_losing_updates`, `::test_fatal_poll_error_stops_without_advancing_offset`, `::test_transient_action_failure_is_not_replayed`; `test_dev_monitor_integration.py` 429/transient cases | none | none | **U — explicit exception** — deliberate network-fault injection remains unexecuted and owner-only. |
| R-14 | Token rotation | No automated real-token rotation; configuration validation rejects malformed/insecure config, but rotation itself requires the real BotFather flow | none | none | **U — explicit exception** — unexecuted owner-only action; no token was read, printed or changed. |
| R-15 | No listener and no Qortium/VPS change | `test_dev_monitor_integration.py::test_monitor_source_has_no_listener_or_host_mutation` (static source assertion); no before/after real runtime comparison | none — the P3/R-07 runs do not prove host/listener invariants | none | **U — explicit exception** — no live before/after listener, Qortium PID/RSS or VPS configuration comparison was performed. |
| R-16 | Graceful shutdown | `test_dev_monitor_service_unit.py` systemd/stop contract; `test_dev_monitor_integration.py::test_stop_flag_stops_between_iterations`; `test_dev_monitor_p4.py` stop/lock cases | none | The monitor was stopped and restarted through its documented path for the synthetic runs; R-07 cleanup succeeded and the monitor was active afterwards. | **PARTIAL (O)** — stop/start, cleanup and return to an active monitor observed; graceful exit status, lock release, and running-job independence were not separately captured. |

Row-level rule: a failing live security row (authorization, redaction,
traversal/symlink, cancel identity or duplicate side effect) blocks acceptance
even when every automated test passes. Conversely, green automated tests do not
promote an unexecuted live row to pass.

### 4.3 Result summary

| Result | Rows |
| --- | --- |
| **PASS (RT/S)** — formal real-Telegram/synthetic-backend verification | R-07, R-08, R-09 (synthetic job only), R-10 |
| **PASS (O)** — owner-observed security denial for the named commands | R-02 (`/start`, `/menu`, `/jobs`) |
| **PARTIAL (O)** — observed surface, unproven guarantee | R-01, R-03, R-05, R-16 |
| **U** — unexecuted, pending or explicit exception | R-04, R-06, R-11, R-12, R-13, R-14, R-15 |
| **T** — retained real-Telegram evidence | none |
| **Production-worker / production-job evidence** | none |

The owner-attested and RT/S results are genuinely useful acceptance evidence, but
they are not a substitute for the unexecuted rows. The open rows are listed with
actions in §7 and §8.

### 4.4 Health-check semantics used by this report

A read-only health check was run at finalization and passed:

```text
mode: control
control unlock: not configured; relying on the numeric allowlist
authorized users: 1; allowed chats: 1
lock: ok - held by live monitor
preflight: NOT ready - a live monitor owns the lock; a second instance is refused
expectation: healthy running monitor verified
telegram getMe: ok; webhook: none
registry: ok (7 projects, 7 repositories, 7 docs roots)
warning: control mode relies on the Telegram user/chat allowlist only
dev-monitor check: passed
```

The check separates two concerns:

- **running-instance health** — is the holder of `monitor.lock` a verified live
  `dev_monitor.py run` process, with no competing monitor process targeting the
  same state directory?
- **start preflight** — could a new monitor safely acquire the lock now?

A legitimate healthy running instance is `lock: ok` and the default `check`
passes. It is simultaneously `preflight: NOT ready`, because starting a second
instance must remain refused. Use `--expect running` for a strict health probe
and `--expect start` for a strict preflight probe. A stale lock file is reported
but does not block a new start; an unknown lock owner or competing instances fail
closed. See the runbook for exact output and exit behavior. The health check is
not Telegram acceptance and does not prove any R-row.

## 5. Automated and synthetic test evidence

The final documentation job ran the complete gate from
`/home/iffi/dev-workspace/control-plane` at the code base above:

| Check | Command | Result |
| --- | --- | --- |
| Full unit/integration suite | `python3 -m unittest discover -s tools -p 'test_*.py' -q` | **474 tests, OK** |
| P4 monitor suite | `python3 tools/test_dev_monitor_p4.py -q` | **25 tests, OK** |
| P3 live acceptance harness tests | `python3 tools/test_p3_live_acceptance.py -q` | **29 tests, OK**; includes E1-E6, E7, R-07 and fail-closed cases |
| Control-plane validation | `python3 tools/validate_control_plane.py` | **passed; 100 active Markdown files, 442 relative links, 85 required files** |
| Agent permission validation | `python3 tools/validate_agent_permissions.py` | **PASS; 338 rules, 98 checks** |
| Skills validation | `python3 tools/validate_skills.py` | **passed; 23 active skills indexed exactly once** |
| Security validation | `python3 tools/validate_security.py --self-test`; `python3 tools/validate_security.py .` | **self-test passed; 241 files scanned** |
| Execution guard | `python3 tools/opencode_guard.py check` | **PASS**; one heavyweight execution (this job), Qortium read-only |

Relevant automated coverage includes:

- authorization and callback denial without job-data leakage;
- duplicate update IDs, cross-connection nonce reuse, expired/foreign
  confirmations, and per-user/per-chat action limits plus the hourly start cap;
- lifecycle, log, report, CLI-error and audit redaction;
- document traversal/absolute/encoded paths, hidden/sensitive names, symlink
  file/directory/root and list-to-open swap, FIFO, binary policy, size caps and
  no-write browsing;
- restart persistence of offset, seen updates, confirmation nonce and owner
  queue, plus notification dedupe across restart;
- transient, 429 and fatal polling faults plus update release after a failed
  action;
- job-directory symlink refusal;
- fake-CLI start, queue, cancel and resume with exactly-once queued delivery;
- P3 E1-E6 queue/cancel, E7 two-cancellation attempt-#2 delivery, R-07
  one-confirmation/two-replay rejection, and fail-closed verification of
  incomplete or fabricated evidence.

Automated and scripted results are not relabelled as RT/S or production-worker
evidence.

## 6. Operational safeguards and boundaries

The monitor's design and the observed runs preserve these safeguards:

- **No listener:** Telegram long polling with an outbound HTTPS client; no
  `setWebhook`, web server, public port or inbound API. The source-level test is
  an assertion, not a live host-invariant proof (R-15 remains U).
- **No Qortium/VPS mutation:** no `sudo`, service manager, package manager,
  network/mount configuration or Qortium control command. The monitor reads
  node PID/RSS only for reporting.
- **No name-based signalling:** cancellation goes only through the existing
  verified `dev cancel` guard-identity path.
- **Authorization:** numeric Telegram user ID and private chat ID allowlist,
  rechecked for every message and callback; unauthorized users receive a generic
  denial without job data.
- **Confirmation:** mutating actions require an explicit, one-time,
  owner/chat/action/expiry-bound confirmation; nonces are claimed atomically.
- **Read-only default:** `control` mode is explicit; the health check observed
  `mode: control` for the acceptance window. The owner should return to
  `read_only` after acceptance unless control is deliberately needed.
- **Credentials and redaction:** tokens, chat IDs and passphrase material are not
  written to reports, audit rows or chat; lifecycle text and job-derived fields
  pass the redaction boundary. Redaction remains pattern-based.
- **Document access:** trusted-root resolution with `O_NOFOLLOW` per component,
  regular files only, size caps, sensitive-name denial, and redaction for text
  previews/downloads.
- **Concurrency:** one verified monitor instance per state directory; the
  execution guard remains the one-heavyweight-execution authority; per-project
  admission serializes monitor-started jobs.
- **Rollback:** set `monitor.mode` back to `read_only`; stop the monitor through
  its documented service or flag path; restore the owner config from a private
  backup if changed; run `dev_monitor.py check`; remove only disposable test
  jobs, documents and symlinks. Never restart, stop or reconfigure Qortium, and
  never change VPS settings.

## 7. Remaining safe operator checklist

These actions remain owner-only. An agent must not execute them. Use only the
authorized private chat, prefer a disposable synthetic job, and never use a
production job, real wallet data, the Qortium node or a deliberately sensitive
production file as a test input.

| Step | Safe action | Expected outcome | Evidence capture | Stop / rollback |
| --- | --- | --- | --- | --- |
| 1. Baseline | Run the read-only preflight in §3. | The running monitor is healthy; no unexpected listener or Qortium change. | Sanitized check output, Qortium PID/RSS, listener list, UTC time. | `check --expect running` fails or Qortium/listener state is unexpected: stop, do not test. |
| 2. R-01 / R-03 menu, browsing and Refresh | Send `/start`, `/jobs`; open a harmless document; press Refresh twice on an unchanged view. | Menu and document view open; mode is visible; no token, chat ID or path leaks; Refresh gives explicit feedback. | Sanitized command/button labels, timestamps and result; no credentials. | Any secret or unexpected data appears: revert to `read_only` and stop. |
| 3. R-02 stale callback | With an owner-controlled non-allowlisted second account, press a stale callback in addition to the already-denied `/start`, `/menu` and `/jobs`. | Generic `Access denied.` only; no job, project, path or configuration data. | Sanitized denial text and timestamp. | Any data disclosure: stop and record a failed security row. |
| 4. R-05 redaction verification | Preview and download a harmless document with a disposable secret marker; compare the source hash before/after and inspect the redacted text. | The marker is removed from preview/download; the source hash and metadata are unchanged; no secret appears. | Sanitized before/after result and file hash; never a real credential. | Any unredacted marker or source change: stop and record a failed security row. |
| 5. R-04 traversal and symlink | Try absolute, `..`, backslash and percent-encoded paths. If needed, create one disposable symlink under the docs root and remove it afterwards. | Every attempt is refused; no file outside the trusted root is read. | Sanitized refusal result and timestamp. | Any successful escape: stop and record a failed security row. |
| 6. R-07 replay (already passed) | If a retained record is desired, re-run the P3 harness `--mode r07`; do not press the confirmation twice. | Exactly one cancellation; two rejected/deduplicated replays; final `CANCELLED`; cleanup; monitor active. | Retained private journal and `verify` output if desired. | A second side effect: stop and record a failed security row. |
| 7. R-08 / R-09 / R-10 retention (already passed) | If a retained record is desired, re-run the P3 harness `--mode e7`; queue one instruction, cancel, Resume, then cancel again. | Synthetic job only; exactly one queued instruction delivered into attempt #2; two cancellations; final `CANCELLED`, never `SUCCESS`. | Retained private `telegram-journal.jsonl`, `verify` output and timestamp. | Any production job, duplicate delivery or `SUCCESS`: stop and keep the failure record. |
| 8. R-11 failed resume | With a disposable synthetic job, queue an instruction and attempt a resume that is deliberately refused. | The instruction remains `[queued]`; nothing is delivered or lost. | Sanitized refusal and queued state. | A lost or duplicated instruction: stop and record a failure. |
| 9. R-12 restart persistence | With a disposable synthetic job `RUNNING`, restart only the monitor via its documented path. | The job continues; no duplicate STARTED/RESUMED/terminal message; offset, queue and confirmations survive. | Sanitized pre/post status, message counts and UTC time. | If Qortium is touched or messages duplicate: stop and record a failure. |
| 10. R-13 fault injection | Only if the owner deliberately injects a safe network fault; otherwise leave this as an unexecuted exception. | Polling backs off and recovers without losing updates or replaying an in-handler action. | Sanitized observed behavior and recovery time. | Any lost or replayed action: stop and record a failure. |
| 11. R-14 token rotation | Owner-only BotFather rotation, owner config update at `0600`, monitor restart, `check`. Never paste the token. | Old token fails cleanly; new token works after restart; no token in logs, chat, audit or reports. | Only "rotated and verified" plus timestamp; no token or hash. | Old token still works or a token appears: stop and record a failure. This report did not execute rotation. |
| 12. R-15 / R-16 host invariants and shutdown | Re-run the preflight; stop/start the monitor through its documented service or flag path. | No new monitor listener; Qortium PID/RSS and VPS configuration unchanged; graceful exit, released lock, unaffected jobs. | Before/after sanitized comparison, exit/status output, UTC time. | Any Qortium/VPS change or forced shutdown: stop and record a failure. Never use a name-based kill. |

Common rollback: set `monitor.mode` back to `read_only`; stop the monitor through
its documented service or flag path; restore the owner config from its private
backup if it changed; run `dev_monitor.py check`; remove only disposable test
jobs, documents and symlinks. Do not restart, stop or reconfigure Qortium, and do
not change VPS settings.

## 8. Remaining-risk register

| ID | Risk / unproven claim | Impact | Current mitigation / evidence | Action and owner |
| --- | --- | --- | --- | --- |
| RR-01 | Real token rotation (R-14) unexecuted. | A compromised or stale token's rotation readiness is unproven. | The monitor validates config permissions and does not print tokens; no token was read or changed. | Owner performs BotFather rotation, updates the owner-local config at `0600`, restarts through the documented path and runs `check`. Do not paste the token. |
| RR-02 | Deliberate network-fault recovery (R-13) unexecuted. | Real transient/429/fatal polling behavior under network faults is unproven. | Automated fault-injection tests pass; the poller uses a durable offset and does not replay in-handler actions in tests. | Owner may inject one safe fault or accept this as a documented exception. |
| RR-03 | Production-worker cancellation (R-09) unproven. | Cancellation of a real development run is not demonstrated. | R-09 passed against a synthetic forced-`CANCELLED` job; automated `dev cancel` tests use fake/test-owned processes. | Do not claim production cancellation. A future production test needs explicit owner authorization and a disposable job. |
| RR-04 | Host-invariant comparison (R-15) unexecuted. | No before/after proof that the monitor opened no listener or left Qortium/VPS unchanged during the real runs. | Static source assertion and architecture boundary only; the health check observed no webhook. | Owner captures baseline and post-run Qortium PID/RSS, listeners and VPS config, then compares. |
| RR-05 | Redacted download content and source invariance (R-05) not independently verified. | A download could deliver a redacted filename without proving secret removal or an unchanged source. | The owner opened `README.redacted.md` on Android; automated tests cover redaction and source hashes. | Owner repeats with a harmless disposable marker, inspects the redacted text and compares source hashes. |
| RR-06 | Running-job restart persistence (R-12) unexecuted. | Offset, queue, nonce and notification dedupe across a restart with a `RUNNING` disposable job are unproven. | Restart tests pass in isolation; the owner observed monitor stop/start around synthetic runs. | Run the disposable running-job restart check in §7 step 9. |
| RR-07 | Failed-resume queue retention (R-11) unexecuted. | A refused resume could theoretically lose or duplicate a queued instruction in real use. | Automated `test_failed_resume_keeps_the_queue_queued` passes. | Run the synthetic refused-resume check in §7 step 8. |
| RR-08 | Live traversal/symlink and real-start paths (R-04, R-06) unexecuted. | Isolated tests may not cover the owner's actual docs layout or a real OpenCode start. | Automated document-hardening and fake-CLI start tests pass; the monitor uses `O_NOFOLLOW` and trusted roots. | Optionally exercise disposable traversal fixtures and a disposable real start under owner control. |
| RR-09 | Cleaned synthetic evidence leaves no retained journal/IDs/timestamps. | Later forensic review cannot independently re-inspect the exact R-07/E1-E7 messages. | The runs passed formal `verify`; this report records only the observed outcomes and invents nothing. | If retention matters, re-run the harness and keep the private sanitized journal. |
| RR-10 | Control mode currently relies on the numeric allowlist only; no `control_passphrase_hash` is configured. | A stolen authenticated Telegram session has no local second factor for mutating actions. | Owner-only private chat, numeric allowlist, one-time confirmations, rate limits and read-only default. | Before sustained/high-consequence control use, configure a strong unique `control_passphrase_hash` and keep the config at `0600`. |
| RR-11 | Redaction is pattern-based; hardlinks inside an owner-controlled docs root remain a residual risk. | A crafted file name/content or hardlink could evade the pattern boundary. | Sensitive-name denial, regular-file checks, `O_NOFOLLOW`, size caps and tests; owner controls docs roots. | Keep docs roots owner-controlled; avoid hardlinks; extend redaction tests for any new sensitive pattern. |
| RR-12 | Rate limits and monitor state are local SQLite data and reset if monitor state is deleted. | Deleting monitor state during a control window removes rate-limit history. | Bounded per-user/per-chat/minute and hourly start caps; state is private. | Do not delete monitor state during an active control window; treat state deletion as a deliberate reset. |
| RR-13 | A simultaneous CLI-started job is serialized only by the global execution guard, not a per-repository worker lock. | Two jobs could contend for one repository outside the monitor's per-project admission. | The global guard remains authoritative for one heavyweight execution; monitor admission is per project. | Keep the global guard; consider a future v3 per-repository worker lock. |

A failed security row (authorization, redaction, traversal/symlink, cancel
identity or duplicate side effect) blocks acceptance. Real token rotation and
deliberate network-fault injection remain explicit unexecuted exceptions until
the owner performs them.

## 9. Optional `control_passphrase_hash` assessment

**Decision: recommended for control mode; not enabled or changed by this job.**
The final health check observed `control unlock: not configured`, so control
currently relies on the numeric allowlist and one-time confirmations. Read-only
mode does not need the passphrase. The owner should add a strong, unique
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

## 10. Evidence capture

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

For the already observed real-bot E1-E7 and R-07 runs whose temporary directories
were cleaned, record only "observed; harness formal verification passed; temporary
evidence not retained". Do not reconstruct unavailable message IDs, update IDs,
timestamps or reports, and do not present RT/S evidence as production-worker
evidence.

Do not copy the owner-local `telegram.json` or monitor SQLite database into Git or
a report.

## 11. Owner sign-off

| Field | Value |
| --- | --- |
| Owner | |
| Date / time (UTC) | |
| Application/code SHA under acceptance | `6efcd2a1bb782910bd2e33b0f6711912f36b5e74` (report base; final documentation commit recorded in the task STATUS) |
| Monitor version | `0.4.0-p4` |
| Mode (`read_only` / `control`) | `control` observed at finalization; revert to `read_only` unless deliberately needed |
| Rows passed with retained evidence (T) | 0 |
| Rows observed as RT/S or owner-attested | R-02, R-07, R-08, R-09, R-10 (plus partial observations R-01, R-03, R-05, R-16) |
| Rows failed, unexecuted or explicit exceptions | R-04, R-06, R-11, R-12, R-13 (exception), R-14 (exception), R-15 (exception); R-09 production-worker cancellation unproven |
| Reason for any exception | See §4.2 and §8: token rotation, network fault injection, production-worker cancellation, host-invariant comparison and the other live checks were not executed. |
| Rollback performed? | No production rollback was required for this documentation job. The isolated synthetic fixtures were cleaned and the monitor was observed active afterwards. |
| Remaining risk accepted? | Owner decision: ______________________________ |
| Owner signature / decision | |

A failed security row blocks acceptance. Revert `monitor.mode` to `read_only`,
stop the monitor through its documented path, and record the failure without
modifying Qortium or VPS configuration. Real token rotation and deliberate
network fault injection remain explicit unexecuted exceptions until the owner
performs them.

## 12. Handoff summary

- **What changed:** this report replaces the previous P4 acceptance checklist
  with a final evidence matrix for R-01 through R-16, the owner's observed
  real-Telegram/synthetic-backend results, explicit partial/unexecuted states,
  the current health semantics, an actionable risk register and an owner
  sign-off section. The P3 harness status and architecture note were corrected
  to record the completed R-07 and E1-E7 runs without inventing cleaned evidence.
- **Validation:** see §5 and the job evidence file for the final full-suite,
  control-plane, permissions and guard results.
- **Delivery:** the documentation commit and verified `dev-control-plane` remote
  SHA are recorded in
  `tasks/orchestration/qortium-dev-monitor-p4-final-acceptance-20261101/STATUS.json`.
  No merge, force-push, deploy, QDN write, wallet transaction, service or
  Qortium/VPS change was performed.
- **Owner next actions:** sign §11; optionally perform R-13 and R-14; retain a
  sanitized journal if desired; optionally complete the remaining safe checklist
  rows; add a control passphrase hash before sustained control use; revert to
  `read_only` when the acceptance window ends.
- **Do not claim:** production-worker execution, production-job delivery,
  production cancellation, retained P4 journal evidence, real token rotation or
  host-invariant comparison unless the corresponding owner action is actually
  performed and recorded.
