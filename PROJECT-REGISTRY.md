# Project registry

Verified local routing: 2026-11-01 (project-scoped delivery policy).
Product state remains in the linked project context. The table verifies the
local checkout, the configured Git remote and the approved development-branch
policy. It does not import full platform documentation or project contexts.

## Registered projects

| ID | Platform | Verified local path | Project-level `AGENTS.md` | Canonical context | Central report root | Git remote | GitHub repository | Development branch pattern | Automatic push |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `control-plane/control-plane` | Control plane | `/home/iffi/dev-workspace/control-plane` | Yes | This repository | `/home/iffi/dev-workspace/docs/workspace/` | `dev-control-plane` | `iffinland/dev-control-plane` | `agent/*` | `yes` |
| `qortal/shadow-archives-webportal` | Qortal | `/home/iffi/dev-workspace/projects/shadow-archives-webportal-QORTAL` | Yes | Pending Phase 2 import. Source reference: `qortal-dev-workspace` at `b8fd2f6fbfcff88c0ab9bc8fd116d5548679d2d2` | `/home/iffi/dev-workspace/docs/shadow-archives-webportal-QORTAL/` | `origin` | `iffinland/shadow-archives-webportal-QORTAL` | `agent/*` | `yes` |
| `qortal/qortal-video-bridge` | Qortal | `/home/iffi/dev-workspace/projects/Qortal-Video-Bridge` | No; inherits this control plane | Pending Phase 2 import | `/home/iffi/dev-workspace/docs/Qortal-Video-Bridge/` | `origin` | `iffinland/Qortal-Video-Bridge` | `agent/*` | `yes` |
| `qortal/wordpress-to-qortal` | Qortal | `/home/iffi/dev-workspace/projects/wordpress-to-qortal` | No; inherits this control plane | Pending Phase 2 import | `/home/iffi/dev-workspace/docs/wordpress-to-qortal/` | `origin` | `iffinland/wordpress-to-qortal` | `agent/*` | `yes` |
| `qortium/blogs` | Qortium | `/home/iffi/dev-workspace/projects/Blogs` | Yes | Pending Phase 2 import | `/home/iffi/dev-workspace/docs/Blogs/` | `origin` | `iffinland/Blogs` | `agent/*` | `yes` |
| `qortium/qortium-united-community` | Qortium | `/home/iffi/dev-workspace/projects/Qortium-United-Community` | Yes | Pending Phase 2 import | `/home/iffi/dev-workspace/docs/Qortium-United-Community/` | `origin` | `iffinland/Qortium-United-Community` | `agent/*` | `yes` |
| `qortium/nodefm-station` | Qortium | `/home/iffi/dev-workspace/projects/nodefm-station` | Yes | Pending Phase 2 import | `/home/iffi/dev-workspace/docs/nodefm-station/` | `origin` | `iffinland/nodefm-station` | `agent/*` | `yes` |

The last four columns are the validated delivery policy used by both `dev start`
and the Telegram Dev Monitor. `Git remote` must exist in the checkout and its URL
must normalise to the configured `GitHub repository`; `Development branch
pattern` must stay inside `agent/*`; `Automatic push` authorizes only a matching
non-protected development branch. Missing, ambiguous or mismatched values refuse
the start instead of falling back to another project's remote. A different
remote, `main`/`master`/`trunk`, merges, tags, releases, deployment, QDN writes,
wallet transactions and server changes are never implied by this policy.

A project-level `AGENTS.md` may add project-specific constraints. It does not
override the control-plane safety, authority, identity or handoff rules. See
[AGENTS.md](AGENTS.md) and
[REPORT-STORAGE-POLICY.md](docs/REPORT-STORAGE-POLICY.md). Category subdirectories
are created when the first report of that category is added.

## Platform source references

These are reference repositories, not projects. Their current source and runtime
remain authoritative for implemented platform behavior.

| ID | Platform | Verified local path | Role |
| --- | --- | --- | --- |
| `qortal/platform-source` | Qortal | `/home/iffi/dev-workspace/projects/qortal-dev-workspace` | Preserved Qortal platform governance and evidence source at `main` `b8fd2f6fbfcff88c0ab9bc8fd116d5548679d2d2`; not imported into the control plane in Phase 1 |
| `qortium/home-reference` | Qortium | `/home/iffi/dev-workspace/projects/qortium-home` | Current local Home reference; re-verify branch and SHA per task |
| `qortium/core-reference` | Qortium | `/home/iffi/dev-workspace/projects/qortium-core` | Current local Core reference; re-verify branch and SHA per task |

## Deferred registry entries

The original registry also named the following projects. They are not registered
with a verified local path in Phase 1 because they are either absent from the
current workspace or represented only by historical evidence. Do not route to
the old workstation paths. Verify the actual checkout before adding a row.

- `qortal/qwb-qortal-web-builders` — QWB evidence exists in preserved Qortal
  source branches; the application checkout is not present in Phase 1.
- `qortium/community-discussion-boards`
- `qortium/discussion-boards`
- `qortium/iffi-vaba-mees`
- `qortium/my-private-room`
- `qortium/video-center`

## Registration rule

A project is registered only after its local path, platform, current branch and
delivery policy are verified. The policy requires all four columns: Git remote
name, matching GitHub repository, `agent/*` development branch pattern and an
explicit `Automatic push` value. Verify with
`python3 -c "from devjob.project_policy import resolve; print(resolve('<path>'))"`
from `tools/`, or simply run `dev start ... --dry-run`. Do not infer a project
from a similarly named directory or reuse another project's remote.
Project-specific facts belong in the project context, not in this registry or in
global guidance.
