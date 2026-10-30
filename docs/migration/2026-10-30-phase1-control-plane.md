# Phase 1 — Canonical control-plane migration record

Date: 2026-10-30
Status: Phase 1 complete; no commit or push

## Source

```text
Repository: /home/iffi/dev-workspace/projects/ai-development-orchestration
Remote:     https://github.com/iffinland/ai-development-orchestration.git
Branch:     origin/agent/shadow-archives/qdn-grouped-publish-outcome-20261001
Commit:     aef3e1ed45c66ef2382e5cc794665d1720f7ad77
Tree:       d699f691edaab47b22c9171e3958e99b8d6e594d
```

The source repository was not modified. The new workspace was created by a
separate single-branch clone from the GitHub remote, then checked out on a new
local branch at the exact commit.

## Destination

```text
Path:   /home/iffi/dev-workspace/control-plane
Branch: phase1/control-plane
Base:   aef3e1ed45c66ef2382e5cc794665d1720f7ad77
Remote: https://github.com/iffinland/ai-development-orchestration.git
```

The destination remote is retained for provenance. No commit, push, tag or PR
was created.

## Imported unchanged

The validated orchestration material was reused rather than rewritten:

- `WORKFLOW.md`
- `GIT-AND-HANDOFF.md`
- `roles/`
- `skills/` including the 15 active skills, index and template
- `tools/validate_skills.py`
- `templates/` including `TASK`, `STATUS`, `HANDOFF`, `REPORT`
- `reports/` and `research/` as historical evidence
- `tasks/` as historical task artifacts
- `CLAUDE.md` as a thin future adapter

Historical reports and task artifacts retain their original paths as provenance.
They are not current routing.

## Added or changed in the new workspace

Added:

- `platforms/README.md`
- `platforms/qortal/README.md`
- `platforms/qortium/README.md`
- `adapters/opencode/README.md`
- `adapters/deepseek/README.md`
- `docs/migration/2026-10-30-phase1-control-plane.md`

Changed:

- `AGENTS.md` — canonical workspace, OpenCode/DeepSeek discovery, instruction
  precedence and platform-pack routing
- `README.md` — control-plane orientation, current baseline, structure, clients,
  platform boundary and Phase 1 status
- `PROJECT-REGISTRY.md` — verified VPS project paths; deferred unverified entries
- `ENVIRONMENT.md` — current VPS paths; removed assertions about unverified node
  endpoints and replaced them with a task-time freshness gate
- `GIT-AND-HANDOFF.md` — current worktree root
- `templates/TASK.md` — current contract path
- Four Qortal skills — current Qortal evidence root and note that some evidence
  lives on preserved branches

No application source or full platform documentation was imported.

## Path corrections

Active control-plane paths now use:

```text
/home/iffi/dev-workspace/control-plane
/home/iffi/dev-workspace/projects
/home/iffi/dev-workspace/backups/agent-workspaces-20261030
```

The old `/home/iffi/VsCodec-Projects/...` and uppercase `AI-Orchestration` paths
remain only inside historical reports, task artifacts and source-evidence
citations. They are provenance, not routing. They must not be treated as current
locations.

## Platform boundary

Qortal and Qortium are separate packs. Full platform documentation import is
deferred. Their current source and runtime remain authoritative. Qortium runtime,
node configuration, services, databases, wallets and data were not touched.

## OpenCode and DeepSeek

OpenCode loads `/home/iffi/dev-workspace/control-plane/AGENTS.md` through the
owner's global instructions setting. DeepSeek reads the same canonical files.

Precedence is owner task instructions, control-plane safety/authority, platform
pack, project-level deltas, skills, then historical evidence. Current platform
source/runtime outranks all summaries for behavior.

Existing project-level `AGENTS.md` files are not overwritten. They inherit the
control plane and declare only project-specific deltas.

No automatic commit, push, publish, deployment, background agent, polling,
scheduler or task execution is configured.

## Preservation

- Phase 0 backups remain at
  `/home/iffi/dev-workspace/backups/agent-workspaces-20261030/`.
- The original orchestration repository remains at
  `agent/orchestration/bootstrap` @ `c52e048...` and was not modified.
- The Qortal repository remains at `main` @ `b8fd2f6...` and was not modified.
- All Phase 0 remote branch refs remain intact.

## Deferred

- Full Qortal/Qortium platform documentation import.
- Project context migration.
- Duplicate/conflict reconciliation between platform guides and skills.
- Any task execution or automation.
- Any commit, push, merge, deployment, publication or release.
