# Qortium Dev Monitor — P3 live Telegram acceptance harness

Status: **implemented and covered by isolated regression tests. The live
Telegram run is explicit operator work and was not executed by the implementing
agent.**

| Field | Value |
| --- | --- |
| Executing agent | `DeepSeek` (`deepseek/deepseek-flash`) through the owner-authorized Workflow v3 job |
| Report/handoff writer | `DeepSeek` (same agent) |
| Artifact type | Operations runbook / acceptance harness |
| Project scope | Cross-project Workflow v3 control plane (`workspace` material) |
| Canonical path | `docs/operations/QORTIUM-DEV-MONITOR-P3-LIVE-ACCEPTANCE.md` |
| Harness CLI | [tools/p3_live_acceptance.py](../../tools/p3_live_acceptance.py) |
| Harness implementation | [tools/devmonitor/acceptance.py](../../tools/devmonitor/acceptance.py) |
| Regression tests | [tools/test_p3_live_acceptance.py](../../tools/test_p3_live_acceptance.py) |
| Monitor runbook | [QORTIUM-DEV-MONITOR.md](QORTIUM-DEV-MONITOR.md) |
| P4 owner checklist | [QORTIUM-DEV-MONITOR-P4-ACCEPTANCE.md](QORTIUM-DEV-MONITOR-P4-ACCEPTANCE.md) |
| Control-plane contract | [AGENTS.md](../../AGENTS.md), [WORKFLOW.md](../../WORKFLOW.md), [GIT-AND-HANDOFF.md](../../GIT-AND-HANDOFF.md) |

## 1. Purpose

The P3 live harness verifies the two P3 Telegram control flows end to end through
the **real authorized Telegram bot**:

1. **Queue instruction** stores an owner instruction durably and does not inject
   it into a running turn.
2. **Cancel job** shows the verified preview, requires the one-time confirmation
   and produces `CANCELLED` through `dev cancel`.
3. **Resume delivery (E7 mode)** keeps the isolated poller alive after the first
   cancellation, delivers exactly one queued instruction into synthetic attempt
   #2 through the real Resume wizard, and stops only after a second cancellation.

The harness exercises the real monitor router, authorization, callback handling,
confirmation nonces, renderers and Telegram Bot API. It replaces only the
backend that could cause a real development effect:

- the project is a throw-away Git repository under the harness work directory;
- the project registry is a generated temporary file with one synthetic project;
- the monitor configuration is a private copy of the owner config with isolated
  paths;
- the Workflow v3 CLI is a deterministic fake that only returns `RUNNING` or
  `CANCELLED`;
- the monitor and job state directories are temporary.

The synthetic job can never become `SUCCESS` or `FAILED`. It is forced to
`CANCELLED`, and every report is labelled synthetic.

## 2. What this proves and what it does not prove

Proves, when the operator completes the run:

- the real bot and the authorized private chat can reach the monitor code;
- the real callback round-trip works for `Queue instruction` and `Cancel job`;
- the one-time confirmation flow works through real Telegram callbacks;
- a queued instruction is stored with an explicit `queued` state and can be
  delivered exactly once through a resume;
- the cancel path produces `CANCELLED` without a production job or process;
- the owner Telegram config and the production project registry are unchanged.

Does not prove:

- that a real OpenCode development job succeeds;
- paid model behaviour, acceptance-command execution or Git delivery;
- that the running Qortium node performed any action;
- that the production monitor service is healthy (run
  `dev_monitor.py check` separately);
- authorization of a production job, deployment, QDN write, wallet transaction
  or merge.

A passing live run is **not** a development success. Do not copy its synthetic
job or report into a production delivery record.

## 3. Safety boundaries

The harness must not:

- edit `~/.config/dev-control-plane/telegram.json`;
- edit the production `PROJECT-REGISTRY.md`;
- write to the live monitor database or the live Workflow v3 job store;
- start a second poller while the production monitor is running;
- restart, stop or reconfigure the production monitor service automatically;
- start OpenCode, invoke a paid model or use a production project;
- send a signal, install a service, open a listener, touch the Qortium node or
  change VPS configuration;
- copy the bot token, chat ID or private monitor database into Git or a report.

The owner stops and restarts the production monitor manually through the
documented service/foreground path. The harness only checks the monitor lock and
refuses to run while the production monitor holds it.

## 4. Fail-closed preconditions

`prepare` and `run` refuse the test when any condition is not provable:

| Condition | Result |
| --- | --- |
| Source config is missing, not a regular file, or group/world accessible | Refuse |
| Source `monitor.mode` is not `control` | Refuse |
| `queue_owner_messages` is disabled | Refuse |
| Source config has no bot token | Refuse |
| Source project registry is missing | Refuse |
| Production monitor lock is held | Refuse |
| Work directory is inside production state or the control-plane checkout | Refuse |
| Temporary monitor config does not validate | Refuse |
| Telegram `getMe` fails, or a webhook is configured | Refuse |
| Production monitor state is missing, so its update offset cannot be proved | Refuse |
| Pending Telegram updates exist beyond the production monitor offset | Refuse; drain them first |
| Another isolated poller already owns the temporary state lock | Refuse |
| E7 is requested without an E7-prepared fixture | Refuse; re-prepare with `--mode e7` |
| Synthetic job is missing, non-synthetic state appears, or the final state is not `CANCELLED` | Verification fails |
| E7 has fewer than two cancellations, no exact attempt-#2 delivery, or a duplicate delivery | Verification fails |

No refusal is silently downgraded to a partial success.

## 5. Prepare the fixture

The source config is read only. The harness copies it, keeps the real bot token
inside the private temporary copy, and rewrites only isolated paths.

```bash
cd /home/iffi/dev-workspace/control-plane
python3 tools/p3_live_acceptance.py prepare \
  --work-dir /tmp/p3-telegram-live \
  --source-config "$HOME/.config/dev-control-plane/telegram.json"
```

The default `--mode e1-e6` preserves the original queue/cancel acceptance flow:
the isolated poller stops at the first `CANCELLED`. For the full resume lifecycle,
prepare explicitly with E7 mode:

```bash
python3 tools/p3_live_acceptance.py prepare \
  --work-dir /tmp/p3-telegram-live \
  --source-config "$HOME/.config/dev-control-plane/telegram.json" \
  --mode e7
```

The mode is recorded in `manifest.json`; `run`, `status` and `verify` use that
recorded mode. The command prints the synthetic job ID, mode, isolated paths and
the next steps. It does **not** contact Telegram.

The generated layout is:

```text
/tmp/p3-telegram-live/
  .p3-live-acceptance          # harness marker required by cleanup
  manifest.json                # no token; paths and source hashes
  telegram.json                # 0600 copied config with isolated paths
  PROJECT-REGISTRY.md          # only synthetic/p3-live-acceptance
  projects/p3-live-acceptance/ # throw-away Git repository
  docs/                        # empty isolated docs root
  job-state/                   # synthetic Workflow v3 state
  monitor/                     # isolated monitor SQLite state
  fake_dev.py                  # deterministic fake CLI
  evidence/
    telegram-evidence.json     # operator fills the UNRECORDED fields
    TELEGRAM-EVIDENCE.md       # interaction script
    telegram-journal.jsonl     # automatic callback/message evidence
```

## 6. Run the isolated live poller

1. Stop the production monitor through its documented path. Do not use the
   harness to stop it. Do not stop or restart Qortium.
2. Start the isolated poller with an explicit confirmation flag:

```bash
python3 tools/p3_live_acceptance.py run \
  --work-dir /tmp/p3-telegram-live \
  --confirm-live-telegram
```

The isolated poller uses the copied real bot token, the real authorized user/chat
allowlist and the real Telegram API. It long-polls the same bot, so the
production monitor must remain stopped for the whole run. If the production
monitor starts again, Telegram returns `409 Conflict` and the run fails; it does
not fall back to another bot or token.

Before polling, the harness reads the production monitor's persisted
`update_offset` read-only and checks that no later Telegram updates are still
pending. If pending updates exist, it refuses rather than replaying stale
production buttons in the isolated state. Let the production monitor drain them
cleanly, stop it again and retry. The harness initializes only the temporary
monitor offset from that value; it never writes the production database.

In the default `e1-e6` mode the poller stops when the synthetic job first reaches
`CANCELLED`. In `e7` mode it deliberately remains active after that first
cancellation so the owner can press `Resume`; it stops only after the second
cancellation is recorded. An absolute `--timeout` (default 900 seconds, minimum
30) bounds the whole run, so a missing Resume or second cancel cannot hang the
poller indefinitely. Use `Ctrl-C` for a manual stop; the synthetic job is
temporary and cleanup removes it.

Do not restart the poller halfway through E7. The lifecycle requires exactly one
resume and exactly two cancellations in the same isolated run.

