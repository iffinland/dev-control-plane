---
name: qortal-qdn-authority-integrity
description: Use when designing or auditing Qortal QDN ownership, identity, derived indexes, engagement operations, immutability claims or rich-text rendering safety.
---

# Qortal QDN Authority and Data Integrity

- Platform: `qortal`
- Maturity: `verified-reference`
- Last checked: `2026-11-01`
- Owner: shared capability library

## Use when

Use for QDN entity/operation modelling, owner detection, moderation and
authority boundaries, deterministic reduction, legacy migration, tombstones,
derived catalogs/indexes, or rendering untrusted rich text.

## Do not use when

Do not use architecture reasoning as a substitute for runtime measurement, live
validation or current Core/host source inspection. Do not apply it to Qortium.
It does not authorize publication or moderation writes.

## Authoritative evidence

- Qortal Core `Service.java`, QDN arbitrary-resource APIs and status source.
- Current Qortal Hub/framework source for host and `qapp-core` conventions.
- Migrated detail:
  [`qortal-architecture-and-data-integrity.md`](../../../platforms/qortal/guides/agents/qortal-architecture-and-data-integrity.md)
  and the
  [`Qortal dApp Development Standard`](../../../platforms/qortal/guides/docs/architecture/qortal-dapp-development-standard.md).

## Reusable contract / procedure

1. **Authority is name ownership.** A resource is addressed by
   `(name, service, identifier)` and publishing/overwriting requires current
   ownership of that registered name. Payload `author`/`owner` text, display
   names, client timestamps, "latest publisher" and derived indexes never grant
   authority. Ownership can transfer; resolve it fresh per session.
2. **Separate entities from operations.** A content entity is owned by its
   publisher; a like/comment/tip/share is an operation resource owned by the
   actor. Authority applies to the resource being created or updated; a target
   reference is validated independently but need not be owned by the actor.
3. **Trusted vs untrusted.** Trust the resource address and node-reported
   metadata/status; treat the payload as untrusted. Schema validation does not
   establish publisher authority or rendering safety.
4. **Reduce fail-closed.** Discovery -> trusted metadata -> strict schema ->
   identity/authority -> deterministic ordering -> entity reduction ->
   operation reduction -> diagnostics/quarantine. Use node timestamps plus
   deterministic tie-breakers; never make client timestamps the sole authority.
5. **Derived state is non-authoritative.** Catalogs, indexes, counts and caches
   must be rebuildable, versioned and honest about stale/partial/unavailable
   state. They must not become ownership proof or block first authoritative
   render.
6. **Immutability language.** QDN has no on-chain delete; `DELETE_HOSTED_DATA`
   removes only locally hosted data and does not remove the on-chain record.
   The framework tombstone convention is overwrite-and-filter, not deletion.
   Never claim content was removed from the network.
7. **Confidentiality.** UI visibility or an allowlist is authorization, not
   confidentiality. Only encryption to recipient public keys supports a privacy
   claim.
8. **Rendering safety is separate.** Escape plain text. Sanitize rich/stored
   HTML with a maintained sanitizer or constrained safe document model; block
   scripts, `on*` handlers and dangerous URL schemes; ensure post-sanitization
   transformations cannot reintroduce unsafe markup. Owner-authored content is
   not exempt.

## Freshness and compatibility gate

Record the current Core/Hub/framework revisions and re-read the relevant source
before relying on any service limit, status value or tombstone convention. QDN
and `qapp-core` behavior can change; a dated report is evidence, not current
truth. Refresh this skill when authority, deletion/tombstone or rendering
guidance changes.

## Validation

- Positive and negative authority tests for each entity and operation,
  including liking/commenting on another author's content.
- Forged payload author/owner tests.
- Deterministic reduction across permutations and duplicate/conflict inputs.
- Idempotency and tombstone tests.
- Malicious HTML/URL fixtures: script tags, event-handler attributes,
  `javascript:`/`data:` URLs and post-sanitization transformations.
- Legacy reader/normalization tests and partial/unavailable discovery tests.

## Known failure modes

- Inferring authority from payload fields or a derived catalog.
- Letting an unrelated publisher overwrite authoritative state.
- Presenting a partial count as a total or a derived index as proof.
- Claiming deletion/moderation removed network content.
- Rendering schema-valid but unsafe HTML, or trusting owner-authored stored HTML.
- Claiming privacy from UI hiding or an allowlist.

## Non-goals

Not a product authorization model, delegated-moderation design, sanitizer
library choice or Qortium contract. It does not authorize mutations.

## Harvest / maturity update

Created 2026-11-01 from the legacy Qortal architecture/data-integrity and
development-standard guides. Maturity is `verified-reference`; source-linked
claims were not re-run against current live Qortal in this migration. Promote
after a current source check and representative runtime/authority tests.
