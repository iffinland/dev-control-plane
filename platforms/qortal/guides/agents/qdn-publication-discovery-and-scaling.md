# QDN Publication, Discovery and Scaling

## Purpose

Define how to publish to QDN safely, how to discover content without N+1
request storms, and how to build catalogs, caches and indexes that scale.

## Use when

Use for publishing, resource schema/identifier design, listing/search,
pagination, catalog/index resources, caching, and any work that touches
discovery volume.

## Do not use when

Do not use publication work to bypass authority or validation rules (see
[`qortal-architecture-and-data-integrity.md`](qortal-architecture-and-data-integrity.md)).

## Prerequisites

- Current Qortal Core revision and node.
- Known `(service, name, identifier)` scheme for each entity.
- Expected content volumes and pagination requirements.

## Required inputs

- Resource purpose and size class.
- Discovery queries the app will need.
- Identity and encryption requirements.
- Freshness and staleness tolerance.

## 1. Choose the right service and size

**VERIFIED.** Services have distinct semantics and limits (Core `Service.java`,
mirrored in the official docs): `JSON` (25 KB, validated), `THUMBNAIL`
(500 KB), `IMAGE` (10 MB), `VIDEO`, `DOCUMENT`, `LIST`/`PLAYLIST`, `APP`
(50 MB, multi-file), `WEBSITE`, `MAIL`/`MAIL_PRIVATE` (1 MB / 5 MB),
`MESSAGE`/`MESSAGE_PRIVATE` (1 MB), `BLOG*`, `COMMENT`, `CHAIN_COMMENT`
(≤239 bytes).

Rules:

- Prefer small, purpose-built single resources over one giant blob.
- `CHAIN_COMMENT` is fully on-chain and fast only for ≤239 bytes.
- **VERIFIED (inspected Hub revision).** Current Hub `src/qortal/get.ts`
  accepts `isMultiFileZip` for both single and multi-resource publication and
  selects `uploadType: 'zip'`, so multi-file ZIP publication from an app is
  source-supported for that revision. Host approval still applies, the
  ZIP/root layout must be correct, and source support is not proof of a
  successful live publication; validate runtime compatibility before
  release-critical use. Host (Hub) publishing remains a legitimate workflow
  choice. Read multi-file resources with a `filepath`.
- In-browser base64 of large files is memory-expensive. Verify the host
  transport path and measure before publishing large media from the app.

## 2. Design identifiers

**VERIFIED** (official docs): prefix identifiers with the app name
(e.g. `myapp_...`) so the app can find its own resources with
`SEARCH_QDN_RESOURCES` + `identifier` + `prefix: true`.

Rules:

- Use one documented prefix per app, recorded in `projects/<project>.md`.
- Derive deterministic identifiers for singleton records and unique identifiers
  for per-item records.
- Keep the identifier stable for the lifetime of the entity. Re-publishing the
  same `(name, service, identifier)` overwrites.
- **VERIFIED.** A shared identifier can be intentional and useful: an avatar is
  `THUMBNAIL` + `qortal_avatar` under the user's name.

## 3. Publish safely

- Preserve host approval/signing.
- Never retry an ambiguous publish automatically.
- Record the exact `(service, name, identifier)` and verify the resource
  afterwards.
- Submission, transaction confirmation, resource status and intended-revision
  verification are separate. A `READY`/available resource does not prove that a
  newly submitted update is the version currently served; compare the served
  content against the intended operation/content with a
  revision/version/content-hash/exact-relevant-payload check.
- Treat `PUBLISH_MULTIPLE_QDN_RESOURCES` as grouped UI approval over independent
  transactions; handle partial success.
- Prefer one owner-authorized controlled live publication test over repeated
  speculative attempts that can leave orphan resources.

## 4. Discover with bounded, paginated search

**VERIFIED — node endpoint query parameters.** `GET /arbitrary/resources/search`
uses lowercase query names: `service`, `query`, `identifier`, `name`
(repeatable list), `title`, `description`, `keywords`, `prefix`,
`exactmatchnames`, `default`, `mode`, `minlevel`, `namefilter`, `followedonly`,
`excludeblocked`, `includestatus`, `includemetadata`, `before`, `after`,
`limit`, `offset`, `reverse`.

**VERIFIED — `SEARCH_QDN_RESOURCES` bridge fields are camelCase and
different.** `q-apps.js` reads `service`, `query`, `identifier`, `name`
(singular string) or `names` (array, emitted as repeated `name=`), `title`,
`description`, `keywords`, `prefix`, `exactMatchNames`, `default`, `mode`,
`minLevel`, `includeStatus`, `includeMetadata`, `nameListFilter`,
`followedOnly`, `excludeBlocked`, `before`, `after`, `limit`, `offset`,
`reverse`, and translates them to the node query names above. Lowercase REST
query names passed to the bridge action are silently ignored; do not copy node
query names into bridge payloads.