## 7. Required Telegram interactions

Perform these actions in the owner's authorized private chat with the real bot.
The automatic journal records the observed message IDs, update IDs, button
labels, callback labels and timestamps. Do not try to type callback data; use the
buttons. Do not press old production-job buttons during the run: the isolated
monitor cannot resolve production references, and the test must use only the
synthetic job's messages.

| ID | Action | Expected observation |
| --- | --- | --- |
| E1 | Send `/jobs` and open the entry whose title starts with `[SYNTHETIC]` | Exactly one synthetic job; no production job is used |
| E2 | Inspect the job view | Buttons `Queue instruction` and `Cancel job` are visible |
| E3 | Press `Queue instruction` and send the instruction containing `P3-TELEGRAM-LIVE-ACCEPTANCE` | Reply says `Instruction queued` / `Queued for the next resume: 1`; delivery is explicitly not live |
| E4 | Send `/messages <job-id>` | The instruction appears as `[queued]` and says it will be delivered on the next resume |
| E5 | Return to the job and press `Cancel job` | Preview says `Cancel this running job?` and names only the synthetic job |
| E6 | Press `Confirm: Cancel running job` | Reply says `Cancel result: cancelled`; the job view shows `CANCELLED` |
| E7 | In `--mode e7`: press `Resume`, `Confirm resume`, `Confirm: Resume job`, then cancel the synthetic job again | Resume preview lists exactly one queued instruction; after resume it is delivered once at attempt #2 and marked `[delivered]`; the poller stops only after the second `Cancel result: cancelled` |

E7 is mandatory for a fixture prepared with `--mode e7`. The fake resume prompt
contains the queued instruction; it never starts OpenCode. The first cancel is
not a terminal acceptance result in E7 mode. Cancelling again is required so
verification can prove exactly one delivery into attempt #2 and a terminal
synthetic state with no success. A run that stops after the first cancel, resumes
more than once, or records a duplicate instruction is not an E7 pass.

## 8. Evidence requirements

The harness requires precise interaction evidence, not a screenshot-only claim.
`telegram-journal.jsonl` is written automatically from the real Telegram
updates and outbound messages. It records:

- Telegram `update_id` and `message_id`;
- callback button labels such as `Queue instruction`, `Cancel job` and
  `Confirm: Cancel running job`;
- sanitized outbound text and button labels;
- the presence of the synthetic instruction token.

Edit `evidence/telegram-evidence.json` and replace every `UNRECORDED` value:

| Field | Required value |
| --- | --- |
| `operator` | Registered role or owner identity that performed the interaction |
| `started_at_utc` | Real start time in `YYYY-MM-DDTHH:MM:SSZ` form |
| `finished_at_utc` | Real end time in `YYYY-MM-DDTHH:MM:SSZ` form |
| `no_success_observed` | `true` only if the synthetic job never showed SUCCESS |
| `production_untouched` | `true` only if the production registry/config/job store were untouched |
| `qortium_unchanged` | `true` only if the Qortium PID/state was unchanged |
| `notes` | Optional short note; no token, chat ID or production job data |

Keep the `job_id` and `synthetic_marker` values. Do not edit the journal by hand
to invent an interaction; verification cross-checks the job state, events, owner
message table and fake resume prompt.

## 9. Verify

```bash
python3 tools/p3_live_acceptance.py verify \
  --work-dir /tmp/p3-telegram-live
```

Verification passes only when all of the following hold:

- the source config and production registry SHA-256 hashes are unchanged;
- only synthetic job records exist in the isolated job state;
- the synthetic job is `CANCELLED`, never `SUCCESS`, `FAILED`, `BLOCKED` or
  `TIMEOUT`;
- the job events include `cancel_requested`, `cancel_observed` and
  `finished state=CANCELLED`;
- the fake `dev cancel` invocation was recorded for that job;
- the owner instruction contains `P3-TELEGRAM-LIVE-ACCEPTANCE` and is `queued`,
  or, for E7, exactly one matching instruction is `delivered` after exactly one
  recorded resume whose prompt contains it;
