# workspace/qortium-dev-monitor-p1: implement Phase P1 read-only Telegram monitor

Contract: /home/iffi/dev-workspace/control-plane/AGENTS.md

Executing agent (actual executor; never inferred from this template or a role):
DeepSeek (`deepseek/deepseek-flash`) through the owner-authorized Workflow v3 job.

Project ID / exact repo / base SHA / agent branch:
`workspace` / `/home/iffi/dev-workspace/control-plane` / `34413a3` /
`agent/control-plane/workflow-v3-20261031`.

Platform session router / canonical project context:
Cross-project control plane (`workspace`); architecture design at
`docs/operations/QORTIUM-DEV-MONITOR-ARCHITECTURE.md`.

Outcome and measurable exit criterion:
Implement P1 read-only Qortium Dev Monitor with authenticated private-chat access,
interactive menus, job status/list, bounded logs, reports, project listing from
`PROJECT-REGISTRY.md`, safe document browsing, read-only downloads, credential
redaction, persistent polling offsets and outbound-only Telegram long polling.
The monitor must reuse Workflow v3 and existing Telegram configuration, must not
create a parallel job manager, must not start a persistent process, and must pass
its new tests plus the full control-plane validation gate.

In scope / out of scope / invariants:
In scope: `tools/dev_monitor.py`, `tools/devmonitor/`, P1 tests, operations
runbook, task artifacts, CI/validator wiring. Out of scope: `dev start/resume/
cancel/accept`, owner-message delivery, webhooks, inbound listeners, persistent
services, VPS/Qortium changes, QDN or wallet actions. Invariant: no commit, reset,
clean or stash of pre-existing unrelated changes.

Applicable skills (path / maturity / freshness result):
No existing skill matched Telegram monitor operation. Reused the current
Workflow v3 CLI/store source and the architecture document instead of repeating a
platform audit.

Proven reference implementation to reuse (or exact missing investigation delta):
Workflow v3 `tools/dev.py`, `tools/devjob/*`, existing Telegram notification
configuration and `docs/operations/QORTIUM-DEV-MONITOR-ARCHITECTURE.md`.

Required surfaces and real runtime acceptance steps:
Automated: new monitor tests and full repository test/validator suite. Owner-only
manual activation: add the nested `monitor` configuration, run
`dev_monitor.py check`, start the foreground monitor and verify the private chat.
Implementation must not start the bot process.

Reference freshness evidence / environment IDs:
Control-plane HEAD `34413a3`; Python 3.13; branch
`agent/control-plane/workflow-v3-20261031`; guard check passed at each phase
boundary.

Authorized external actions (exact repo, branch, operation; otherwise none):
Commit only P1-related changes on the task branch. No push, merge, deploy, QDN,
wallet or server action.

Unattended execution authorization (only when explicitly granted):
- Agent profile / guard command / maximum wall-clock:
  Workflow v3 development profile; `tools/opencode_guard.py`; eight-hour maximum.
- Resource limits / stop condition:
  Guard defaults; stop at acceptance or timeout.
- Checkpoint cadence and recovery:
  Guard check at phase boundaries; preserve working tree and session history.

Forbidden actions (unattended):
Qortium node/service/data/log mutation, VPS system changes, persistent bot
process, webhook, inbound listener, QDN publication, wallet transaction,
mainnet payment, `--auto`, name-based process signalling, destructive cleanup.

Acceptance evidence required (OpenCode exit code 0 alone is not success):
Exact diff, new test output, full repository suite, control-plane/skills/security
validators, manual activation steps, and preserved pre-existing dirty files.

Canonical report path / handoff branch:
`/home/iffi/dev-workspace/docs/workspace/implementation/2026-10-31-qortium-dev-monitor-p1.md`;
task artifacts under this directory.

Owner-only steps or reason owner validation is not applicable:
Owner must add real numeric Telegram IDs, run `check`, and start the foreground
monitor manually. P1 did not start it.

Capability-harvest expectation (likely reusable capability or project-specific):
Project-specific control-plane capability for now. No reusable Telegram skill was
created because P2-P4 will materially change the operational contract.