Rules:

- Prefer one paginated `SEARCH_QDN_RESOURCES` with `includeStatus` and
  `includeMetadata` over per-item fetches.
- Identifier matching is substring matching anywhere in the identifier unless
  `prefix: true` is set. When correctness depends on an exact resource
  identity, post-filter the returned `service`, `name` and `identifier`, and
  distinguish a null/default identifier from an explicit one.
- Set an explicit page size and a total resource/page budget.
- Detect repeated pages and deduplicate.
- Sort deterministically.
- Handle partial/unavailable results honestly.
- A fixed unpaginated cap MUST NOT be reported as complete discovery.

**VERIFIED limitation.** `query` searches name, identifier, title and
description metadata only. It does **not** search body/full content. Body-text
search requires an app-maintained index or catalog.

## 5. Avoid N+1 discovery

Anti-pattern to document and reject:

```text
20 cards
x separate like query
x separate comment query
x separate metadata/status query
```

Required mitigations:

- Batch identity resolution (see §7).
- Fetch metadata/status in the listing query rather than per card.
- Aggregate engagement in one query per content type per page, or maintain a
  catalog with pre-aggregated counts.
- Lazy-load per-card engagement only when it becomes visible, and only for the
  fields that need it.
- Bound concurrency with a queue. **VERIFIED.** `qapp-core` provides
  `RequestQueueWithPromise` and dedicated search/fetch queues; current apps cap
  concurrency in this way.

## 6. Catalog / index resources

For scalable listing, maintain a derived catalog resource (for example `LIST` or
`JSON` under an app-prefixed identifier) that records the app's own item
references — not authority.

Rules:

- The catalog is derived, rebuildable and non-authoritative.
- It MUST carry a schema version.
- It MUST expose whether it is stale/partial.
- It MUST be validated against the entity resources; a catalog entry is a
  locator, not proof.
- It MUST NOT be the sole way to discover user content (avoid a single point of
  failure); search remains a fallback.
- Partition or shard it as volume grows.
- **VERIFIED.** `qapp-core` ships list/index tooling (`useResources`,
  `useListReturn`, `ListLoader`, `IndexManager`) and current apps use list
  resources (e.g. Subwire's `LIST_ARTICLES_FEED`).

## 7. Batch expensive lookups

- **VERIFIED.** Use `POST /names/list` to resolve primary names for many
  addresses at once, and `/names/address/{address}` for one account, instead of
  one call per author.
- Cache avatar URLs (`/arbitrary/THUMBNAIL/{name}/qortal_avatar`) rather than
  refetching.
- Cache resource status; a status poll is not free.

## 8. Cache policy

Every cache MUST define:

- key;
- success TTL;
- failure TTL (failures must expire; they must not become permanent truth);
- invalidation;
- force-refresh;
- whether null/empty results are cached;
- whether stale success may be used while discovery is incomplete.

**VERIFIED** current-app precedent: Subwire caches primary names for 24h and
profiles for 5 minutes in IndexedDB.

A forced high-level refresh MUST bypass dependent stale caches when authority,
identity or publication state depends on them.

## 9. Plan scale tests

Test: more than one page, many publishers, duplicate pages, large partitions,
unavailable resources, partial partitions, cache invalidation, concurrency
limits, and a cold first visit versus a warm repeat visit.

## Mandatory rules

- Whole-catalog snapshots SHOULD NOT be rewritten for independent operations.
- Indexes MUST NOT override entities.
- Search completeness MUST be explicit.
- Transient failures MUST NOT poison authority resolution after recovery.
- Public idempotent reads, permissioned authentication requests and signed
  writes require different retry policies; only genuinely idempotent public
  reads may be retried automatically.
- Exact current parameter names MUST be verified, not copied from memory.

## Validation

- Pagination boundary, multi-page, loop, retry, budget and partial tests.
- Identifier/name/service consistency tests.
- Deterministic reduction across permutations.
- Stale-cache, failed-cache and last-known-good tests.
- Post-publication exact-resource verification.
- Measured request counts for a full page render.

## Completion criteria

- Resource and authority identities are explicit.
- Discovery is bounded, paginated, deterministic and honest about partiality.
- N+1 patterns are absent or explicitly justified.
- Derived state cannot establish authority.

## Related files

- [`qortal-qdn-and-bridge.md`](qortal-qdn-and-bridge.md)
- [`qortal-architecture-and-data-integrity.md`](qortal-architecture-and-data-integrity.md)
- [`runtime-diagnostics-and-performance.md`](runtime-diagnostics-and-performance.md)
- [`../docs/architecture/qortal-dapp-development-standard.md`](../docs/architecture/qortal-dapp-development-standard.md)
