# control-plane/control-plane: P4 security acceptance evidence consolidation

Contract: `/home/iffi/dev-workspace/control-plane/AGENTS.md`

Executing agent (actual executor; never inferred from this template or a role):
DeepSeek (`deepseek/deepseek-flash`) through the owner-authorized Workflow v3 job
`20261101T163605Z-p4-security-acceptance-evidence-0db52673`.

Project ID / exact repo / base SHA / agent branch:
`control-plane/control-plane` / `/home/iffi/dev-workspace/control-plane` /
`383a25bb6099cdb75cf968d63347c8c2a24a6da9` /
`agent/control-plane/workflow-v3-20261031`.

Platform session router / canonical project context:
Cross-project Workflow v3 control plane (`workspace` material). Operations
context: `docs/operations/QORTIUM-DEV-MONITOR*.md`, the P3/P4 task artifacts and
the control-plane contract.

Outcome and measurable exit criterion:
Correct the P4 R-01 through R-16 acceptance matrix so automated tests, scripted
synthetic tests, genuine real-Telegram/synthetic-backend observations, owner
attestations and unexecuted checks are distinct. Record the completed real P3
E1-E7 run truthfully without inventing cleaned-up message IDs or timestamps;
keep R-08, R-09 and R-10 as RT/S evidence only, not production-worker proof.
Account for observed menu, Refresh and monitor service stop/start without
claiming unobserved guarantees. Add a concise safe operator checklist with
expected outcomes, evidence capture and rollback, and mark real token rotation
and deliberate fault injection as unexecuted exceptions. Run focused security
regressions, the complete unit suite, control-plane validation and permissions
validation. Commit scoped changes and push to the verified development branch.

In scope / out of scope / invariants:
In scope: P4/P3 acceptance documentation, architecture status note, the permitted
`skills/shared/workflow-v3-completion-contract/SKILL.md` update, focused and full
validation, and this task evidence. Out of scope: code changes to monitor
semantics, live Telegram interactions, service restart, owner config or token,
production monitor state, Qortium/VPS changes, real wallet data, merge, deploy,
QDN or force-push. Invariant: preserve the owner-dirty `skills/README.md`, two
`skills/qortium/` files and the untracked `skills/shared/browser-thumbnail-generation/`
directory.

Task-start evidence (also used by the Workflow v3 completion contract):
- Applicable skills: `skills/shared/capability-harvest/SKILL.md` (shared,
  `verified-runtime`, last checked 2026-09-13) for the mandatory harvest decision;
  `skills/shared/workflow-v3-completion-contract/SKILL.md` (shared, `candidate`,
  last checked 2026-11-01) for the evidence/commit/push contract. No Qortal or
  Qortium platform skill applies to this control-plane acceptance task.
- Documentation read: `AGENTS.md`, `WORKFLOW.md`, `GIT-AND-HANDOFF.md`,
  `PROJECT-REGISTRY.md`, `ENVIRONMENT.md`, `roles/DEEPSEEK.md`,
  `platforms/qortium/README.md`, `docs/operations/QORTIUM-DEV-MONITOR.md`,
  `docs/operations/QORTIUM-DEV-MONITOR-ARCHITECTURE.md`,
  `docs/operations/QORTIUM-DEV-MONITOR-P3-LIVE-ACCEPTANCE.md`,
  `docs/operations/QORTIUM-DEV-MONITOR-P4-ACCEPTANCE.md`, the P3/P4 task
  artifacts, the workspace P4 validation/implementation reports and the two
  loaded skills.
- Reference freshness evidence / environment IDs: current source and docs read at
  base `383a25bb6099cdb75cf968d63347c8c2a24a6da9` on branch
  `agent/control-plane/workflow-v3-20261031`; Python 3.13; no Qortal/Qortium
  platform reference was needed. `python3 tools/validate_skills.py` passed with
  23 active skills indexed exactly once.
- Proven reference implementation to reuse: the existing P4 acceptance evidence
  classes and the completed P3 E1-E7 harness/runbook; no new monitor code was
  justified.
- Verification performed before implementation: inspected the current P4/P3
  documentation, P3 task history, job evidence, monitor tests and the project
  delivery policy.

Required surfaces and real runtime acceptance steps:
Automated: focused authorization, confirmation-replay, redaction,
report/document download, traversal and symlink tests; full unittest discovery;
control-plane, skills, security and agent-permission validators. Owner-only:
the remaining safe Telegram actions in the P4 checklist, including real token
rotation and deliberate fault injection. The agent did not execute any live
Telegram action, service restart, Qortium/VPS change or wallet access.

Authorized external actions (exact repo, branch, operation; otherwise none):
- Project delivery policy: `dev-control-plane` -> `iffinland/dev-control-plane`,
  development pattern `agent/*`, automatic push `yes`.
- Development-branch push authorized (and remote name): `dev-control-plane`,
  branch `agent/control-plane/workflow-v3-20261031`.
- Protected branch / merge / deploy / QDN write / wallet transaction / destructive
  operation authorized: none.

Unattended execution authorization (only when explicitly granted):
- Agent profile / guard command / maximum wall-clock:
  Workflow v3 development profile; `tools/opencode_guard.py`; four-hour job
  timeout within the eight-hour guard maximum.
- Mandatory default completion contract / optional override: default; no override.
- Resource limits / stop condition: guard defaults; stop at acceptance or timeout.
- Checkpoint cadence and recovery: guard check at phase boundaries; preserve the
  working tree and session history.

Forbidden actions (unattended):
Live Telegram interaction, service restart, owner token/config change, Qortium
node/service/data/log mutation, VPS change, wallet/seed/keystore access, real
account automation, production sensitive-file creation, merge, deploy, QDN,
force-push, `--auto`, name-based signalling and destructive cleanup.

Acceptance evidence required (OpenCode exit code 0 alone is not success):
Exact diff and commit SHA, focused regression output, complete unit-test output,
validator outputs, guard state, preserved owner dirty paths, this task evidence,
the mandatory job evidence file, the authorized push and matching remote SHA.

Canonical report path / handoff branch:
`tasks/orchestration/qortium-dev-monitor-p4-security-evidence-20261101/`;
`agent/control-plane/workflow-v3-20261031`.

Owner-only steps or reason owner validation is not applicable:
The remaining live Telegram checks, real token rotation, deliberate fault
injection and any monitor service restart remain owner-only. The prior real P3
E1-E7 run is owner-observed and its temporary evidence was cleaned, so its IDs
and timestamps are unavailable and must not be reconstructed.

Capability-harvest expectation (likely reusable capability or project-specific):
Harvested the reusable evidence-class distinction into
`skills/shared/workflow-v3-completion-contract/SKILL.md`. The R-matrix details
remain control-plane/project-specific.

Documentation updates expected (or explicit none):
Update the P4 acceptance document, the P3 live-acceptance document and the
architecture note; update the permitted completion-contract skill. Do not touch
the owner-dirty skill index or Qortium skills.

Scoped commit expectation (exact paths):
`docs/operations/QORTIUM-DEV-MONITOR-ARCHITECTURE.md`,
`docs/operations/QORTIUM-DEV-MONITOR-P3-LIVE-ACCEPTANCE.md`,
`docs/operations/QORTIUM-DEV-MONITOR-P4-ACCEPTANCE.md`,
`skills/shared/workflow-v3-completion-contract/SKILL.md` and this task directory.

Remote SHA verification expectation:
Compare `git ls-remote --heads dev-control-plane
agent/control-plane/workflow-v3-20261031` with local `HEAD` after pushing.
