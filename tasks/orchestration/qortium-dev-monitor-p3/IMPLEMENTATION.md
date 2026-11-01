# Implementation — workspace/qortium-dev-monitor-p3

Executing agent (actual executor of the work): DeepSeek
(`deepseek/deepseek-flash`) through the owner-authorized Workflow v3 job
`20261101T061959Z-qortium-dev-monitor-p3-961a2a11`.

Report/handoff writer (if different from the executing agent): same agent.

Exact application repository / branch / SHA:
`/home/iffi/dev-workspace/control-plane`,
`agent/control-plane/workflow-v3-20261031`, implementation commit
`ca88cb862352e8391e62a4831f39f6c06d6dd005` (base `71c3382`).

Verdict and measurable acceptance achieved:
P3 is implemented and automated validation passes. Cancellation is additive,
identity-verified and resumable. Owner instructions are durable, explicitly
state-tracked and delivered at the resume boundary. P1/P2 behaviour,
notification deduplication, admission serialization and security boundaries are
preserved. The active monitor service was not restarted, owner-local credentials
were not modified and no deployment occurred. Live Telegram owner acceptance
remains pending.

## 1. What changed

### Workflow v3 (additive)

- `CANCELLED` added to `JOB_STATES`, terminal states and notification states.
- `dev cancel <job-id> [--json] [--grace SECONDS]`:
  - refuses anything that is not `RUNNING` with a live worker;
  - revalidates the recorded guard PID against `/proc/<pid>/cmdline`
    (`opencode_guard.py run`, the exact job ID, run log or session title);
  - refuses PID 1, the cancelling process group and detected Qortium processes;
  - writes a durable `cancel.requested.json` scoped to the current attempt and
    appends `cancel_requested` before signalling;
  - sends `SIGTERM` to that exact guard PID only;
  - waits a bounded grace period and never escalates to a name-based kill;
  - skips acceptance commands, writes `CANCELLED` plus `report.md`, and preserves
    the working tree and OpenCode session;
  - reconciles or finalizes a matching cancellation if the worker disappears;
  - never applies an old cancel marker to a later resumed attempt.
- `dev resume --prompt-file -` reads a long instruction from standard input.
- Worker observes the cancel marker after the guard exits, appends
  `cancel_observed`, and finishes as `CANCELLED`.
- `dev status` exposes `cancelled_at`; reports and notifications include the new
  terminal state.

### Qortium Dev Monitor

- Control-mode cancel flow with preview, exact worker/guard PIDs and a one-time
  confirmation. The monitor never signals a process directly.
- Job menu shows `Cancel job` only for a RUNNING job with a live worker and
  `Queue instruction` in control mode.
- `MonitorState.owner_messages` stores queued instructions with
  `delivery_state` (`queued`/`delivered`), `delivered_at`, `delivered_attempt`
  and a short redacted error.
- `/queue [job]` and `/messages [job]`; `Queue instruction` button; pending count
  shown in job status.
- Resume preview lists queued instructions and the final confirmation shows how
  many are included. The monitor composes the base instruction plus a delimited
  owner-follow-up block and invokes `dev resume --prompt-file -`.
- Messages are marked delivered only after Workflow v3 accepts the resume. A
  refused or failed resume keeps them queued.
- An unknown OpenCode session still requires the explicit New session toggle.
- `CANCELLED` is a terminal lifecycle state for notification relay/dedup.
- Config adds `owner_message_max_chars`, `owner_message_retention_seconds` and
  honours `queue_owner_messages`. Delivered instructions are pruned after
  retention; queued instructions are not silently expired.

### Documentation

- `docs/operations/QORTIUM-DEV-MONITOR.md` is now the P3 runbook with activation,
  cancel, queue, resume, troubleshooting and owner acceptance steps.
- `docs/operations/QORTIUM-DEV-MONITOR-ARCHITECTURE.md` records P3 as implemented.
- `docs/operations/DEV-WORKFLOW-V3.md` documents `CANCELLED`, `dev cancel` and
  `dev resume --prompt-file -`.

## 2. Safety review

- No `setWebhook`, listener, webhook helper or inbound API was added.
- No `sudo`, service manager, global package install, Qortium command or node
  file write was added.
- The only process signal in the new code is `os.kill(verified_guard_pid,
  SIGTERM)` inside `cancel_job`. It is preceded by `/proc` identity validation
  and is scoped to the job's own guard.
