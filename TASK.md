# Workflow v3 evidence: automatic per-job evidence and dirty-path parsing

This is the task-start and delivery evidence file for the recorded job. The
harness did not create this file for this pre-fix job; it was written by the
executing agent from work actually performed. Initialization or presence alone
is not completion.

- Job ID: `20261101T085757Z-fix-workflow-v3-project-github-d-6609f249`
- Repository: `/home/iffi/dev-workspace/control-plane`
- Branch: `agent/control-plane/workflow-v3-20261031`
- Base SHA: `e015a3420b45a56b876c301e443e0504f8de976d`
- Executing agent: `DeepSeek`

## Task-start contract

- Skills loaded: `skills/shared/workflow-v3-completion-contract/SKILL.md`
  (platform `shared`, maturity `candidate`, last checked 2026-11-01) and
  `skills/shared/capability-harvest/SKILL.md` (platform `shared`, maturity
  `verified-runtime`, last checked 2026-09-13). Their freshness gate was checked
  against the current checked-out `contract.py`, `evidence.py`, `runner.py` and
  the operating docs at job HEAD.
- Documentation read: `AGENTS.md`, `WORKFLOW.md`, `GIT-AND-HANDOFF.md`,
  `PROJECT-REGISTRY.md`, `docs/operations/DEV-WORKFLOW-V3.md`,
  `docs/operations/OPENCODE-PERMISSIONS.md`, `templates/TASK.md`,
  `examples/workflow-v3/TASK.md` and
  `adapters/opencode/agents/opencode-development.md`.
- Baseline: branch `agent/control-plane/workflow-v3-20261031`, base
  `e015a3420b45a56b876c301e443e0504f8de976d`; pre-existing owner changes in the
  skills tree are preserved and were not staged.
- Reference freshness: the current contract/runner/agent-profile source and the
  live test suite, not a historical summary.
- Missing investigation delta: the previous attempt delivered and pushed the
  implementation but the contract had no evidence file, and the first
  `git status --porcelain` record was truncated after a whole-output strip.

## Documentation and capability maintenance

- Capability harvest: updated
  `skills/shared/workflow-v3-completion-contract/SKILL.md` with the automatic
  per-job evidence procedure, job-specific validation and NUL-safe path parsing.
  No new skill was needed; the change belongs to an existing canonical skill.
- Documentation updates: updated `WORKFLOW.md`, `AGENTS.md`,
  `docs/operations/DEV-WORKFLOW-V3.md`,
  `docs/operations/OPENCODE-PERMISSIONS.md`, `templates/TASK.md`,
  `examples/workflow-v3/TASK.md` and the completion-contract skill.
- Scoped commit and remote SHA: recorded by the job record and the final push;
  the verified remote SHA is compared with local `HEAD` rather than assumed.

## Required evidence block

<!-- workflow-v3-evidence:v1 -->
- job_id: 20261101T085757Z-fix-workflow-v3-project-github-d-6609f249
- skill_discovery: Loaded skills/shared/workflow-v3-completion-contract/SKILL.md (shared, candidate, last checked 2026-11-01) and skills/shared/capability-harvest/SKILL.md (shared, verified-runtime, last checked 2026-09-13).
- freshness: Checked the current contract.py, evidence.py and runner.py at job HEAD 5a0bdd8; the skill guidance is compatible with the checked-out source.
- documentation_loading: Read AGENTS.md, WORKFLOW.md, GIT-AND-HANDOFF.md, PROJECT-REGISTRY.md, docs/operations/DEV-WORKFLOW-V3.md, docs/operations/OPENCODE-PERMISSIONS.md, templates/TASK.md, examples/workflow-v3/TASK.md and adapters/opencode/agents/opencode-development.md.
- capability_harvest: Capability harvest: updated skills/shared/workflow-v3-completion-contract/SKILL.md and docs/operations/DEV-WORKFLOW-V3.md; no new skill was needed.
- documentation_updates: Documentation update: updated WORKFLOW.md, AGENTS.md, docs/operations/DEV-WORKFLOW-V3.md, docs/operations/OPENCODE-PERMISSIONS.md, templates/TASK.md, examples/workflow-v3/TASK.md and the workflow-v3 completion-contract skill.
<!-- workflow-v3-evidence:end -->

## Validation and delivery

- Focused tests cover NUL-safe dirty-path parsing, the job-specific evidence
  template, refusal to accept unfilled evidence, wrong-job evidence, removed
  initialized blocks and the narrow legacy path repair.
- Acceptance commands, validators, scoped commit and authorized
  `dev-control-plane` push are recorded in the job report and job record.
- Pre-existing owner changes under `skills/` remain uncommitted and preserved.
