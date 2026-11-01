---
name: qortal-publication-discovery-scaling
description: Use when publishing Qortal QDN resources, designing identifiers, listing or searching resources, building catalogs/indexes, or removing N+1 discovery and cache problems.
---

# Qortal QDN Publication, Discovery and Scaling

- Platform: `qortal`
- Maturity: `verified-reference`
- Last checked: `2026-11-01`
- Owner: shared capability library

## Use when

Use for QDN service/identifier selection, safe publication, paginated discovery,
catalog/index design, batching, caches, request budgets and scale tests.

## Do not use when

Do not use publication work to bypass authority, validation, rendering safety or
explicit write authorization. Do not use this skill for Qortium publishing.

## Authoritative evidence

- Qortal Core `Service.java`, `ArbitraryResource.java`,
  `ArbitraryResourceStatus.java` and current bridge source.
- Current Qortal apps and `qapp-core` for verified batching/cache patterns.
- Migrated detail:
  [`qdn-publication-discovery-and-scaling.md`](../../../platforms/qortal/guides/agents/qdn-publication-discovery-and-scaling.md).

## Reusable contract / procedure

1. **Choose the service deliberately.** `APP`/`WEBSITE` are multi-file bundles;
   `JSON` is small validated JSON; `THUMBNAIL`, `IMAGE`, `VIDEO`, `AUDIO`,
   `DOCUMENT`, `LIST`/`PLAYLIST`, `MAIL*`, `MESSAGE*` and `CHAIN_COMMENT` have
   distinct limits and semantics. Prefer small purpose-built resources over one
   giant blob. Re-read current `Service.java` for exact limits.
2. **Design identifiers.** Use one documented app prefix (for example
   `myapp_`) so the app can discover its own records with `prefix: true`. Keep
   singleton and per-item identifiers stable; re-publishing the same
   `(name, service, identifier)` overwrites. Identifier matching is substring
   unless `prefix: true`, so post-filter exact `service`, `name` and
   `identifier` when correctness depends on identity.
3. **Publish safely.** Preserve host approval/signing. Never auto-retry an
   ambiguous publish. Record the exact address and verify the served content
   matches the intended revision after publication. Treat
   `PUBLISH_MULTIPLE_QDN_RESOURCES` as grouped approval over independent
   transactions with partial success. Prefer one controlled live test over
   repeated speculative attempts.
4. **Search with bridge field names.** `SEARCH_QDN_RESOURCES` uses camelCase
   fields (`includeStatus`, `includeMetadata`, `exactMatchNames`, `minLevel`,
   `nameListFilter`, `names`, ...) and translates them to lowercase node query
   names. Lowercase REST names passed to the bridge are silently ignored.
   `query` searches name/identifier/title/description, not body text.
5. **Avoid N+1.** Prefer one paginated search with metadata/status over
   per-card status, metadata, like or comment queries. Batch identity with
   `/names/list`; cache avatars and status; use `qapp-core` request queues to
   bound concurrency; lazy-load only visible per-card data.
6. **Catalogs are derived.** A `LIST`/`JSON` catalog or index is a locator, not
   authority. Version it, expose stale/partial state, validate entries against
   entities, keep search as a fallback and partition as volume grows.
7. **Define every cache.** Key, success TTL, failure TTL, invalidation, forced
   refresh, null/empty caching and stale-while-incomplete policy. Failures must
   expire and must not poison later authority resolution.

## Freshness and compatibility gate

Record the current Core revision and re-read `Service.java`,
`ArbitraryResource.java` and `q-apps.js` before reuse. Verify bridge parameter
names and response shapes, not just node REST names. If services, limits,
search semantics or the bridge contract changed, update this skill and re-run
the scale tests. A stale revision blocks correctness claims.

## Validation

- Pagination boundaries, multi-page, repeated-page and total-budget tests.
- Identifier/name/service exactness and prefix behavior.
- Deterministic reduction across permutations.
- N+1 request-count measurement for a full page render.
- Stale, failed, empty and last-known-good cache tests.
- Post-publication exact served-resource verification.
- Partial/unavailable discovery states reported honestly.

## Known failure modes

- One status/metadata/engagement query per card.
- Copying lowercase node query names into `SEARCH_QDN_RESOURCES`.
- Treating identifier substring matches as exact identity.
- Reporting a fixed unpaginated cap as complete discovery.
- Letting a derived catalog establish ownership or become the only discovery path.
- Retrying an ambiguous publish or treating `READY` as proof of the new revision.
- Caching a transient failure permanently.

## Non-goals

Not an authority/rendering model, a release process, a Qortium contract or write
authorization. It does not prove a live publication succeeded.

## Harvest / maturity update

Created 2026-11-01 from the legacy Qortal publication/discovery guide and the
development standard. Maturity is `verified-reference`: source-linked at the
recorded revision, not re-validated against a current live node in this
migration. Promote after a current source check plus measured discovery and
publication evidence.
