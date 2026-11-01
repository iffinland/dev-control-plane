# Qortal Architecture and Data Integrity

## Purpose

Define reusable rules for authority, identity, deterministic reduction,
independent operations, access boundaries, immutability and compatibility in
QDN-backed Qortal applications.

## Use when

Use for architecture design or audit, security and data-integrity work, shared
mutable QDN state, moderation/roles, engagement models, and migrations.

## Do not use when

Do not use architecture reasoning as a substitute for runtime measurement, UI
validation, or current Core/host source inspection.

## Prerequisites

- Product entity and operation inventory.
- Current application read/write paths.
- Current Qortal Core/host/framework revisions.
- Known compatibility and migration requirements.

## Required inputs

- Entity types and immutable IDs.
- Publisher name, address and actor evidence.
- Mutation and moderation requirements.
- Trusted QDN metadata available to reducers.
- Legacy formats and current live-data patterns.

## Workflow

### 1. Establish authority

For every entity determine:

- publisher (name) and the service/identifier that address it;
- required name ownership;
- immutable fields;
- owner-edit fields;
- moderator/admin fields, if any (owner decision);
- forbidden cross-domain fields;
- transfer behaviour — ownership of a name can change, and update authority
  moves with it;
- tombstone/deactivation behaviour.

**VERIFIED.** In QDN, a resource is owned by a registered **name**. Publishing or
overwriting requires current ownership of the `name`. Do not infer authority
from embedded `author`/`owner` fields, arbitrary display text, client
timestamps, "latest publisher", or derived indexes.

### 2. Separate entities from operations

Represent actions independently when they have different actors, ordering or
authorization: edits, likes/reactions, comments, tips, moderation, deletion,
access changes. An operation MUST NOT replace an authoritative entity snapshot
unless replacement is the explicit validated model.

Distinguish a **content entity** (a post, video or article owned by its
publisher name) from an **interaction/operation resource** (a like, comment,
tip or share created by the actor who performs the action). Liking or
commenting on another author's content creates an operation resource under the
actor's own name; it does NOT require the actor to own the target content.

### 3. Define trusted versus untrusted data

Trusted: the resource's `name`, `service`, `identifier`, and the node-reported
`created`/`updated` metadata and status.

Untrusted: everything inside the payload. Payload claims MUST NOT overwrite
trusted metadata. **VERIFIED** (official docs): QDN is permissionless, so it is
impossible to prove that a resource was published by a particular app; validate
content against an expected schema instead.

Schema validation is **not** rendering safety. A payload can satisfy its schema
while carrying HTML that executes in the app. Schema validation, publisher
authority validation and rendering safety are three separate concerns; see
§11 for the reusable rendering-safety requirement.

### 4. Validate identity and permissions

Validate, in order:

1. the resource's `name` matches the claimed publisher name;
2. the acting account currently owns that name (resolve fresh; the selected
   account from `GET_USER_ACCOUNT` is an address, not a name);
3. the actor holds authority over the operation resource being created or
   updated (for example a like/comment resource published under the actor's own
   name); authority applies to that resource, not to the target content;
4. any target/parent reference is validated independently for exact identity
   and plausibility; the target need not be owned by the actor, but a forged or
   mismatched parent MUST be rejected;
5. operation fields satisfy a field-level policy.

Current ownership MUST NOT be substituted for historical ownership without
evidence.

### 5. Order deterministically

Use node-reported creation/update metadata and deterministic tie-breakers.
Client-supplied timestamps MAY be content metadata but MUST NOT be the sole
authority or the only ordering key. Define idempotency and conflicting-operation
handling.

### 6. Reduce fail-closed

Recommended pipeline:

```text
raw discovery (paginated, bounded)
-> trusted metadata validation
-> strict envelope/schema parsing
-> identity and authority validation
-> deterministic ordering
-> entity reduction
-> independent operation reduction
-> diagnostics / quarantine
-> derived view and index generation
```

Malformed, forged, conflicting, unavailable, unauthorized or missing-target
records need stable rejection/quarantine codes. Authority-sensitive paths MUST
fail closed. Safe read-only legacy data MAY be shown through an explicitly
non-authoritative compatibility adapter.

### 7. Keep derived state non-authoritative

Indexes, catalogs, directories, caches, counts and search hints:

- MUST be derived and validated;
- MUST NOT establish ownership or replace entities;
- SHOULD be rebuildable and partitioned;
- MUST expose stale, partial and unavailable states;
- MUST NOT block first useful authoritative render unless required for
  correctness.

### 8. Immutability and correct language

