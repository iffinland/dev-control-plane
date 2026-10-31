# control-plane/workflow-v3: autonomous development jobs with 8-hour guard

Contract: /home/iffi/dev-workspace/control-plane/AGENTS.md
Executing agent (actual executor; never inferred from this template or a role): DeepSeek
Project ID / exact repo / base SHA / agent branch:
`control-plane`, `/home/iffi/dev-workspace/control-plane`, base `b48f6af`,
branch `agent/control-plane/workflow-v3-20261031`.
Platform session router / canonical project context: control-plane only; no
platform source changes.
Outcome and measurable exit criterion: implement Workflow v3 CLI
(`dev start/status/report/logs/resume`), durable jobs, acceptance verification,
detectors, detached background execution, safe resume and Telegram
notifications; raise guard and default job maximum to 8 hours; all tests and
validators pass.
In scope / out of scope / invariants:
In scope: control-plane tools, tests, docs, examples, migration, OpenCode
development profile. Out of scope: Qortium/Qortal source, node, database,
services, VPS system configuration, real blockchain transactions. Invariants:
preserve the guard's Qortium read-only and process-group safety behavior; keep
runtime state and credentials outside Git.
Applicable skills (path / maturity / freshness result): `skills/shared/capability-harvest`
read as procedure; no platform skill applied because this is control-plane
workflow tooling. No skill index edit was made because the index contains
unrelated owner work in progress.
Proven reference implementation to reuse (or exact missing investigation delta):
existing `tools/opencode_guard.py`, existing restricted OpenCode profile and
OpenCode 1.19.5 CLI behavior.
Required surfaces and real runtime acceptance steps:
guard tests, Workflow v3 CLI tests with a disposable fake OpenCode, control-plane
structure/skills/security validators, Git hook tests, `git diff --check`.
Reference freshness evidence / environment IDs: OpenCode 1.19.5 at
`/home/iffi/.opencode/bin/opencode`; Debian VPS workspace; guard check PASS at
phase boundaries.
Authorized external actions (exact repo, branch, operation; otherwise none):
local commit only on `agent/control-plane/workflow-v3-20261031`; no push, merge,
publish, deploy, signing or transaction.
Unattended execution authorization (only when explicitly granted): owner
authorized this implementation task; no real model session was started by the
test harness.
- Agent profile / guard command / maximum wall-clock: this implementation ran
  under `opencode-unattended`; guard maximum 8h.
- Resource limits / stop condition: guard PASS/WARN only; stop on REFUSE.
- Checkpoint cadence and recovery: guard check before/after phases; job tests use
  fake OpenCode and synthetic procfs.
Forbidden actions (unattended): modify/signal Qortium, change VPS or system
packages/services, real blockchain transactions, credential exposure.
Acceptance evidence required (OpenCode exit code 0 alone is not success):
tests, validators, exact diff, job state tests, guard timeout tests.
Canonical report path / handoff branch:
`/home/iffi/dev-workspace/docs/workspace/implementation/2026-10-31-workflow-v3.md`;
branch `agent/control-plane/workflow-v3-20261031`.
Owner-only steps or reason owner validation is not applicable: owner must review,
install the development profile and merge; real OpenCode/Telegram/QDN/live-app
acceptance was not executed in this implementation task.
Capability-harvest expectation (likely reusable capability or project-specific):
control-plane operational capability documented in
`docs/operations/DEV-WORKFLOW-V3.md`; no platform skill promotion.
