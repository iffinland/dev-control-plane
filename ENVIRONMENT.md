# Environment and reference registry

Updated: 2026-10-30 (Phase 1). This registry records non-secret paths and
reference state used by the control plane. It does not grant access, configure
tunnels, or authorize server changes.

## Workspace paths

| ID | Verified VPS path | Role |
| --- | --- | --- |
| `control-plane` | `/home/iffi/dev-workspace/control-plane` | Canonical agent control plane |
| `projects-root` | `/home/iffi/dev-workspace/projects` | Local project and source checkouts |
| `central-docs` | `/home/iffi/dev-workspace/docs` | Canonical central report storage, grouped by project and category |
| `source-references` | `/home/iffi/dev-workspace/docs/references` | Preserved third-party and source documents with provenance; reference material, not platform authority |
| `phase0-backups` | `/home/iffi/dev-workspace/backups/agent-workspaces-20261030` | Verified Phase 0 backups including `.git` |
| `qortal-platform-source` | `/home/iffi/dev-workspace/projects/qortal-dev-workspace` | Preserved Qortal platform source; `main` `b8fd2f6fbfcff88c0ab9bc8fd116d5548679d2d2` |
| `orchestration-migration-source` | `/home/iffi/dev-workspace/projects/ai-development-orchestration` | Preserved migration repository; do not modify in Phase 1 |
| `qortium-home-reference` | `/home/iffi/dev-workspace/projects/qortium-home` | Qortium Home reference checkout |
| `qortium-core-reference` | `/home/iffi/dev-workspace/projects/qortium-core` | Qortium Core reference checkout |

## Network and node boundary

No live node endpoint, tunnel, credential, API key, wallet, or service state is
asserted as current by Phase 1. The prior environment registry contained dated
tunnel and node details tied to an earlier workstation; those are historical
evidence, not current routing.

At task time, verify the intended environment from owner-local configuration and
record:

- transport and exact endpoint actually used;
- network (mainnet/testnet) and node/host version;
- read/write permission boundary;
- observation timestamp and evidence;
- whether the evidence is node API, real host, or published QDN behavior.

Keep credentials, wallet data and private infrastructure details in owner-local
configuration. Never commit them to this repository or copy them into task
artifacts.

## Reference checkouts

Reference repositories must be verified per task. Do not assume a cached branch,
SHA, worktree, or remote-tracking ref is current.

| Reference | Local path | Notes |
| --- | --- | --- |
| Qortal platform source | `/home/iffi/dev-workspace/projects/qortal-dev-workspace` | Preserved at the Phase 0 baseline; newer evidence branches remain on the remote |
| Qortium Home | `/home/iffi/dev-workspace/projects/qortium-home` | Verify branch, HEAD and dirty state before use |
| Qortium Core | `/home/iffi/dev-workspace/projects/qortium-core` | Verify branch, HEAD and dirty state before use |

Other references cited in historical reports or skills may not exist in this VPS
layout. Treat their old paths as historical provenance and resolve the current
checkout before relying on them.

## Mandatory freshness gate

Before platform-dependent design, implementation or validation:

1. Resolve the exact required Core, Home/Hub, framework and donor references.
2. Record path, remote, branch, HEAD, dirty files and linked worktrees.
3. Check the upstream branch live and record UTC time and upstream SHA. A cached
   origin ref is not a freshness check.
4. Preserve intentional pins and dirty owner checkouts. Use an isolated clean
   worktree if needed. Never reset, clean, auto-stash, force-update, or relocate
   owner work.
5. Record the actual inspected revision and relevant source paths.
6. State missing evidence as a blocker for any dependent claim.

Reference freshness does not authorize commits, pushes, deployments, QDN writes,
signing, transactions, issue mutation or server changes.
