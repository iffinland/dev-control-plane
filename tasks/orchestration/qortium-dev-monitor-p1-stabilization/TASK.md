# workspace/qortium-dev-monitor-p1-stabilization: stabilize P1 monitor and add a systemd user unit

Contract: /home/iffi/dev-workspace/control-plane/AGENTS.md

Executing agent (actual executor; never inferred from this template or a role):
DeepSeek (`deepseek/deepseek-flash`) through the owner-authorized Workflow v3 job
`20261031T194940Z-qortium-dev-monitor-p1-stabiliza-f24f5ee3`.

Project ID / exact repo / base SHA / agent branch:
`workspace` / `/home/iffi/dev-workspace/control-plane` / `0fe5209` /
`agent/control-plane/workflow-v3-20261031`.

Platform session router / canonical project context:
Cross-project control plane (`workspace`). Primary operational context:
`docs/operations/QORTIUM-DEV-MONITOR.md` and
`docs/operations/QORTIUM-DEV-MONITOR-ARCHITECTURE.md`.

Outcome and measurable exit criterion:
Investigate intermittent multi-second Telegram menu delays across callback
acknowledgement, Telegram API calls, synchronous Workflow v3 CLI calls, SQLite,
document browsing and polling. Add bounded timing diagnostics that never expose
secrets. Fix demonstrated bottlenecks rather than speculative ones. Add a
production-ready systemd user unit stored in the repository for the existing
monitor with automatic restart, correct working directory, graceful shutdown,
duplicate-instance protection and safe transient-failure handling. Document exact
install, activate, status and log commands without installing or starting the
unit. Preserve Telegram configuration, Workflow v3 notifications, control-plane
behavior and unrelated uncommitted changes.

In scope / out of scope / invariants:
In scope: monitor timing module and instrumentation, measured timeout/state/poll
fixes, graceful shutdown, exit codes, systemd user unit, monitor tests, operations
runbook and CI/validator wiring. Out of scope: installing/enabling/starting the
service, live Telegram acceptance, job mutation, Qortium node/service/data/log
changes, VPS configuration, QDN, wallet, webhook or inbound listener. Invariant:
do not stage, reset, clean or commit the pre-existing dirty `skills/` files.

Applicable skills (path / maturity / freshness result):
No matching reusable skill existed for this control-plane monitor stabilization.
Reviewed current monitor source/tests and the P1 operations/architecture documents
instead of repeating a platform audit.

Proven reference implementation to reuse (or exact missing investigation delta):
The existing `tools/dev_monitor.py` and `tools/devmonitor/` package, Workflow v3
`tools/dev.py`/`tools/devjob/*`, the existing owner-local Telegram configuration,
and the P1 operations runbook.

Required surfaces and real runtime acceptance steps:
Automated: monitor tests, full repository test suite, control-plane, skills,
security and agent-permission validators, `systemd-analyze verify`, isolated CLI
status smoke. Owner-only/manual: install the user unit, enable/start it, verify
`systemctl --user status` and journal output, then exercise the private Telegram
chat. The implementation did not install or start the unit.

Reference freshness evidence / environment IDs:
Control-plane base `0fe5209`; Python 3.13.5; systemd 257; branch
`agent/control-plane/workflow-v3-20261031`; guard check passed at each phase
boundary.

Authorized external actions (exact repo, branch, operation; otherwise none):
Commit only relevant monitor code, tests, unit and documentation on
`agent/control-plane/workflow-v3-20261031`. No push, merge, deploy, QDN, wallet or
server action.

Unattended execution authorization (only when explicitly granted):
- Agent profile / guard command / maximum wall-clock:
  Workflow v3 development profile; `tools/opencode_guard.py`; eight-hour maximum.
- Resource limits / stop condition:
  Guard defaults; stop at acceptance or timeout.
- Checkpoint cadence and recovery:
  Guard check at phase boundaries; preserve working tree and session history.

Forbidden actions (unattended):
Qortium node/service/data/log mutation, VPS system changes, service
install/enable/start, webhook, inbound listener, QDN publication, wallet
transaction, mainnet payment, `--auto`, name-based process signalling,
destructive cleanup, modifying owner Telegram configuration.

Acceptance evidence required (OpenCode exit code 0 alone is not success):
Exact diff and commit SHA, monitor test output, full suite, control-plane/skills/
security/permission validators, `systemd-analyze verify`, timing/timeout evidence,
service documentation, and preserved pre-existing dirty files.

Canonical report path / handoff branch:
`/home/iffi/dev-workspace/docs/workspace/implementation/2026-10-31-qortium-dev-monitor-stabilization.md`;
task artifacts under this directory on the agent branch.

Owner-only steps or reason owner validation is not applicable:
Owner must install/enable/start the systemd user unit (or use the foreground
command) and verify real Telegram behavior. Login linger is already enabled.

Capability-harvest expectation (likely reusable capability or project-specific):
Project-specific control-plane capability. No reusable platform skill was created;
the timing labels and service contract are monitor-specific.
