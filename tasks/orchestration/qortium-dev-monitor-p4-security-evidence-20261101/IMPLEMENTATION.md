# Implementation — control-plane/qortium-dev-monitor-p4-security-evidence

Executing agent (actual executor of the work): DeepSeek
(`deepseek/deepseek-flash`) through the owner-authorized Workflow v3 job
`20261101T163605Z-p4-security-acceptance-evidence-0db52673`.

Report/handoff writer (if different from the executing agent): same agent.

Exact application repository / branch / SHA:
`/home/iffi/dev-workspace/control-plane`,
`agent/control-plane/workflow-v3-20261031`, documentation/skill commit
`6fb9962ea1be9bf98570857008d72c3ab072a858` (base
`383a25bb6099cdb75cf968d63347c8c2a24a6da9`). This task-evidence commit follows
the documentation commit; the final remote SHA is recorded in `STATUS.json` and
the handoff.

Verdict and measurable acceptance achieved:
The R-01 through R-16 matrix now distinguishes automated tests, scripted
synthetic tests, genuine real-Telegram/synthetic-backend observations, owner
attestations and unexecuted checks. The completed real P3 E1-E7 run is recorded
truthfully without unavailable message IDs or timestamps. R-08, R-09 and R-10 are
RT/S evidence only, never production-worker verification. Menu, Refresh and
monitor service stop/start are recorded as observations, not unproven security
guarantees. Token rotation and deliberate fault injection remain explicit
unexecuted exceptions. A concise owner checklist covers the remaining safe live
actions with expected outcomes, evidence capture and rollback. Focused and full
automated validation passed. No live Telegram action, service restart, token or
owner-config change, Qortium/VPS change or wallet access was performed.

## 1. What changed

### Acceptance documentation

- `docs/operations/QORTIUM-DEV-MONITOR-P4-ACCEPTANCE.md`:
  - replaced the stale "no real evidence" status with the observed real P3 E1-E7
    result and its cleaned-evidence limitation;
  - added `RT/S — real Telegram with synthetic backend` and retained-`T`
    evidence classes, and clarified `O` and `U`;
  - rewrote R-01 through R-16 with the correct class per row;
  - recorded menu, Refresh and service stop/start only as owner-attested
    observations, with the unproven parts explicit;
  - added the remaining safe operator checklist (preflight, expected outcome,
    evidence capture and stop/rollback for each action);
  - marked real token rotation and deliberate network fault injection as
    unexecuted owner-only exceptions;
  - updated evidence capture and sign-off fields.
- `docs/operations/QORTIUM-DEV-MONITOR-P3-LIVE-ACCEPTANCE.md`: records that the
  owner completed the real-bot E1-E7 run with the synthetic worker and formal
  verification passed, while the cleaned temporary directory leaves no retained
  journal or identifiers.
- `docs/operations/QORTIUM-DEV-MONITOR-ARCHITECTURE.md`: notes the RT/S scope and
  the remaining owner-only exceptions.

### Reusable skill

- `skills/shared/workflow-v3-completion-contract/SKILL.md`: added a reusable
  acceptance-evidence classification so automated, scripted,
  real-transport/synthetic-backend, owner-attested and unexecuted results are
  never collapsed into one another.

### Safety

- The owner-dirty `skills/README.md`, two `skills/qortium/` skills and the
  untracked `skills/shared/browser-thumbnail-generation/` directory were left
  untouched and unstaged.
- No token, chat ID, passphrase, wallet data or owner configuration was read,
  printed, changed or committed.
- No service was stopped or restarted; no live Telegram message was sent; no
  Qortium or VPS setting changed.

## 2. Evidence

Focused regression coverage (all OK):

```bash
python3 -m unittest -v \
  tools.test_dev_monitor_p4.AuthorizationAndReplayTests \
  tools.test_dev_monitor_auth \
  tools.test_dev_monitor_p4.RedactionTests \
  tools.test_dev_monitor_documents
# 30 tests, OK

python3 -m unittest -v \
  tools.test_dev_monitor_p4.DocumentHardeningTests \
  tools.test_dev_monitor_integration.MonitorIntegrationTests.test_authorized_start_returns_main_menu \
  tools.test_dev_monitor_integration.MonitorIntegrationTests.test_unauthorized_callback_is_rejected_before_state_lookup \
  tools.test_dev_monitor_integration.MonitorIntegrationTests.test_job_download_log \
  tools.test_dev_monitor_integration.MonitorIntegrationTests.test_document_browse_preview_and_redacted_download \
  tools.test_dev_monitor_integration.MonitorIntegrationTests.test_duplicate_callback_update_runs_action_once \
  tools.test_dev_monitor_integration.MonitorIntegrationTests.test_duplicate_after_restart_acknowledges_without_repeating_action
# 13 tests, OK
```

Complete automated gate:

```bash
python3 -m unittest discover -s tools -p 'test_*.py' -q
# 468 tests, OK (250.046s)

python3 tools/validate_control_plane.py
# passed: 100 active Markdown files, 441 relative links, 85 required files

python3 tools/validate_skills.py
# passed: 23 active skills indexed exactly once

python3 tools/validate_security.py --self-test
python3 tools/validate_security.py .
# self-test passed; 235 files scanned

python3 tools/validate_agent_permissions.py
# PASS (338 rules, 98 checks)

python3 tools/opencode_guard.py check
# WARN only: the current job occupies the one heavyweight slot and the
# 5-minute load average exceeded the warning threshold; no refusal.
```

`git diff --check` over the task-owned documentation and skill paths is clean.
The whole-tree check reports only the pre-existing owner trailing whitespace in
`skills/qortium/qdn-resource-discovery/SKILL.md`, which was preserved and not
staged.

## 3. Truthfulness limits

- The real P3 E1-E7 run's message IDs, update IDs, timestamps, journal and report
  are unavailable because the temporary evidence directory was cleaned. They are
  not reconstructed.
- R-08, R-09 and R-10 prove the observed real Telegram round-trip against the
  isolated synthetic backend, not production-worker or production-job behavior.
- Menu, Refresh and monitor service stop/start were observed, but this does not
  prove a dedicated `/start` secret-exposure test, running-job restart
  persistence, graceful lock release or listener/Qortium invariance.
- Real token rotation and deliberate fault injection remain unexecuted.

## 4. Capability harvest

`skill harvest: updated skills/shared/workflow-v3-completion-contract/SKILL.md`
with reusable acceptance-evidence classes (automated, scripted,
real-transport/synthetic-backend, retained real-runtime, owner-attested,
unexecuted). The R-matrix and live Telegram checklist remain
control-plane/project-specific.

## 5. Remaining owner-only work

The owner should execute the remaining safe checklist rows with the real bot,
record sanitized evidence under `/home/iffi/dev-workspace/docs/workspace/validation/`,
and separately perform real token rotation and any deliberate fault-injection
test. No agent should perform those actions automatically.