- for E7, the job records exactly two attempts (`#1`, `#2`), exactly one resume,
  exactly two `cancel_observed` events (attempt #1 and attempt #2), exactly two
  fake cancel calls and one fake resume call; the delivered instruction has
  `delivered_attempt = 2`;
- for E7, the journal shows exactly one Resume preview/confirmation pair, exactly
  one `Queued instructions included: 1`, and two cancel previews/results;
- the journal contains the required buttons, callbacks and confirmation labels;
- the operator evidence has no `UNRECORDED` value and all attestations are true.

E7 verification fails closed when any of those conditions is missing, when more
than one token-bearing instruction or resume is recorded (duplicate delivery), or
when the synthetic job reaches `SUCCESS`. A report may say `delivered` only when
the durable owner-message row proves attempt #2 delivery.

A pass writes `evidence/report.json` and `evidence/REPORT.md`. Both are
synthetic evidence and must never be presented as a real development delivery.

## 10. Cleanup and rollback

```bash
python3 tools/p3_live_acceptance.py cleanup \
  --work-dir /tmp/p3-telegram-live
```

Cleanup refuses if the isolated poller still holds its lock and refuses any
directory without the harness marker. It removes only the temporary fixture.

After cleanup:

1. Restart the production monitor manually through its documented path.
2. Run `python3 tools/dev_monitor.py check` and record the sanitized result.
3. Do not delete or modify production job state, monitor state or Qortium files.

If the production monitor was already running, `prepare` refuses before creating
the fixture. If it starts during the run, stop the run, clean the fixture and
retry only after the production monitor is stopped deliberately.

## 11. Relationship to the P4 checklist

Use this harness for R-08 (queue an instruction) and R-09 (cancel only the
disposable job) when the owner wants a deterministic synthetic backend. The full
P4 checklist remains authoritative for authorization, redaction, document
traversal, restart persistence, polling faults, token rotation, no-listener and
no-Qortium-change checks.

The harness does not replace the P4 checklist and does not authorize a live
production job.

### 11.1 Verified synthetic E1-E7 results reused by P4

The repository has verified automated E1-E7 synthetic coverage in
[`tools/test_p3_live_acceptance.py`](../../tools/test_p3_live_acceptance.py):

- E1-E6 queue/cancel through the real router with a scripted transport
  (`test_live_flow_queue_and_cancel_produces_verifiable_evidence`);
- the explicit E7 two-cancellation lifecycle with exactly-once attempt-#2
  delivery (`test_e7_waits_for_resume_then_stops_only_after_second_cancel`);
- fail-closed rejection of incomplete E7, duplicate delivery, false success,
  unrecorded evidence, changed sources and non-synthetic jobs;
- the default E1-E6 run still stops after the first cancellation.

The P4 acceptance matrix cites these results as **S — synthetic P3 E1-E7**. They
prove the synthetic queue/cancel/resume contract only. They do **not** prove
real production-job delivery, real OpenCode execution, real Telegram journal
capture or every P4 row. The real-bot E1-E7 run described above remains
unexecuted and owner-only; no live `telegram-evidence.json` or journal is stored
in this repository.

## 12. Troubleshooting

| Symptom | Action |
| --- | --- |
| `production monitor is running` | Stop it manually through its documented path; the harness never stops or restarts it |
| `source monitor mode must be 'control'` | Enable control mode deliberately in the owner config, then re-run `prepare` |
| `queue_owner_messages disabled` | Enable queuing deliberately, then re-run `prepare` |
| `source config ... group/world accessible` | Set the owner config to mode `0600` |
| `Telegram preflight failed` | Check network and token validity; never print the token |
| `a Telegram webhook is configured` | Clear the webhook explicitly before long polling |
| `409 Conflict` | Another poller is active; stop the production monitor deliberately |
| `timed out ... before ... lifecycle` | The synthetic job did not reach the mode's terminal condition; no success is claimed. Inspect `status`, then retry or clean up |
| `resume acceptance requires ... --mode e7` | The fixture was prepared for E1-E6. Re-prepare with `--mode e7`; do not extend an E1-E6 run |
| `final state is RUNNING` | A resume was performed without a final cancel; cancel the synthetic job again |
| `E7 requires exactly two recorded cancellations` | The poller/operator stopped after the first cancel. Re-run E7 and perform the second cancel |
| `E7 requires ... delivered by the resume` | The Resume wizard did not deliver the queued instruction; inspect the preview/journal and retry the resume |
| `E7 requires exactly one owner instruction` | A duplicate token-bearing instruction was queued; clean up and re-prepare |
| `no queued owner instruction contains ...` | The instruction text did not include the synthetic marker; repeat E3 |
| `non-synthetic job found` | Do not mix production job state into the fixture; clean up and re-prepare |
| `isolated monitor is still running` | Stop it with its stop flag or `Ctrl-C`, then clean up |
