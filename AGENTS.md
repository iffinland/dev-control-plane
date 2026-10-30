# Qortal / Qortium orchestration contract

Owner decision: 2026-09-13. Scope is exclusively Qortal and Qortium.
This repository owns shared development coordination and reusable capability
knowledge, not blockchain/platform implementation truth.

## Canonical workspace

The canonical control plane is:

```text
/home/iffi/dev-workspace/control-plane
```

Registered projects inherit this contract. Platform boundaries live under
`platforms/`; platform implementation truth remains in current platform
source/runtime. Historical reports and task artifacts retain their original
paths as provenance and are not current routing.

OpenCode loads this root instruction file through the owner's global
instructions adapter. DeepSeek uses the same canonical files. The adapters under
`adapters/` are discovery notes, not a second policy. No background agent,
polling loop, scheduler, or automatic task execution is provided by this
workspace.

## Instruction precedence and inheritance

When OpenCode, DeepSeek, or another agent works in a registered project, apply
this order:

1. explicit owner task authorization and task-specific constraints;
2. this control-plane contract (`AGENTS.md`, `WORKFLOW.md`,
   `GIT-AND-HANDOFF.md`) for cross-cutting safety, authority, identity and
   handoff rules;
3. the matching platform pack under `platforms/` for platform-specific routing;
4. the project's own `AGENTS.md` or equivalent, which may add project-specific
   constraints but must not weaken this contract or claim broader authority;
5. matching skills from `skills/`, after their freshness/compatibility check;
6. historical reports, task artifacts and donor evidence.

Current platform source and observed runtime outrank every summary for claims
about platform behavior. Do not overwrite an existing project-level `AGENTS.md`;
inherit this contract and add only project-specific deltas. If instructions
conflict and cannot be reconciled, stop and report the conflict.

## Mandatory session start

Before a new or resumed task:

1. Read [WORKFLOW.md](WORKFLOW.md), resolve the project in
   [PROJECT-REGISTRY.md](PROJECT-REGISTRY.md), then read its platform pack and
   canonical project context when imported. In Phase 1 the packs are boundaries
   and source references; if a project context is not present, use the registry
   source reference and stop before any platform-dependent work that requires it.
2. Read your role under `roles/` and
   [GIT-AND-HANDOFF.md](GIT-AND-HANDOFF.md).
3. Search [skills/](skills/README.md) for capabilities relevant to the requested
   outcome. Load only matching skills; record their maturity and freshness.
4. Check [ENVIRONMENT.md](ENVIRONMENT.md) and perform its platform/reference
   freshness gate before platform-dependent design, implementation or
   validation.
5. Use [templates/TASK.md](templates/TASK.md) for one compact controller.

Do **not** start with a full platform audit when a relevant verified skill exists.
Do a bounded compatibility/delta check first. If the skill is stale or absent,
investigate from current authoritative source and working implementations.

## Authority separation

- Owner instructions decide product intent, scope and authorization.
- This contract owns cross-platform roles, handoff, branch/environment
  coordination and reusable capability lifecycle.
- Platform packs retain technical guides and project contexts; central report
  storage is defined by
  [REPORT-STORAGE-POLICY.md](docs/REPORT-STORAGE-POLICY.md).
- Current checked-out authoritative source and observed runtime establish
  implemented platform behavior; skills summarize reusable evidence but never
  override fresher source/runtime.
- Application source and durable product documentation remain in their repos.
- Historical reports and donor/reference apps are evidence, never competing
  policy.

Never transfer a Qortal contract to Qortium, or the reverse, just because names
or request shapes are similar. Every skill declares its platform scope.

Platform boundaries:

- [Qortal platform pack](platforms/qortal/README.md)
- [Qortium platform pack](platforms/qortium/README.md)

For an older Qortal dApp affected by platform evolution, start with the
[`qortal-legacy-dapp-audit-repair`](skills/qortal/legacy-dapp-audit-repair/SKILL.md)
skill, then load only the capability-specific skills the inventory requires. Its
host reference is `candidate` evidence and must be checked against current
Qortal source/runtime.

The packs are boundaries and source references. Full platform documentation is
intentionally not imported. The condensed Qortal reference added 2026-10-31
does not become platform truth.

## Reuse-first engineering

For platform integration use this order:

```text
requirement
-> matching skill?
-> skill freshness/compatibility check
-> current proven donor/reference implementation
-> current platform source
-> smallest missing delta
-> runtime validation
-> capability harvest
```

A reusable finding must not remain trapped in one project's report when it can
prevent repeat work elsewhere. At substantial handoff run
[`capability-harvest`](skills/shared/capability-harvest/SKILL.md) and either
update/create a skill or explicitly record that the result was project-specific.

Do not create a giant universal abstraction merely because code can be shared.
Standardize stable shell/host primitives and verified capabilities. Keep
project-specific domain logic, publication protocols and branding local unless
multiple proven consumers justify promotion.

## Product/layout default

For new applications prefer the
[`functional-app-bootstrap`](skills/shared/app-bootstrap/SKILL.md): establish a
neutral functional shell and prove the important platform/runtime flows before
spending substantial implementation budget on final branding. This is a default,
not a ban on visual-first tasks when visual design is itself the requested
outcome.

## Report storage

All substantial reports, audits, research, implementation notes, validation
evidence and handoffs are stored centrally under
`/home/iffi/dev-workspace/docs/<project>/<category>/`, with cross-project and
control-plane material under `workspace/`. The categories are `audit/`,
`reports/`, `research/`, `implementation/`, `validation/` and `handoffs/`.
Application technical documentation stays in the project repository.

Never write substantial reports to the `docs/` root, an application repository or
`/tmp/`. See [REPORT-STORAGE-POLICY.md](docs/REPORT-STORAGE-POLICY.md). Compact
task controllers and status files remain under `tasks/` as defined by
[GIT-AND-HANDOFF.md](GIT-AND-HANDOFF.md).

## Evidence and safety

The former blanket Qortal “no SSH tunnel” policy is superseded. An explicitly
configured and verified tunnel may provide read-only node access. It does not
prove host/bridge/account behavior, replace real host validation, or authorize
server changes.

Preserve owner work. Do not reset, clean, automatically stash, remove duplicate
files, or relocate linked worktrees. Record unresolved conflicts and propose a
recoverable consolidation plan before destructive cleanup.

Reports, handoffs and status artifacts must name the agent that actually
executed the work, never the orchestrator, the CLI/tool profile the work ran
inside, the committing writer or a template default. Identity is evidence, not a
default: it is never inferred from a role or placeholder, and an unestablished
executor is recorded as `unknown` rather than guessed. Every platform report is
authored from [templates/REPORT.md](templates/REPORT.md). See
[GIT-AND-HANDOFF.md](GIT-AND-HANDOFF.md).

No commit, push, merge, tag, release, deploy, QDN publication, signing,
transaction, issue mutation or server change is authorized merely because an
agent has filesystem/network access. Exact authorization stays task-scoped.

These files are an implemented local coordination contract, not a running agent
service or automatically published GitHub standard. A chat without file access
must receive the exact published contract revision; never pretend an inaccessible
local path was read.
