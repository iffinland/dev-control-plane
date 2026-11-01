# workspace/qortium-dev-monitor-p4: hardening and operations

Contract: /home/iffi/dev-workspace/control-plane/AGENTS.md

Executing agent (actual executor; never inferred from this template or a role):
DeepSeek (`deepseek/deepseek-flash`) through the owner-authorized Workflow v3 job
`20261101T064540Z-qortium-dev-monitor-p4-hardening-72a27d10`.

Project ID / exact repo / base SHA / agent branch:
`workspace` / `/home/iffi/dev-workspace/control-plane` / `6b8bc7d` /
`agent/control-plane/workflow-v3-20261031`.

Platform session router / canonical project context:
Cross-project control plane (`workspace`). Operational context:
`docs/operations/QORTIUM-DEV-MONITOR.md`,
`docs/operations/QORTIUM-DEV-MONITOR-ARCHITECTURE.md`,
`docs/operations/QORTIUM-DEV-MONITOR-P4-ACCEPTANCE.md` and
`docs/operations/DEV-WORKFLOW-V3.md`.

Outcome and measurable exit criterion:
Implement P4 of Qortium Dev Monitor: harden and comprehensively test P1-P3
authorization, callback replay, rate limits, redaction, safe document access,
symlink/path traversal resistance, start/resume/cancel, durable owner queue,
notification dedupe, polling recovery, restart persistence and concurrency
protection. Correct the P3 false `missing_dependency` classification without
hiding real missing dependencies. Add regression, fault-injection and
integration tests with isolated fixtures and fake Telegram transports. Provide
an English runbook and real-runtime owner acceptance checklist. Full test suite,
control-plane validator and permission validator pass; owner activation remains
manual.

In scope / out of scope / invariants:
In scope: detector classification correction, monitor hardening, P4 tests, P4
operations documentation, owner acceptance checklist, task evidence. Out of
scope: installing, restarting or changing the active monitor service,
owner-local credentials, Qortium node/service/data/logs, VPS configuration,
deployment, push, merge, actual Telegram actions or live-job cancellation.
Invariant: preserve the pre-existing modified systemd unit, `skills/` changes and
the untracked browser-thumbnail skill.

Applicable skills (path / maturity / freshness result):
No matching reusable skill existed for this control-plane feature. Reused the
current monitor/Workflow v3 source, tests, architecture, runbook and the
capability-harvest decision test. Harvest result: none — project-specific only.

Proven reference implementation to reuse (or exact missing investigation delta):
Existing `tools/devmonitor/`, `tools/devjob/`, `tools/dev.py`, the execution
guard's verified PID/PGID boundary, the P3 cancel/queue implementation and the
existing owner-local Telegram configuration.

Required surfaces and real runtime acceptance steps:
Automated: full unittest discovery, control-plane validator, skills validator,
security validator, agent-permission validator and guard check. Owner-only:
execute R-01 through R-16 in
`docs/operations/QORTIUM-DEV-MONITOR-P4-ACCEPTANCE.md` with the real bot after
restarting the monitor outside this task.

Reference freshness evidence / environment IDs:
Base `6b8bc7d`; Python 3.13; branch
`agent/control-plane/workflow-v3-20261031`; guard check passed at phase
boundaries. Current source/runtime inspected; no Qortal/Qortium platform
reference was needed.

Authorized external actions (exact repo, branch, operation; otherwise none):
Commit only P4-related files on `agent/control-plane/workflow-v3-20261031`.
No push, merge, deploy, service activation, Telegram action, live-job cancel,
QDN, wallet or server action.

Unattended execution authorization (only when explicitly granted):
- Agent profile / guard command / maximum wall-clock:
  Workflow v3 development profile; `tools/opencode_guard.py`; four-hour job
  timeout within the eight-hour guard maximum.
- Resource limits / stop condition:
  Guard defaults; stop at acceptance or timeout.
- Checkpoint cadence and recovery:
  Guard check at phase boundaries; preserve working tree and session history.

Forbidden actions (unattended):
Qortium node/service/data/log mutation, VPS system changes, monitor service
restart/install, webhook, inbound listener, QDN, wallet, mainnet payment,
`--auto`, name-based signalling, destructive cleanup, credential modification,
actual Telegram actions and cancellation of live jobs.

Acceptance evidence required (OpenCode exit code 0 alone is not success):
Exact diff and commit SHA, full test output, validator output, guard check output,
P3 false-classification investigation evidence, and preservation of unrelated
working-tree changes.

Canonical report path / handoff branch:
`tasks/orchestration/qortium-dev-monitor-p4/IMPLEMENTATION.md`;
`agent/control-plane/workflow-v3-20261031`; local-only. Central report:
`/home/iffi/dev-workspace/docs/workspace/implementation/2026-11-01-qortium-dev-monitor-p4-hardening.md`.

Owner-only steps or reason owner validation is not applicable:
The owner must activate P4 by restarting the monitor and perform real Telegram
acceptance R-01 through R-16. Automated tests cannot prove the real bot/network.

Capability-harvest expectation (likely reusable capability or project-specific):
Project-specific control-plane hardening. No new reusable skill is justified
before real-runtime owner acceptance.
