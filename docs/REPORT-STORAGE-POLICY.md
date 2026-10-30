# Report storage policy

Status: **mandatory and permanent** (Phase 1.6, 2026-10-30).
Applies to: OpenCode, DeepSeek, ChatGPT, Codex and any future registered agent.
Authority: this policy is part of the canonical control plane and is subordinate
only to explicit owner task instructions and the control-plane `AGENTS.md`.

## 1. Canonical root

All substantial development reports and work artifacts are stored centrally
under:

```text
/home/iffi/dev-workspace/docs/
```

Reports must never be written directly into this root, into a project repository,
or into `/tmp/`. Application technical documentation such as `README.md`,
`ROADMAP.md`, specifications and release runbooks remains inside its own project
repository.

## 2. Required structure

```text
/home/iffi/dev-workspace/docs/
├── workspace/
│   ├── audit/
│   ├── reports/
│   ├── research/
│   ├── implementation/
│   ├── validation/
│   └── handoffs/
├── Blogs/
│   ├── audit/
│   ├── reports/
│   ├── research/
│   ├── implementation/
│   ├── validation/
│   └── handoffs/
├── nodefm-station/
│   └── ...same six categories...
├── Qortium-United-Community/
│   └── ...same six categories...
├── shadow-archives-webportal-QORTAL/
│   └── ...same six categories...
├── Qortal-Video-Bridge/
│   └── ...same six categories...
└── wordpress-to-qortal/
    └── ...same six categories...
```

Every registered project has exactly one central root. Category directories are
created when the first artifact of that category is added. Do not create empty
category directories in advance.

## 3. Project mapping

| Project ID | Central documentation root | Application repository |
| --- | --- | --- |
| `qortium/blogs` | `/home/iffi/dev-workspace/docs/Blogs/` | `/home/iffi/dev-workspace/projects/Blogs` |
| `qortium/nodefm-station` | `/home/iffi/dev-workspace/docs/nodefm-station/` | `/home/iffi/dev-workspace/projects/nodefm-station` |
| `qortium/qortium-united-community` | `/home/iffi/dev-workspace/docs/Qortium-United-Community/` | `/home/iffi/dev-workspace/projects/Qortium-United-Community` |
| `qortal/shadow-archives-webportal` | `/home/iffi/dev-workspace/docs/shadow-archives-webportal-QORTAL/` | `/home/iffi/dev-workspace/projects/shadow-archives-webportal-QORTAL` |
| `qortal/qortal-video-bridge` | `/home/iffi/dev-workspace/docs/Qortal-Video-Bridge/` | `/home/iffi/dev-workspace/projects/Qortal-Video-Bridge` |
| `qortal/wordpress-to-qortal` | `/home/iffi/dev-workspace/docs/wordpress-to-qortal/` | `/home/iffi/dev-workspace/projects/wordpress-to-qortal` |
| cross-project / control plane | `/home/iffi/dev-workspace/docs/workspace/` | `/home/iffi/dev-workspace/control-plane` |

No report may be filed under another project's root. Cross-project audits,
infrastructure reports, control-plane reports and general workspace
documentation belong under `workspace/`.

## 4. Category definitions

| Category | Use for |
| --- | --- |
| `audit/` | Independent audits, path/environment/migration audits, security and compliance reviews, policy checks. |
| `reports/` | General dated task reports, status reports, infrastructure reports, environment documentation, post-task summaries. |
| `research/` | Investigations, comparisons, option analysis, reference notes and feasibility work. |
| `implementation/` | Implementation plans, design notes, change summaries and development evidence that are not application source. |
| `validation/` | Test, runtime, host, publication and owner-acceptance evidence. |
| `handoffs/` | Handoff and status artifacts intended for another agent or the owner. |

Choose the category that describes the artifact, not the agent that wrote it.
When an artifact spans categories, file it under the primary purpose and link to
related artifacts.

## 5. Storage rules

1. Every project gets its own central documentation directory.
2. Never mix reports from different projects in one project directory.
3. Cross-project, control-plane and general workspace material goes under
   `workspace/`.
4. Use descriptive filenames with dates where appropriate, for example
   `2026-10-30-<topic>-audit.md`.
5. Do not place new reports directly in the root `docs/` directory.
6. Do not store substantial reports in `/tmp/`; `/tmp` is only for transient
   command output and logs.
7. Application `README.md`, `ROADMAP.md` and product specifications remain in
   their project repository. The central tree stores reports, audits, research
   and development evidence.
8. Every substantial report is authored from
   `/home/iffi/dev-workspace/control-plane/templates/REPORT.md` and records its
   canonical path.
9. Move or copy artifacts only when necessary; update every Markdown link and
   absolute path that points at a moved artifact.
10. Do not delete reports. Historical reports retain their original paths when
    they live in preserved reference repositories, control-plane `reports/`,
    control-plane `tasks/` or other provenance archives.

## 6. Task artifacts versus central reports

The control-plane `GIT-AND-HANDOFF.md` workflow keeps the compact task controller
and status artifacts (`TASK.md`, `STATUS.json`, and any concise
`IMPLEMENTATION.md`/`AUDIT.md` handoff files) under
`/home/iffi/dev-workspace/control-plane/tasks/<project>/<task>/`.

The detailed evidence belongs in the central tree:

```text
control-plane/tasks/<project>/<task>/   compact task state and handoff
docs/<project>/<category>/<report>.md   substantial report and evidence
```

Task artifacts should link to the central report by its canonical path. They do
not replace it.

## 7. Historical material

The following are provenance and must not be moved or rewritten in this phase:

- `/home/iffi/dev-workspace/control-plane/reports/`
- `/home/iffi/dev-workspace/control-plane/tasks/`
- `/home/iffi/dev-workspace/control-plane/docs/migration/`
- preserved reference repositories such as
  `/home/iffi/dev-workspace/projects/qortal-dev-workspace` and
  `/home/iffi/dev-workspace/projects/ai-development-orchestration`

If a link from active guidance points into moved material, update the link only;
do not alter the historical report content.

## 8. Phase 1.6 migration record

Workspace-level artifacts previously stored directly in `docs/` were moved
without content changes (only self-path references were corrected):

| Previous path | New path |
| --- | --- |
| `docs/AGENT-WORKSPACE-COMPARISON.md` | `docs/workspace/audit/AGENT-WORKSPACE-COMPARISON.md` |
| `docs/AGENT-WORKSPACE-PHASE0.md` | `docs/workspace/audit/AGENT-WORKSPACE-PHASE0.md` |
| `docs/AGENT-WORKSPACE-PHASE1.md` | `docs/workspace/audit/AGENT-WORKSPACE-PHASE1.md` |
| `docs/AGENT-WORKSPACE-PHASE1.5.md` | `docs/workspace/audit/AGENT-WORKSPACE-PHASE1.5.md` |
| `docs/DEVELOPMENT-ENVIRONMENT.md` | `docs/workspace/reports/DEVELOPMENT-ENVIRONMENT.md` |

No project-specific reports existed under `docs/` at migration time, so no
project report was moved into `workspace/`.

## 9. Enforcement

- OpenCode loads this policy through
  `/home/iffi/dev-workspace/control-plane/AGENTS.md`.
- Every project `AGENTS.md` and project routing documentation names its central
  root.
- `control-plane/tools/validate_control_plane.py` must continue to pass.
- `control-plane/tools/validate_skills.py` must continue to pass.
- Validation must confirm that active absolute paths exist, active relative
  links resolve, project roots match the registry, and no report is written to
  the `docs/` root.
- A task is not complete until its report is stored in the correct project and
  category directory.