- The monitor still passes arguments as arrays with `shell=False`; owner text is
  never executed as a shell command. Acceptance commands remain the only
  intentional shell surface, owned by Workflow v3 and previewed before start.
- Owner message bodies are stored only in private monitor SQLite and are never
  written to the sanitized audit table. Delivery errors are redacted.
- Notification keys remain durably claimed before send; `CANCELLED` uses the same
  terminal deduplication path as existing states.
- Per-project admission and the global execution guard are unchanged. Cancellation
  acquires the per-project admission lock during its check-and-invoke section.

## 3. Evidence

Commands run from `/home/iffi/dev-workspace/control-plane`:

```bash
python3 tools/test_dev_cancel.py
python3 tools/test_dev_monitor_p3.py
# and every other tools/test_*.py module
python3 tools/validate_control_plane.py
python3 tools/validate_skills.py
python3 tools/validate_security.py --self-test
python3 tools/validate_security.py .
python3 tools/validate_agent_permissions.py --check
python3 tools/opencode_guard.py check
```

Results:

- `test_dev_cancel.py`: 6 tests, OK.
- `test_dev_monitor_p3.py`: 10 tests, OK.
- Full unittest suite: 320 cases across 20 modules, OK; the security-hook test
  script also passed.
- Control-plane validator: 54 Markdown files, 210 relative links, 57 required
  files.
- Skills validator: 17 active skills indexed exactly once.
- Security validator: self-test passed; 169 files scanned.
- Agent permission validator: PASS (337 rules, 97 checks).
- Execution guard: PASS; one heavyweight execution and readonly Qortium
  detection reported normally.

No real Telegram request, OpenCode session, job signal, Qortium call or VPS
change was made by the tests. Signal tests used test-owned child processes.

## 4. Activation

The active monitor service was deliberately **not** restarted or changed. To
activate P3:

1. Review the P3 diff and confirm the owning branch:
   `git show --stat ca88cb8`.
2. Keep `~/.config/dev-control-plane/telegram.json` mode `0600`. Optionally add:
   `"events": [..., "CANCELLED"]`, `queue_owner_messages`, `owner_message_max_chars`
   and `owner_message_retention_seconds` inside the nested `monitor` object.
3. Run the read-only preflight:
   `python3 tools/dev_monitor.py check`.
4. Restart the monitor so the new code is loaded. For the owner-installed user
   unit use the normal owner service procedure; for a foreground monitor use
   `Ctrl-C` and start it again. Running Workflow v3 jobs are detached and are not
   affected.
5. No Workflow v3 worker restart is needed; new CLI invocations use the new code.
   Already-running jobs keep their current worker, but their job store remains
   compatible.

Do not deploy, merge, restart Qortium or change VPS configuration as part of
activation.

## 5. Owner acceptance

In the authorized private chat:

1. Confirm `dev cancel <terminal-job>` refuses with a sanitized error and sends
   no signal.
2. Start a small control-mode job. Verify `Cancel job` appears only while the
   job is RUNNING with a live worker.
3. Queue an instruction while running. The reply must state delivery happens on
   the next resume, not live.
4. Cancel the job. Verify `CANCELLED` arrives once, the worktree is unchanged and
   the job remains resumable.
5. Resume the cancelled job. The preview must list the queued instruction and the
   confirmation must show it included. `/messages <job>` must show it delivered
   at the new attempt.
6. Force a failed or refused resume with a newly queued instruction and verify it
   stays queued.
7. Resume a job with no known OpenCode session and verify the explicit New
   session toggle is required.
8. Restart the monitor during a running job and verify no duplicate
   STARTED/RESUMED/terminal notification.

## 6. Preserved owner work

The following pre-existing changes were left untouched and unstaged:

```text
 M deploy/systemd/user/qortium-dev-monitor.service
 M skills/README.md
 M skills/qortium/home2-qdn-publishing/SKILL.md
 M skills/qortium/qdn-resource-discovery/SKILL.md
?? skills/shared/browser-thumbnail-generation/
```

No reset, clean, stash, checkout, relocation or destructive cleanup was run.

## 7. Remaining findings / next actor

Next actor: owner. Remaining work is live activation and acceptance, followed by
a P4 hardening pass (real-runtime matrix, incident runbook and any binary document
policy change). No further P3 code change is justified before that evidence.
