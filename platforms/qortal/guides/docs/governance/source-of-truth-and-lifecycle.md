# Source of Truth and Documentation Lifecycle

## Purpose

Define where Qortal facts and rules belong, how conflicts are resolved, and how
active guidance is separated from project documentation and historical reports.

## Authority by subject

### Platform behavior

Use this order:

1. current checked-out Qortal Core (`Qortal/qortal`) source and rendered
   behavior;
2. current application host source (Qortal Hub / gateway node) for host-side
   behavior;
3. current Q-App framework source (`qapp-core`, `qapp-templates`) for framework
   behavior;
4. verified runtime behavior tied to an exact node, host and revision;
5. current project source and tests;
6. canonical shared guidance in this workspace;
7. official Qortal documentation pages;
8. historical reports and prior conversation.

Source beats documentation when they disagree. Runtime evidence proves what the
observed environment did; it does not prove that a different revision or node
behaves identically. Record provenance when the distinction matters.

**Known documentation/source discrepancy (2026-09-11):** the Q-Apps API page
documents only `_qdnTheme` and `_qdnContext`, while Core's `HTMLParser` injects
`_qdnContext`, `_qdnTheme`, `_qdnLang`, `_qdnService`, `_qdnName`,
`_qdnIdentifier`, `_qdnPath`, `_qdnBase` and `_qdnBaseWithPath`. Source wins.

### Factual / implemented-state authority

For "what does the platform or application actually do", use this order:

1. current project source and Git history;
2. durable project documentation in the application repository;
3. verified runtime behavior tied to an exact revision and environment;
4. `projects/<project-slug>.md` and historical task reports (dated snapshots).

Project context summarizes verified current facts and routing. It MUST NOT
override current source, and stale snapshots MUST be dated and labelled.

### Product / authorization authority

For "what should the product do" and "what changes are authorized", owner
decisions are authoritative. They are recorded in `projects/<project-slug>.md`
and in explicit owner-decision statements in active guidance.

- Owner decisions determine desired product behavior and authorize changes;
  they are not subordinate to the existing implementation.
- If implementation contradicts a documented owner product decision, that is
  evidence of an implementation gap. The implementation does not automatically
  override the owner decision; the conflict MUST be reported and resolved by the
  owner.
- Owner decisions cannot override verified platform facts. A decision that
  contradicts a VERIFIED Core/host/framework capability or limit MUST be
  surfaced as an owner/implementation conflict, not silently coded around.

### Shared workflow and governance

Use this order:

1. current local `qortal-dev-workspace` working tree for active editing;
2. approved committed revision in this repository;
3. GitHub mirror of the approved revision;
4. legacy workspace or project-local agent guidance only as migration evidence.

Pending uncommitted governance content is locally authoritative for the active
review session but is not an approved published standard until reviewed and
committed.

## Content ownership

| Content | Canonical location |
| ------- | ------------------ |
| Minimum agent contract and routing | `AGENTS.md`, `agents/` |
| Workflow v2 execution contract | `docs/workflows/workflow-v2.md` |
| Reusable dApp architecture rules | `docs/architecture/` |
| Agent-specific constraints | `agents/roles/` |
| Current shared project context | `projects/<slug>.md` |
| Reusable task/report shapes | `templates/` |
| Durable application architecture/API/operator/release docs | application repository `docs/` |
| AI audits, investigations, implementations, runtime reports, validation, reviews, handoffs | `docs/<slug>/` in this workspace |
| Platform implementation truth | current Qortal Core / Hub / framework repositories |

Global rules MUST NOT be copied into application repositories. A project
`AGENTS.md` is a thin entry point containing only project-specific deltas and a
route to this repository.

## Fact state

Separate:

- **VERIFIED CURRENT** — checked against current source or measured runtime;
- **VERIFIED HISTORICAL** — true for a recorded revision/environment;
- **INFERENCE** — supported but not directly proven;
- **UNKNOWN** — evidence unavailable;
- **OWNER DECISION** — product or authority choice not derivable from source.

Do not call a dated report "stale" merely because it is historical. The problem
is presenting historical evidence as current guidance without provenance.

## Document lifecycle

### Active canonical guidance

Active guidance is linked from `AGENTS.md`, the session router, or the routed
guide index. It must be maintained, internally consistent, and free of
project-specific facts unless the file is under `projects/`.

### Durable project documentation

Application READMEs and `docs/` contain product identity, architecture, data
models, APIs, migration specifications, operator guidance, and reproducible
release/provenance procedures. They do not store AI task reports.

### Historical reports

Reports preserve what was inspected, changed, measured or concluded at a
specific time. Do not rewrite their evidence to match current behavior. Mark
supersession through an index or a later report.

### Legacy guidance

Before removing legacy guidance:

1. inventory it;
2. classify reusable, project-specific, obsolete, and unsafe material;
3. migrate reusable rules into the correct active guide;
4. record the migration in `agents/README.md`;
5. remove the duplicate rather than leaving two authorities.

## Local and GitHub lifecycle

- Edit locally in this workspace.
- Treat the working tree as authoritative during an active session.
- Commit/push only with explicit owner authorization.
- Do not create parallel governance copies in project repositories.

## Conflict handling

1. Identify which authority tier each claim belongs to.
2. Prefer the higher tier.
3. If source and documentation conflict, follow source and report the
   discrepancy.
4. If a conflict cannot be resolved from evidence, mark it UNKNOWN or OWNER
   DECISION and stop dependent work.
5. Never silently change a documented architecture decision.

## Completion criteria

- Facts are labelled and sourced.
- No umbrella or project-specific rule is duplicated across tiers.
- Platform claims are traceable to a revision or explicitly unknown.
- Reports live only under the canonical report root.

## Related files

- [`../workflows/workflow-v2.md`](../workflows/workflow-v2.md)
- [`../workflows/report-storage-policy.md`](../workflows/report-storage-policy.md)
- [`../../../../../AGENTS.md`](../../../../../AGENTS.md)
