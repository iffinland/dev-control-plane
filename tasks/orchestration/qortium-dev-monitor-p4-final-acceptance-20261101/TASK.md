# control-plane/control-plane: P4 final acceptance report and handoff

Contract: `/home/iffi/dev-workspace/control-plane/AGENTS.md`

Executing agent (actual executor; never inferred from this template or a role):
DeepSeek (`deepseek/deepseek-flash`) through the owner-authorized Workflow v3 job
`20261101T180615Z-finalize-p4-security-acceptance-360188a1`.

Project ID / exact repo / base SHA / agent branch:
`control-plane/control-plane` / `/home/iffi/dev-workspace/control-plane` /
`6efcd2a1bb782910bd2e33b0f6711912f36b5e74` /
`agent/control-plane/workflow-v3-20261031`.

Platform session router / canonical project context:
Cross-project Workflow v3 control plane (`workspace` material). Operations
context: `docs/operations/QORTIUM-DEV-MONITOR*.md`, the P3/P4 task artifacts and
the control-plane contract.

Outcome and measurable exit criterion:
Produce the final P4 acceptance report for R-01 through R-16 with explicit
evidence classes and honest pass, partial and unexecuted states. Record the
owner's real Telegram observations: R-02 unauthorized `/start`, `/menu` and
`/jobs` denials; R-03 workspace README preview/browsing; R-05
`README.redacted.md` download opened on Android without a manual secret-removal
or source-hash comparison; R-07 isolated synthetic replay formal pass with one
cancellation, two rejected/deduplicated replays, final `CANCELLED`, cleanup and
monitor active; R-08 through R-10 real Telegram synthetic E1-E7 formal pass with
queued instruction, two cancellations, Resume and exactly-once attempt-#2
delivery. Keep cleaned temporary evidence unreconstructed. Distinguish real bot +
synthetic backend from production-worker execution. Include automated evidence,
health semantics, safeguards, limitations, risk register and owner sign-off. Run
the full unit suite, control-plane validation and agent-permission validation;
commit scoped documentation, push, and verify the remote SHA.

In scope / out of scope / invariants:
In scope: P4 acceptance report, P3 harness status correction, architecture and
runbook status notes, task evidence, full validation. Out of scope: application
behaviour, Telegram config, monitor or Qortium service restart, Qortium/VPS
settings, credentials, wallet data, production-job cancellation, merge, deploy,
QDN or force-push. Invariant: preserve the owner-dirty `skills/README.md`, the
two `skills/qortium/` files and the untracked
`skills/shared/browser-thumbnail-generation/` directory.

Task-start evidence:
- Applicable skills: `skills/shared/capability-harvest/SKILL.md` (shared,
  `verified-runtime`, last checked 2026-09-13) for the harvest decision;
  `skills/shared/workflow-v3-completion-contract/SKILL.md` (shared, `candidate`,
  last checked 2026-11-01) for evidence classes and delivery checks. No Qortal or
  Qortium platform skill applies to this control-plane documentation task.
- Documentation read: `AGENTS.md`, `WORKFLOW.md`, `GIT-AND-HANDOFF.md`,
  `PROJECT-REGISTRY.md`, `ENVIRONMENT.md`, `roles/DEEPSEEK.md`,
  `platforms/qortium/README.md`, `docs/operations/QORTIUM-DEV-MONITOR.md`,
  `docs/operations/QORTIUM-DEV-MONITOR-ARCHITECTURE.md`,
  `docs/operations/QORTIUM-DEV-MONITOR-P3-LIVE-ACCEPTANCE.md`,
  `docs/operations/QORTIUM-DEV-MONITOR-P4-ACCEPTANCE.md`, the P3/P4 task
  artifacts, the workspace P4 validation/implementation reports and the two
  loaded skills.
- Freshness: current source and docs read at base `6efcd2a` on branch
  `agent/control-plane/workflow-v3-20261031`; Python 3.13; no Qortal/Qortium
  platform reference was needed.

Required surfaces and real runtime acceptance steps:
Automated: full unittest discovery, P4 monitor suite, P3 live acceptance suite,
control-plane, skills, security and agent-permission validators and the execution
guard. Owner-only: the remaining safe Telegram actions, real token rotation,
deliberate fault injection, production-worker cancellation and host-invariant
comparisons. The agent did not execute any live Telegram action, service restart,
Qortium/VPS change or wallet access.

Authorized external actions:
- Project delivery policy: `dev-control-plane` -> `iffinland/dev-control-plane`,
  development pattern `agent/*`, automatic push `yes`.
- Development-branch push: `dev-control-plane`,
  `agent/control-plane/workflow-v3-20261031`.
- Protected branch / merge / deploy / QDN write / wallet transaction / destructive
  operation authorized: none.

Acceptance evidence required:
Exact diff and commit SHA, full test output, focused P4/P3 output, validator
outputs, guard state, preserved owner dirty paths, task evidence, the mandatory
job evidence file, the authorized push and matching remote SHA.

Canonical report path / handoff branch:
`tasks/orchestration/qortium-dev-monitor-p4-final-acceptance-20261101/`;
`agent/control-plane/workflow-v3-20261031`.

Owner-only steps:
The owner signs the acceptance report, decides whether to accept the documented
exceptions, optionally performs token rotation and fault injection, and performs
any residual live check. The cleaned synthetic journals, message IDs and
timestamps remain unavailable and must not be reconstructed.

Capability-harvest expectation:
None new beyond the existing `workflow-v3-completion-contract` evidence classes.
The R-matrix and live Telegram checklist remain control-plane/project-specific.

Documentation updates expected:
Update the P4 acceptance report, the P3 live-acceptance status, the architecture
and runbook status notes, and this task directory. Do not touch the owner-dirty
skill index or Qortium skills.

Scoped commit expectation (exact paths):
`docs/operations/QORTIUM-DEV-MONITOR-P4-ACCEPTANCE.md`,
`docs/operations/QORTIUM-DEV-MONITOR-P3-LIVE-ACCEPTANCE.md`,
`docs/operations/QORTIUM-DEV-MONITOR-ARCHITECTURE.md`,
`docs/operations/QORTIUM-DEV-MONITOR.md` and this task directory.

Remote SHA verification expectation:
Compare `git ls-remote --heads dev-control-plane
agent/control-plane/workflow-v3-20261031` with local `HEAD` after pushing.
