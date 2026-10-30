# Qortium platform pack

Status: **Phase 1 boundary and source reference only.** Full Qortium platform
documentation is not imported here yet.

## Source boundary

A canonical Qortium platform governance workspace has not been verified in this
VPS layout. The legacy `/home/iffi/VsCodec-Projects/Qortium/qortium-dev-workspace`
path from the migration source is historical and must not be assumed to exist.

Current local reference checkouts:

| Reference | Local path | Note |
| --- | --- | --- |
| Qortium Home | `/home/iffi/dev-workspace/projects/qortium-home` | Verify branch, HEAD and dirty state before use |
| Qortium Core | `/home/iffi/dev-workspace/projects/qortium-core` | Verify branch, HEAD and dirty state before use |

These are reference repositories, not a substitute for a canonical Qortium
platform pack. Their source and observed runtime remain authoritative for
Qortium behavior.

## Current routing

- Start with the control-plane [AGENTS.md](../../AGENTS.md) and
  [WORKFLOW.md](../../WORKFLOW.md).
- Use Qortium skills only for Qortium tasks.
- Verify current Qortium Home/Core source and runtime before relying on a skill
  or historical report.
- Do not modify the running Qortium node, its configuration, services, data or
  wallets as part of an agent task.

## Deferred to a later phase

- Resolution or reconstruction of the canonical Qortium platform workspace.
- Import of Qortium platform guides and project contexts.
- Deduplication between Qortium guides and Qortium skills.
- Any commit, push, deployment, QDN write or release action.
