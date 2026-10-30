# Reusable capability library

This directory is the canonical cross-project library of reusable development
capabilities for Qortal and Qortium. A skill is not generic advice and it is not
a project diary. It is a compact, reusable procedure or verified platform
contract that prevents agents from rediscovering the same integration on every
application.

## Why this exists

The orchestration workflow previously routed every substantial platform concern
back through source inspection and audit. That is safe but wasteful when the
same capability has already been proven. The new rule is:

```text
new requirement
-> search applicable skills first
-> verify skill freshness against current platform source/runtime
-> reuse when still valid
-> investigate only the missing or changed delta
-> validate the result
-> harvest reusable new knowledge back into the skill library
```

An audit should become a durable investment. A platform fact discovered for one
application must not remain trapped in that application's report when it is
reusable elsewhere.

## Platform boundary

Every skill declares one of:

- `qortal` — Qortal-specific contracts and references;
- `qortium` — Qortium-specific contracts and references;
- `shared` — workflow or application-engineering capability that does not assume
  one network's bridge/API semantics.

Never apply a Qortal skill to Qortium, or the reverse, merely because names and
APIs look similar. Qortal and Qortium source/runtime remain separate authority.
Platform routing boundaries are defined in
[`platforms/qortal`](../platforms/qortal/README.md) and
[`platforms/qortium`](../platforms/qortium/README.md).

Skills are summaries of reusable evidence. Current platform source/runtime
outranks them. Some historical evidence files cited by skills live on preserved
Qortal branches; verify the branch and file before citing them.

## Maturity

Every skill carries a maturity state:

- `candidate` — promising reusable pattern, but the complete contract has not
  yet passed our own required runtime validation;
- `verified-reference` — current authoritative source and one or more working
  implementations establish the contract, but our own target runtime has not
  yet proven it end to end;
- `verified-runtime` — required source checks and our own real runtime validation
  have passed;
- `stale` — an invalidation trigger fired or a compatibility check found drift;
- `retired` — intentionally superseded; retain only when historical context is
  useful.

A `candidate` can guide investigation but cannot replace validation. A
`verified-reference` can normally replace a full rediscovery audit with a
bounded compatibility check. A `verified-runtime` is the preferred reusable
path until its freshness gate fails.

## Skill index

This table is the routing index for the library: match the requirement to a
skill path, load only the matching skills, then run that skill's own
freshness/compatibility gate before reuse. `Last checked` is the skill's own
header date, not the date of the underlying platform revision.

