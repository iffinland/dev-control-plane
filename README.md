# Canonical Agent Control Plane

This repository is the canonical, shared control plane for AI-assisted Qortal
and Qortium development. It owns coordination, roles, reusable skills, task
templates and project routing. It does not own application source or platform
implementation truth.

Start with [AGENTS.md](AGENTS.md).

## Current baseline

Phase 1 established this workspace from the validated orchestration commit:

```text
source repository: https://github.com/iffinland/ai-development-orchestration
source branch:     agent/shadow-archives/qdn-grouped-publish-outcome-20261001
source commit:     aef3e1ed45c66ef2382e5cc794665d1720f7ad77
local branch:      phase1/control-plane
```

The workspace is intentionally not committed or pushed in Phase 1. Platform
documentation is not imported yet; Qortal and Qortium are represented by boundary
packs only.

## Core model

```text
owner outcome
-> shared control-plane contract
-> project registry and platform pack
-> relevant reusable skills
-> current platform source/runtime freshness check
-> bounded implementation
-> layered validation
-> capability harvest
-> durable handoff
```

Agents must search the [reusable capability library](skills/README.md) before
redoing platform research. New reusable findings are harvested back into it so
future applications pay only for the changed/project-specific delta.

## Structure

```text
control-plane/
├── AGENTS.md                 canonical agent contract and precedence
├── WORKFLOW.md               execution and validation workflow
├── GIT-AND-HANDOFF.md        branch, task, identity and handoff rules
├── PROJECT-REGISTRY.md       verified project routing
├── ENVIRONMENT.md            non-secret environment and reference registry
├── roles/                    thin agent role definitions
├── templates/                TASK, STATUS, HANDOFF and REPORT shapes
├── skills/                   canonical reusable capability library
├── platforms/
│   ├── qortal/               Qortal boundary and source reference
│   └── qortium/              Qortium boundary and source reference
├── adapters/
│   ├── opencode/             OpenCode discovery and inheritance notes
│   └── deepseek/             DeepSeek client boundary notes
├── tools/                    skills/library validators
├── tasks/                    historical task artifacts and evidence
├── reports/                  historical orchestration reports
├── research/                 historical pattern research
└── docs/                     report-storage policy, operations runbooks and migration records
```

Central report storage is `/home/iffi/dev-workspace/docs/<project>/<category>/`;
cross-project and control-plane material belongs under `workspace/`. See the
[Report storage policy](docs/REPORT-STORAGE-POLICY.md).

## Main documents

- [Shared contract](AGENTS.md)
- [Workflow](WORKFLOW.md)
- [Reusable capability library](skills/README.md)
- [Project registry](PROJECT-REGISTRY.md)
- [Environment registry](ENVIRONMENT.md)
- [Report storage policy](docs/REPORT-STORAGE-POLICY.md)
- [OpenCode tmux session runbook](docs/operations/OPENCODE-TMUX-SESSIONS.md)
- [Git and durable handoff](GIT-AND-HANDOFF.md)
- [Qortal platform boundary](platforms/qortal/README.md)
- [Qortal legacy audit reference](platforms/qortal/references/README.md)
- [Qortium platform boundary](platforms/qortium/README.md)
- [OpenCode adapter](adapters/opencode/README.md)
- [DeepSeek adapter](adapters/deepseek/README.md)
- [Phase 1 migration record](docs/migration/2026-10-30-phase1-control-plane.md)
- [Agent roles](roles/)
- [Task and handoff templates](templates/)

## Clients and roles

Current operating roles:

```text
ChatGPT -> architecture / controller / review
Codex    -> local orchestration / bounded independent audit / escalation
DeepSeek -> primary cost-efficient local implementation
OpenCode -> CLI harness that loads this control plane and executes assigned work
```

OpenCode and DeepSeek are clients/execution surfaces, not separate governance
sources. They read the same canonical contract and skills. Claude remains an
optional future adapter.

No background agent, polling process, scheduler, notification service, or
automatic task dispatch is installed by this repository.

## Platform boundary

Qortal and Qortium are separate technical contracts. Never apply one platform's
bridge, identity, QDN or account semantics to the other merely because names or
request shapes look similar. The platform packs in Phase 1 are routing and
source references; current platform source and runtime remain authoritative.

## Historical paths

Historical `reports/`, `tasks/` and source-evidence references retain their
original workstation paths as provenance. They are not current routing. Active
files use the actual VPS layout under `/home/iffi/dev-workspace`.

## UI/product bootstrap decision

New applications may start from a neutral functional shell for platform,
routing, auth, QDN, cache, error/loading, accessibility and validation
primitives. Final branding/layout remains project-specific and is normally
applied after the important runtime flows work. This does **not** standardize all
owner applications into one visual design.

## Phase status

Phase 1 stops at control-plane establishment. Full Qortal and Qortium platform
documentation import, duplicate reconciliation, project-context migration and
any automation remain later phases.
