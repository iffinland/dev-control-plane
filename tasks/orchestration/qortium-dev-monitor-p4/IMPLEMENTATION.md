# Implementation — workspace/qortium-dev-monitor-p4

Executing agent (actual executor of the work): DeepSeek
(`deepseek/deepseek-flash`) through the owner-authorized Workflow v3 job
`20261101T064540Z-qortium-dev-monitor-p4-hardening-72a27d10`.

Report/handoff writer (if different from the executing agent): same agent.

Exact application repository / branch / SHA:
`/home/iffi/dev-workspace/control-plane`,
`agent/control-plane/workflow-v3-20261031`, implementation commit
`80fae75a3c7d97754c480a92f4c95d8d6aed6a81` (base `6b8bc7d`).

Verdict and measurable acceptance achieved:
P4 hardening is implemented and automated validation passes. P1-P3 behavior is
preserved, the P3 detector misclassification is corrected, and the real-runtime
owner matrix is documented but not executed by the agent. The active monitor
service was not restarted, owner-local credentials were not modified, no actual
Telegram action was sent and no live job was cancelled.

## 1. P3 false-classification investigation

The P3 job `20261101T061959Z-qortium-dev-monitor-p3-961a2a11` was marked
`BLOCKED` with:

```text
missing_dependency: FileNotFoundError: [Errno 2] No such file or directory:
'/home/iffi/.local/state/dev-control-plane/jobs/20261101T120000Z-cancel-test-12345678/job.json'
```

The excerpt came from a real failing `test_dev_cancel.py` run. That test had a
real fixture problem and was fixed during P3; the job failure itself was not
false. The classification was false: a test fixture's missing data file is not a
missing command, module or dependency.

Correction:

- the generic `missing_dependency` pattern no longer treats every
  `No such file or directory`, `ENOENT` or `FileNotFoundError` as a dependency;
- shell-style exec failures such as `bash: /opt/tool: No such file or
  directory`, `/usr/bin/env: 'python3': No such file or directory` and
  `dash: 1: tool: not found` remain `missing_dependency`;
- `command not found`, missing-module errors and `missing dependency` text remain
  `missing_dependency`;
- a Python/Node traceback naming an ordinary missing data file is now a
  `failed_command`, so the real failure is not hidden;
- `tools/test_detect.py` covers the exact P3 excerpt, a failed console block, real
  shell/module/dependency positives and a missing regular file negative.

## 2. What changed

### Monitor hardening

- `LifecycleNotifier` redacts STARTED/RESUMED/terminal/alert text before sending;
  job-derived title, blocker and alert detail can no longer bypass redaction.
- `MonitorConfig` adds `max_actions_per_minute`,
  `max_actions_per_chat_per_minute` and `max_starts_per_hour` with bounded
  defaults.
- `Router` enforces both per-user and per-chat action budgets.
- `ControlManager.perform_start` enforces the hourly start cap inside the
  per-project admission critical section.
- `MonitorState.consume_confirmation` claims a nonce with one conditional
  `UPDATE`, so a replayed or concurrent confirmation cannot be consumed twice.
- `JobFacade.job_dir` rejects a symlinked job directory or a resolved path outside
  the job store before deriving log/report/event paths.
- Queued owner-message delivery records the resumed attempt number returned by
  Workflow v3, with the previous-attempt fallback.

### Tests

- New `tools/test_dev_monitor_p4.py` (25 tests) covers authorization denial without
  data leakage, duplicate update handling, atomic/expired/foreign confirmations,
  per-user and per-chat limits, hourly start cap, lifecycle and log/report/audit
  redaction, CLI error redaction, document traversal fuzzing, hidden/sensitive
  names, symlink file/directory/root and symlink swap, FIFO and binary policy,
  size caps, no-write browsing, restart persistence, notification dedupe across
  restart, transient/429/fatal polling faults, action-failure release, job
  directory symlink refusal, and fake-CLI start/queue/cancel/resume integration.
- `tools/test_detect.py` gains the detector regression class described above.
- `tools/test_dev_cancel.py` waits for freshly spawned test children to exec before
  exercising verified cancellation, removing a `/proc` readiness race in the test
  harness. Production refusal behavior is unchanged.
- `tools/devmonitor_test_support.py` fixes the fake `dev start` helper so the new
  job is visible to a subsequent fake `status --all`.

### Documentation

- `docs/operations/QORTIUM-DEV-MONITOR.md` is the P4 runbook with new limits,
  validation commands, incident response, token rotation and deployment /
  rollback guidance.
- `docs/operations/QORTIUM-DEV-MONITOR-P4-ACCEPTANCE.md` is the English
  real-runtime owner checklist R-01 through R-16 with evidence capture and
  sign-off.
- `docs/operations/QORTIUM-DEV-MONITOR-ARCHITECTURE.md` records P4 as implemented
  and documents the detector correction and retained owner-only layers.
- `README.md` points at the P4 runbook.

## 3. Safety review

- No `setWebhook`, listener, webhook helper or inbound API was added.
- No `sudo`, service manager, global package install, Qortium command or node
  file write was added.
- No new process signal was added. The only signal remains the verified
  `dev cancel` path.
- The monitor still passes arguments as arrays with `shell=False`; owner text is
  never executed as a shell command.
- Lifecycle notification text now passes the same redaction boundary as
  interactive messages.
- Owner message bodies remain private monitor state and are never written to the
  sanitized audit table.
- Per-project admission and the global execution guard are unchanged.
- Unrelated owner modifications were preserved and not staged:
  `deploy/systemd/user/qortium-dev-monitor.service`, three `skills/` files and the
  untracked `skills/shared/browser-thumbnail-generation/` directory.

## 4. Evidence

Commands run from `/home/iffi/dev-workspace/control-plane`:

```bash
python3 -m unittest discover -s tools -p 'test_*.py' -q
python3 tools/validate_control_plane.py
python3 tools/validate_skills.py
python3 tools/validate_security.py --self-test
python3 tools/validate_security.py .
python3 tools/validate_agent_permissions.py
python3 tools/opencode_guard.py check
```

Results:

- Full unittest discovery: 350 tests, OK.
- P4 suite: 25 tests, OK.
- Detector regression suite: 34 tests, OK.
- Control-plane validator: 55 active Markdown files, 222 relative links, 59
  required files.
- Skills validator: 17 active skills indexed exactly once.
- Security validator: self-test passed; 174 files scanned.
- Agent permission validator: PASS (337 rules, 97 checks).
- Execution guard: PASS; one heavyweight execution (this job) and Qortium
  read-only.

## 5. Remaining risks and owner-only work

- The monitor was not restarted, so the running process does not yet execute P4
  code. Activation is an owner action.
- Real Telegram acceptance R-01 through R-16 is pending; use the P4 checklist.
- Detector classification is heuristic. It now avoids the P3 false positive and
  preserves explicit missing-command/module/dependency signals, but a novel
  runtime wording may still need a new fixture.
- Rate limits are process durability state, not an OS sandbox. Deleting monitor
  state resets them.
- Redaction is pattern-based; the owner must still avoid sending secrets in
  prompts or documents.
- A hardlink inside an owner-controlled docs root remains a documented residual
  risk.
- The per-project admission lock covers monitor-initiated jobs; a simultaneous
  CLI-started job is still serialized only by the global guard.

## 6. Capability harvest

`skill harvest: none — project-specific only`. The detector misclassification
and monitor boundaries are documented in this control-plane repository; no
separate reusable Qortal/Qortium platform skill is justified before real-runtime
owner acceptance.
