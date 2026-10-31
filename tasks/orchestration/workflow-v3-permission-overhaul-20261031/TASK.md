# control-plane/workflow-v3-permission-overhaul: overhaul development permissions and outcome classification

Contract: /home/iffi/dev-workspace/control-plane/AGENTS.md
Executing agent (actual executor; never inferred from this template or a role):
DeepSeek (`deepseek/deepseek-flash`), Workflow v3 job
`20261031T202338Z-workflow-v3-permission-model-ove-1225f2d4`.
Project ID / exact repo / base SHA / agent branch:
`control-plane`, `/home/iffi/dev-workspace/control-plane`, base `5b56c97`,
branch `agent/control-plane/workflow-v3-20261031`.
Platform session router / canonical project context: control-plane only; no
platform source changes.
Outcome and measurable exit criterion: investigate the actual rejected
operations from the two latest Qortium Dev Monitor sessions; simplify the
development permission policy to allow normal autonomous development, Git,
build, test, diagnostic, registered-project and approved-tooling paths while
retaining credential, wallet, live-Qortium and VPS-system protections; correct
outcome classification for recovered intermediate failures without hiding
unresolved denials or failed required acceptance criteria; update the source
profile, deployment procedure, documentation and regression tests; pass all
tests, validators and effective merged-rule checks; commit only relevant
changes.
In scope / out of scope / invariants:
In scope: `adapters/opencode/agents/opencode-development.md`,
`tools/install_opencode_profiles.sh`, `tools/devjob/detect.py`,
`tools/devjob/runner.py`, `tools/validate_agent_permissions.py`, permission /
detection / CLI / guard tests and the related operations documentation.
Out of scope: Qortium/Qortal source, node, database, services, VPS system
configuration, the Telegram monitor, QDN writes, wallet transactions, push,
merge, release and deployment. Invariants: preserve unrelated dirty `skills/`
changes; do not restart Qortium or the monitor; keep runtime state and
credentials outside Git.
Applicable skills (path / maturity / freshness result):
No platform skill applied. Read the control-plane contract and current Workflow
v3 source; the task is control-plane tooling.
Proven reference implementation to reuse (or exact missing investigation delta):
current `tools/devjob/detect.py`, `tools/validate_agent_permissions.py`,
`tools/install_opencode_profiles.sh` and the installed OpenCode 1.19.5 agent
definition.
Required surfaces and real runtime acceptance steps:
full test suite, control-plane validator, permission validator, skills and
security validators, execution-guard check, installed-profile merge check via
`opencode debug agent opencode-development`, and a scoped `git diff --check`.
Reference freshness evidence / environment IDs:
OpenCode 1.19.5 at `/home/iffi/.opencode/bin/opencode`; Python 3.13; Debian VPS
workspace; branch base `5b56c97`.
Authorized external actions (exact repo, branch, operation; otherwise none):
local commit only on `agent/control-plane/workflow-v3-20261031`; user-level
OpenCode profile installation with backups; no push, merge, publish, deploy,
signing or transaction.
Unattended execution authorization (only when explicitly granted):
- Agent profile / guard command / maximum wall-clock:
  `opencode-development`; `python3 tools/opencode_guard.py check`; 3h job
  timeout, 8h guard maximum.
- Resource limits / stop condition: guard PASS/WARN only; stop on REFUSE.
- Checkpoint cadence and recovery: guard check at phase boundaries; preserve
  the working tree and session history on timeout or step exhaustion.
Forbidden actions (unattended): modify/signal/restart Qortium, change VPS or
system packages/services, alter the Telegram monitor, real blockchain
transactions, credential exposure.
Acceptance evidence required (OpenCode exit code 0 alone is not success):
tests, validators, effective merged-rule checks, exact diff, guard output.
Canonical report path / handoff branch:
`/home/iffi/dev-workspace/docs/workspace/implementation/2026-10-31-workflow-v3-permission-overhaul.md`;
branch `agent/control-plane/workflow-v3-20261031`.
Owner-only steps or reason owner validation is not applicable: owner review and
merge; restart any long-running OpenCode session to load the installed profile.
Capability-harvest expectation (likely reusable capability or project-specific):
control-plane workflow capability; documentation updated in place, no platform
skill promotion.
