# workspace/qortium-dev-monitor-p3: cancel and owner messaging

Contract: /home/iffi/dev-workspace/control-plane/AGENTS.md

Executing agent (actual executor; never inferred from this template or a role):
DeepSeek (`deepseek/deepseek-flash`) through the owner-authorized Workflow v3 job
`20261101T061959Z-qortium-dev-monitor-p3-961a2a11`.

Project ID / exact repo / base SHA / agent branch:
`workspace` / `/home/iffi/dev-workspace/control-plane` / `71c3382` /
`agent/control-plane/workflow-v3-20261031`.

Platform session router / canonical project context:
Cross-project control plane (`workspace`). Operational context:
`docs/operations/QORTIUM-DEV-MONITOR.md`,
`docs/operations/QORTIUM-DEV-MONITOR-ARCHITECTURE.md` and
`docs/operations/DEV-WORKFLOW-V3.md`.

Outcome and measurable exit criterion:
Implement P3 of Qortium Dev Monitor: additive `CANCELLED`, verified `dev cancel`,
graceful guard termination, durable reports, persistent owner instruction queue
with explicit delivery state, safe resume composition, no concurrent OpenCode
sessions in one repository and explicit new-session confirmation. Preserve P1/P2,
notification deduplication, serialization and security boundaries. All automated
tests and validators pass; owner activation remains manual.

In scope / out of scope / invariants:
In scope: additive Workflow v3 cancel and prompt-file support, monitor cancel and
queue flows, SQLite owner-message state, render/menu/router/control changes, P3
tests, documentation and implementation report. Out of scope: installing,
restarting or changing the active monitor service, owner-local credentials,
Qortium node/service/data/logs, VPS configuration, deployment, push or merge.
Invariant: preserve the pre-existing modified systemd unit and `skills/` changes.

Applicable skills (path / maturity / freshness result):
No matching reusable skill existed for this control-plane feature. Reused
current monitor/Workflow v3 source, tests and the P1/P2 operations documents.

Proven reference implementation to reuse (or exact missing investigation delta):
Existing `tools/devmonitor/`, `tools/devjob/` and `tools/dev.py`; the execution
guard's verified PID/PGID and safe process-group termination; the existing
owner-local Telegram configuration.

Required surfaces and real runtime acceptance steps:
Automated: all repository test modules, validators, guard check and syntax checks.
Owner-only: restart the monitor to load P3, then exercise cancel, queue, resume
delivery, failed-resume queue retention and unknown-session refusal from the
private owner chat. The implementation did not restart the service.

Reference freshness evidence / environment IDs:
Base `71c3382`; Python 3.13; branch
`agent/control-plane/workflow-v3-20261031`; guard check passed at phase
boundaries.

Authorized external actions (exact repo, branch, operation; otherwise none):
Commit only P3-related files on `agent/control-plane/workflow-v3-20261031`.
No push, merge, deploy, service activation, QDN, wallet or server action.

Unattended execution authorization (only when explicitly granted):
- Agent profile / guard command / maximum wall-clock:
  Workflow v3 development profile; `tools/opencode_guard.py`; eight-hour maximum.
- Resource limits / stop condition:
  Guard defaults; stop at acceptance or timeout.
- Checkpoint cadence and recovery:
  Guard check at phase boundaries; preserve working tree and session history.

Forbidden actions (unattended):
Qortium node/service/data/log mutation, VPS system changes, monitor service
restart/install, webhook, inbound listener, QDN, wallet, mainnet payment,
`--auto`, name-based signalling, destructive cleanup, credential modification.

Acceptance evidence required (OpenCode exit code 0 alone is not success):
Exact diff and commit SHA, P3 and regression test output, validator output, guard
check output, and preservation of unrelated working-tree changes.

Canonical report path / handoff branch:
`tasks/orchestration/qortium-dev-monitor-p3/IMPLEMENTATION.md`;
`agent/control-plane/workflow-v3-20261031`; local-only.

Owner-only steps or reason owner validation is not applicable:
The owner must activate P3 by restarting the monitor and perform live Telegram
acceptance. P3 tests cannot prove the real bot/network.

Capability-harvest expectation (likely reusable capability or project-specific):
Project-specific control-plane implementation. No new reusable skill is
justified before real-runtime owner acceptance.