**VERIFIED.** QDN has no on-chain delete. `DELETE_HOSTED_DATA` removes only
locally hosted data, is refused on public/gateway nodes, and does not remove the
on-chain record. The current framework's "delete"-convention is to overwrite
the resource with a small placeholder payload and filter it back out on read
(revision-scoped `qapp-core` behavior, not a timeless Core rule).

Therefore:

- Never claim user content was deleted from QDN.
- Never claim a moderation action removed content from the network.
- Use honest states: hidden in this app, filtered locally, unliked/deactivated,
  superseded.
- Design moderation as an app-local presentation/authority layer, and document
  its limits in the project context.

### 9. Access boundaries

UI visibility or an address allowlist is an authorization boundary, not a
confidentiality boundary. Only encryption to recipient public keys (for example
`MAIL_PRIVATE`, `*_PRIVATE` services) can support a confidentiality claim. Do not
claim privacy that the data model does not provide.

### 10. Compatibility and migration

Define:

- strict legacy readers plus canonical normalization;
- provenance on normalized records;
- precedence between legacy and new state;
- migration/adoption evidence (including whether re-publication is required);
- quarantine for unresolved authority;
- rollback/correction strategy.

MUST NOT auto-adopt unresolved legacy authority from payload authors or
timestamps. QDN resources are addressed by `(name, service, identifier)`, so a
migration usually means publishing a new resource or a new schema version
alongside the old one, not mutating history.

### 11. Render untrusted content safely

Schema validation, publisher/authority validation and rendering safety MUST be
treated as three separate concerns. A valid schema and a trusted publisher do
not make stored or transmitted HTML safe, and running script inside the app can
alter the UI and invoke the `qortalRequest()` bridge.

This is a reusable global rule. Apply it to comments, rich-text posts, imported
content, owner preview, cached/stored content, and content from any other
publisher. Owner-authored content is **not** exempt: stored or imported HTML can
still be malformed or dangerous.

**PLAIN TEXT**

- escape and render as text;
- MUST NOT be interpolated as trusted HTML.

**RICH HTML**

- sanitize untrusted or stored HTML with a maintained sanitizer, or render a
  constrained safe document model;
- explicitly block or remove scripts, event-handler attributes (`on*`) and
  other executable markup;
- validate allowed URL schemes;
- handle `javascript:`, `data:` and other dangerous URLs intentionally;
- sanitize or validate media/link transformations;
- transformations applied **after** sanitization MUST NOT reintroduce unsafe
  markup.

Choose a specific sanitizer/editor per project and record it in
`projects/<project>.md`; do not treat this global rule as a library decision.

**Validation fixtures.** Any feature that renders untrusted or stored content
MUST include malicious HTML and URL fixtures: script tags, event-handler
attributes, `javascript:` and `data:` URLs, and post-sanitization
transformation cases.

## Mandatory rules

- Decentralized MUST NOT mean unvalidated.
- New applications MUST NOT begin with a v1 write model and later add parallel
  authority systems.
- Unrelated publishers MUST NOT replace authoritative state.
- Operation domains MUST NOT mutate each other's fields.
- A count derived from a partial scan MUST NOT be presented as a total.
- Schema validation and publisher authority MUST NOT be treated as HTML
  rendering safety.
- Untrusted HTML MUST be sanitized or rendered through a constrained safe
  document model; a transformation after sanitization MUST NOT reintroduce
  unsafe markup.
- Partial discovery MUST NOT grant authority.
- Payload identity claims MUST NOT grant authority.

## Validation

- Authority tests for each entity and operation, including the negative cases,
  including liking/commenting on another author's content.
- Forged author/owner payload tests.
- Deterministic reduction across input permutations.
- Idempotency, duplicate-like and tombstone tests.
- Rich-text rendering tests with malicious HTML/URL fixtures: script tags,
  event-handler attributes, `javascript:`/`data:` URLs and post-sanitization
  transformations.
- Legacy reader and normalization tests.
- Partial/unavailable discovery tests.

## Completion criteria

- Entity/operation authority is explicit and verified.
- Trusted versus untrusted data is separated.
- Immutability and moderation claims are truthful.
- Derived state cannot establish authority.

## Related files

- [`qortal-qdn-and-bridge.md`](qortal-qdn-and-bridge.md)
- [`qdn-publication-discovery-and-scaling.md`](qdn-publication-discovery-and-scaling.md)
- [`live-qdn-validation.md`](live-qdn-validation.md)
- [`../docs/architecture/qortal-dapp-development-standard.md`](../docs/architecture/qortal-dapp-development-standard.md)