| Skill | Platform | Maturity | Use for | Last checked |
| --- | --- | --- | --- | --- |
| [`skills/qortal/cross-app-video-publishing/SKILL.md`](qortal/cross-app-video-publishing/SKILL.md) | `qortal` | `verified-runtime` | Q-Tube-compatible public video publication, `qtube_vid_` identifiers, media/metadata split, discovery and partial-publish semantics. | `2026-09-13` |
| [`skills/qortal/subwire-article-publishing/SKILL.md`](qortal/subwire-article-publishing/SKILL.md) | `qortal` | `verified-runtime` | SubWire-compatible article `DOCUMENT`: qapp-core identifier math, payload, bare-base64 WebP cover, prefix discovery, unsanitized-renderer constraint. | `2026-09-13` |
| [`skills/qortal/quitter-announcement/SKILL.md`](qortal/quitter-announcement/SKILL.md) | `qortal` | `verified-runtime` | Optional, separately approved SubWire-style Quitter announcement of a published article. | `2026-09-13` |
| [`skills/qortal/qdn-derived-index-coherence/SKILL.md`](qortal/qdn-derived-index-coherence/SKILL.md) | `qortal` | `verified-runtime` | Derived QDN index over authoritative entities: reconciliation, bounded discovery, stale/unreadable recovery, convergence/repair. | `2026-09-13` |
| [`skills/qortal/bridge-fetch-qdn-resource-normalization/SKILL.md`](qortal/bridge-fetch-qdn-resource-normalization/SKILL.md) | `qortal` | `verified-runtime` | Normalizing JSON-parsed `FETCH_QDN_RESOURCE` bridge results at the transport boundary. | `2026-09-13` |
| [`skills/qortal/private-chat-contact-form/SKILL.md`](qortal/private-chat-contact-form/SKILL.md) | `qortal` | `verified-runtime` | Direct Qortal private-chat Contact forms: current-name recipient resolution, host approval, truthful submission/ambiguity UX, retention and no-retry boundaries. | `2026-09-15` |
| [`skills/qortal/qdn-content-crud/SKILL.md`](qortal/qdn-content-crud/SKILL.md) | `qortal` | `verified-runtime` | Per-entity QDN create/update/reorder/tombstone under the app's own name: revision-in-payload, read-back verification, media-before-entity ordering, single-file media URL rule, `mode=ALL` discovery, and per-item normalisation of grouped publish failures. | `2026-10-01` |
| [`skills/qortal/registered-name-owner-mode/SKILL.md`](qortal/registered-name-owner-mode/SKILL.md) | `qortal` | `verified-runtime` | Automatic owner/visitor decision from the injected context globals and `GET_USER_ACCOUNT`/`GET_ACCOUNT_NAMES`, fail-closed, no persisted authority. | `2026-09-16` |
| [`skills/qortal/inline-owner-editing/SKILL.md`](qortal/inline-owner-editing/SKILL.md) | `qortal` | `verified-runtime` | In-page owner controls: per-action re-check, truthful submitted/verified/rejected/ambiguous vocabulary, draft survival, no automatic retry, manual owner-mode re-check. | `2026-09-16` |
| [`skills/qortium/account-write-gate/SKILL.md`](qortium/account-write-gate/SKILL.md) | `qortium` | `verified-runtime` | One shared account-write gate: read-only/playback never unlocks, locked writes open Home's own unlock UI and resume the original write, cancel = zero writes, password stays in Home; lock-state `loading` is not an identity change and page-local state survives the unlock. | `2026-09-18` |
| [`skills/qortium/qdn-resource-discovery/SKILL.md`](qortium/qdn-resource-discovery/SKILL.md) | `qortium` | `verified-reference` | Qortium publisher enumeration vs search discovery (`LIST_QDN_RESOURCES` vs `SEARCH_QDN_RESOURCES`). | `2026-09-13` |
| [`skills/qortium/qdn-media-readiness/SKILL.md`](qortium/qdn-media-readiness/SKILL.md) | `qortium` | `verified-reference` | Qortium AUDIO/VIDEO readiness before playback and bounded fetch/poll. | `2026-09-13` |
| [`skills/qortium/home2-qdn-publishing/SKILL.md`](qortium/home2-qdn-publishing/SKILL.md) | `qortium` | `verified-runtime` | Home 2 source-token publishing: select/stage and publish as separate phases, token-only publish, refused inline/path/fee fields, ten-item batch with distinct tokens, per-item result, unknown-outcome and proof-of-work-deadline handling, Unicode source filenames, owner release-archive path and served-bundle-hash gate. | `2026-09-18` |
| [`skills/shared/app-bootstrap/SKILL.md`](shared/app-bootstrap/SKILL.md) | `shared` | `verified-reference` | Functional app shell before product-specific branding. | `2026-09-13` |
| [`skills/shared/capability-harvest/SKILL.md`](shared/capability-harvest/SKILL.md) | `shared` | `verified-runtime` | Post-task decision to promote a finding into this library. | `2026-09-13` |

Qortal and Qortium skills are not interchangeable. A Qortal bridge/QDN behavior
must not be assumed for Qortium, or the reverse.

## Required skill contents

Use [`_template/SKILL.md`](_template/SKILL.md). Each skill must state:

- platform and maturity;
- when to use it and when not to;
- authoritative source revisions and proven donor implementations;
- exact reusable contract/procedure;
- assumptions and invalidation triggers;
- compatibility/freshness check;
- required validation layers;
- known failure modes and non-goals;
- what evidence upgrades or downgrades maturity.

Do not copy large platform source files into this repository. Record the exact
repo, revision, source path, relevant contract and validation evidence.

## Quality gate

Run this command at the end of every skill creation, normalization, or
promotion, before handoff:

```bash
python3 tools/validate_skills.py
```

The command is dependency-free and enforces canonical metadata/headings,
platform and maturity boundaries, dated freshness rules for `verified-runtime`
skills, valid relative links, duplicate detection, and exact index coverage.
A skill change is incomplete until this command passes. The index is not
maintained by convention alone: every active skill under `shared/`, `qortal/`,
and `qortium/` must appear in the table above exactly once.

## Skill selection

At task start, agents read only skills relevant to the outcome. Do not load the
whole library. The task controller records the selected skills and their
freshness result.

If no matching skill exists, investigate from current authoritative source and
working implementations. After validation, run the capability-harvest skill to
decide whether the result should become a new skill or update an existing one.

## Claude readiness

The canonical skill source is this `skills/` tree, not a Claude-only copy.
Current active agents remain ChatGPT, Codex and DeepSeek. `CLAUDE.md` is a thin
future adapter only. When Claude Code is actually enabled, add the minimum
version-current discovery adapter (for example `.claude/skills -> ../skills` if
that remains supported) rather than duplicating the skill contents.
