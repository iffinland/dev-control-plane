# Implementation — workspace/p3-telegram-live-acceptance

Executing agent (actual executor of the work): DeepSeek
(`deepseek/deepseek-flash`) through the owner-authorized Workflow v3 job
`20261101T140335Z-p3-telegram-live-acceptance-test-c2538145`.

Report/handoff writer (if different from the executing agent): same agent.

Exact application repository / branch / SHA:
`/home/iffi/dev-workspace/control-plane`,
`agent/control-plane/workflow-v3-20261031`, implementation commit
`a26360c0b526e9473b1efa87d90951846f6e8970`, base
`1660f03f61eab7dbf4acbf889f34de735fc7d404`. The verified application remote SHA
is `a26360c0b526e9473b1efa87d90951846f6e8970`.

Verdict and measurable acceptance achieved:
The P3 live acceptance harness is implemented and covered by 16 isolated
regression tests. The harness prepares a throw-away Git repository, a generated
synthetic-only registry, temporary monitor/Workflow state, a deterministic fake
Workflow v3 CLI and a journaling Telegram wrapper. It refuses to prepare or run
while the production monitor is active, requires an explicit live-confirmation
flag, and verifies that the synthetic job ends `CANCELLED` with a queued or
delivered owner instruction. It never starts OpenCode, sends a Telegram message on
its own, edits the production registry/config, or touches the Qortium node.

The owner has not executed the live Telegram interaction. That remains the only
unexecuted acceptance layer.

## 1. What changed

### Harness

- `tools/devmonitor/acceptance.py`:
  - `LiveAcceptanceHarness.prepare` validates the source config/mode/allowlists,
    refuses while the production monitor holds its lock, creates a private work
    directory, initializes an isolated Git repository, generates a registry with
    only `synthetic/p3-live-acceptance`, copies the source config with isolated
    registry/repo/docs paths, seeds a synthetic `RUNNING` job, and writes an
    evidence template plus manifest.
  - `run` refuses without `--confirm-live-telegram`, checks `getMe`/webhook
    state, starts only the isolated poller with the fake CLI, and stops when the
    synthetic job reaches `CANCELLED` or times out.
  - `verify` cross-checks source config/registry hashes, synthetic-only job
    state, cancellation events, fake `dev cancel`, owner message state, optional
    resume delivery, and the recorded Telegram button/callback labels; it
    rejects `SUCCESS`/`FAILED`/`BLOCKED`/`TIMEOUT`, non-synthetic records,
    incomplete evidence and `UNRECORDED` operator fields.
  - `cleanup` removes only a marked harness directory after the isolated poller
    has stopped.
  - `RecordingTelegramApi` journals real update/message IDs, callback labels,
    sanitized outbound text and button labels without the token, chat ID or raw
    callback nonces.
- `tools/p3_live_acceptance.py`: operator CLI for `prepare`, `run`, `verify`,
  `status` and `cleanup`.
- `tools/dev_monitor.py`: `_build_components` accepts optional injected API and
  job facade so the harness can reuse the production component graph without
  changing the default path or the service unit.
- `tools/test_p3_live_acceptance.py`: 16 tests covering fixture isolation,
  source preservation, fail-closed preconditions, fake-worker cancellation and
  resume, no SUCCESS path, full queue/cancel router flow, evidence rejection,
  changed-source rejection, explicit live confirmation and cleanup.

### Documentation and validation

- `docs/operations/QORTIUM-DEV-MONITOR-P3-LIVE-ACCEPTANCE.md`: purpose,
  non-goals, safety boundaries, fail-closed table, prepare/run/verify/cleanup
  commands, exact Telegram interaction matrix and evidence fields.
- `docs/operations/QORTIUM-DEV-MONITOR.md`: links the harness from validation and
  P4 owner acceptance.
- `docs/operations/QORTIUM-DEV-MONITOR-P4-ACCEPTANCE.md`: points the synthetic
  R-08/R-09 path at the harness.
- `tools/validate_control_plane.py`: requires the new harness, tests and runbook.

## 2. Safety review

- No `setWebhook`, listener, service installation/restart, `sudo`, package
  install, name-based signal or Qortium command was added.
- The only live network action is an explicit `run` with
  `--confirm-live-telegram`; it long-polls the real bot after the owner has
  stopped the production monitor manually.
- The fake CLI has no `start` implementation and no SUCCESS path. It only
  returns `RUNNING` or `CANCELLED` for synthetic jobs and records resume stdin.
- All synthetic state and the temporary repository live under the private work
  directory. Source config/registry hashes are recorded at prepare and checked at
  verify.
- The production `PROJECT-REGISTRY.md`, owner `telegram.json`, live monitor
  SQLite state and live job store are never written.
- The synthetic job is titled `[SYNTHETIC]` and is forced to `CANCELLED`; its
  report explicitly states it is not a development success.
- Pre-existing owner changes were preserved and not staged:
  `skills/README.md`, two `skills/qortium/` entries and the untracked
  `skills/shared/browser-thumbnail-generation/` directory.

## 3. Evidence

Commands run from `/home/iffi/dev-workspace/control-plane`.

### Required acceptance

```bash
python3 -m unittest discover -s tools -p 'test_*.py' -q
python3 tools/validate_control_plane.py
python3 tools/validate_agent_permissions.py
```

Results:

- Full unittest discovery: 454 tests, OK.
- Control-plane validator: 100 active Markdown files, 440 relative links, 85
  required files.
- Agent permission validator: PASS (338 rules, 98 checks).
- Focused harness suite: 16 tests, OK.
- Skills validator: 23 active skills indexed exactly once.
- Security validator self-test and full scan: passed (234 files).
- Execution guard: `WARN` only (current OpenCode process occupies the one
  heavyweight slot and load average exceeded the warning threshold); no refusal.

### What the tests prove

- The source config/registry are byte-for-byte unchanged after prepare.
- The temporary registry contains only the synthetic project and no production
  path.
- The temporary repository has the expected synthetic GitHub-shaped remote.
- The temporary config is `0600` and points only at isolated roots.
- A read-only source mode, disabled queue, insecure config, running production
  monitor and production state work directory are refused.
- Fake cancel produces `CANCELLED`, records cancellation events and never
  `SUCCESS`; it contains no `os.kill`.
- Fake resume records the instruction and leaves the job `RUNNING`, never
  `SUCCESS`, and refuses non-synthetic records.
- The real monitor router (with a fake Telegram API) queues an instruction and
  cancels through the real button/confirmation flow; verification then passes.
- Verification rejects `UNRECORDED` evidence, a synthetic `SUCCESS`, a
  non-synthetic job record and a changed source config.
- Cleanup removes only a marked fixture and preserves the source files.

## 4. Owner-only activation and acceptance

1. Read `docs/operations/QORTIUM-DEV-MONITOR-P3-LIVE-ACCEPTANCE.md`.
2. Stop the production monitor manually through its documented path. Do not stop
   or restart Qortium.
3. Run `prepare` with the owner config, then `run --confirm-live-telegram`.
4. Perform E1-E6 (and optional E7 resume) in the authorized private chat.
5. Fill `telegram-evidence.json`; run `verify`.
6. Run `cleanup`; restart the production monitor manually; run
   `dev_monitor.py check`.

## 5. Capability harvest

`skill harvest: none — project-specific/control-plane only.` The reusable
capability is the harness itself and its operations runbook in this repository.
A new shared Qortal/Qortium skill would require editing the owner-dirty
`skills/README.md`, which this job is forbidden to modify.

## 6. Remaining findings / next actor

Next actor: owner. The live Telegram interaction, production monitor stop/start
and the Qortium no-change attestation remain owner actions. No further code change
is justified before that evidence exists.
