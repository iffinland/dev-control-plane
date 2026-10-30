---
name: qortal-qdn-derived-index-coherence
description: Use when a Qortal app keeps a derived QDN catalog/index over authoritative entity resources and must not lose entities or show false emptiness when the index is stale, partial or unreadable, or when node search metadata exists but resource bytes do not.
---

# Qortal QDN derived-index coherence and recovery

- Platform: `qortal`
- Maturity: `verified-runtime`
- Last checked: `2026-09-13`
- Owner: shared capability library

## Use when

- A Qortal app publishes separate authoritative entity resources plus a derived
  catalog/manifest/partition index used for listing and search.
- A listing can be wrong because the index is stale, incomplete or unreadable,
  or because a node exposes search metadata while the resource bytes are not yet
  available.
- You need the read-time reconciliation, bounded fallback discovery, retry and
  later-convergence/repair pattern that keeps entities authoritative.

## Do not use when

- The app has no derived index (pure per-resource discovery or a single
  authoritative document).
- You need a specific index schema, partition layout or identifier family — those
  are project-local.
- You want an unbounded full-archive rescan, or a rewrite of an index you cannot
  read completely.
- The platform is Qortium. Test the equivalent behavior there separately; do not
  assume Qortal node semantics transfer.

## Authoritative evidence

| Source | Revision | Paths / contract proved |
| --- | --- | --- |
| `Qortal/qortal` (Core 6.1.9) `master` | `108bf191d42d710ec617f535af30cfd82fc03c87` | node search index vs resource-byte availability; `MISSING_DATA`/`DOWNLOADING` status and `{"error":1401,"message":"Data unavailable. Please try again later."}`; `/arbitrary/...` 404 while search still returns a locator. |
| `Qortal/Qortal-Hub` `develop` | `12a573b27246e8a626b24794830c6bc432d1b05d` | current host/bridge authority for the search/fetch actions used by this pattern. |
| Reference implementation (Shadow Archives Gallery) | app commits `b247ccd` (index coherence) and `472f244` (bridge reads/media hydration) | `src/services/contentRepository.ts` (`mergeListings`, bounded reconciliation, `catalog-unreadable`/`catalog-reconciled` diagnostics), `src/services/catalogWriter.ts` (`planCatalogWrite` re-indexes unassigned entities), `src/services/galleryPublishService.ts` (transient index-read retry + bounded repair), `src/services/catalogRepository.ts` (search-then-fetch index read). Report: `docs/shadow-archives-webportal/handoffs/2026-09-13-gallery-owner-workflow-index-coherence-owner-handoff.md`. |

Runtime evidence (why maturity is `verified-runtime`):

- Read-only Qortal mainnet nodes `127.0.0.1:24991` / `:24992`, Core
  `qortal-6.1.9-108bf19` (2026-09-13). On `:24991` the manifest **bytes** were
  `MISSING_DATA` (`localChunkCount: 1 / totalChunkCount: 2`) and
  `GET /arbitrary/DOCUMENT/…` returned error 1401, while the app's pre-fix read
  returned `status: 'error'`, `source: 'none'`, 0 listings even though every
  entity was discoverable. On `:24992` all resources were `READY` and a readable
  but stale index listed only 1 of 3 discoverable entities. After the fix both
  nodes listed the same 3 entities (`source: 'catalog'` reconciled on `:24992`,
  `source: 'fallback'` on `:24991`).
- Owner real-host acceptance **2026-09-13**: Gallery publish → authoritative read
  → index convergence → thumbnails/item/album render → reload persistence
  `OWNER-RUNTIME PASS`.
- Evidence reports (reference these, do not copy them):
  `docs/shadow-archives-webportal/handoffs/2026-09-13-gallery-owner-workflow-index-coherence-owner-handoff.md`,
  `docs/shadow-archives-webportal/runtime/2026-09-13-gallery-host-read-contract-and-media-rendering-report.md`,
  `docs/shadow-archives-webportal/handoffs/2026-09-13-owner-runtime-checkpoint.md`
  under `/home/iffi/dev-workspace/projects/qortal-dev-workspace/`; verify the
  current checkout or preserved evidence branch before citing.

## Scope classification

- **Verified Qortal platform behavior:** node search index availability is
  independent of resource-byte availability; `MISSING_DATA`/`DOWNLOADING`
  statuses and error 1401; `SEARCH_QDN_RESOURCES` response shape.
- **Reusable application architecture (this skill):** entity authority,
  read-time reconciliation, bounded fallback discovery, unreadable-index
  preservation, later convergence/repair.
- **Project-local (not shared):** any specific partition/manifest schema,
  identifier family (`saw_*`), catalog entry fields, or UI notice copy. Keep
  Shadow Archives identifiers and Gallery-specific presentation out of other
  apps.

## Reusable contract / procedure

Model:

```text
authoritative entities
-> derived catalog/index
-> bounded discovery reconciliation
-> stale/unreadable index recovery
-> later convergence / repair
```

1. **The derived index is never the authority.** Authoritative entity resources
   define what exists. A catalog entry may win a same-identifier conflict only
   because it carries richer compiled summary data — never because it is the
   source of truth.
2. **Read-time reconciliation.** When the index is readable, run a **bounded**
   metadata-only discovery (e.g. one newest-first page per entity kind) and
   merge: keep catalog entries, add discovered-only entities by exact
   identifier, de-duplicate. A readable but stale index must not hide
   authoritative entities.
3. **Distinguish search metadata from resource bytes.** A search result proves a
   locator exists, not that the bytes are served. On a node, bytes may be
   `MISSING_DATA`/`DOWNLOADING` (`{"error":1401…}`, HTTP 404) while search
   returns the entry. Handle both states truthfully; do not present index
   absence as "no content".
4. **Unreadable/partial index recovery.** If the index cannot be read or is
   invalid, fall back to bounded discovery and report `catalog-unreadable`-style
   diagnostics. **Never rewrite an unreadable/partial index from an incomplete
   view** — rebuilding from a partial view can permanently drop entries.
5. **Bound everything.** Cap index-read retries (e.g. a small attempt count with
   an injectable delay), discovery pages, hydration items, entity fetches and
   concurrency; never fetch full media bytes during listing.
6. **Later convergence/repair.** A later successful write should repair orphaned
   index entries: find authoritative entities the readable index is missing,
   fetch only those payloads (bounded), rebuild rich entries, and upsert by
   identifier. Preserve existing entries, carry the payload's `state` (never
   re-add a withdrawn entity as active), and keep repair best-effort so it can
   never block, roll back or corrupt the authoritative content write.
7. **Truthful status and diagnostics.** Report `ready`/`partial`/`error` plus
   explicit diagnostics (`catalog-reconciled`, `catalog-unreadable`, hydration
   failures) and an honest user notice ("index was out of date and was
   reconciled" vs "index could not be read; showing live discovery"). Do not
   claim completeness.
8. **Order the write path:** media → entity → derived index, so an unusable index
   never blocks authoritative content, and the index is always the skippable
   last stage.

## Freshness and compatibility gate

Before reuse:

1. Re-check the Core revision/build and the Hub bridge action contract against
   the pins; node availability behavior is runtime state, so re-verify live.
2. Confirm `SEARCH_QDN_RESOURCES` still returns locators when bytes are
   unavailable, and that status/error text has not changed.
3. Inspect the app's own index schema and confirm the reconciliation/repair
   bounds still apply.
4. Mark the result `compatible`, `needs-delta-audit`, or `stale`.

## Validation

- Static/unit: reconciliation adds discovered-only entities and never
  duplicates; unreadable index falls back instead of erroring; transient index
  read retries; repair re-indexes an orphaned entity; a skipped index write still
  lists the published item; repair failure never blocks publishing.
- Local runtime: simulate `READY` vs `MISSING_DATA`/`404` transport responses and
  assert truthful diagnostics.
- Live: run the read path against one node whose index bytes are unavailable and
  one where they are `READY`; compare listing sets to authoritative entities.
- Owner: publish → converge → reload persistence on the real host.

## Known failure modes

- **Index read failure treated as fatal:** the app shows nothing even though
  every entity is discoverable (the observed root cause).
- **Trusting a valid manifest as complete:** a readable index silently becomes
  the source of truth for the listing set.
- **Orphaned index entry:** a skipped/ambiguous index write leaves an entity out
  of the index; without repair it is never re-added.
- **Unbounded discovery/hydration:** full-archive rescans or per-item body
  fetches make a listing expensive.
- **Rewriting a partial index:** rebuilding from an incomplete view drops
  entries.
- **Conflating search metadata with bytes:** reporting a resource as available
  when the node cannot serve it.

## Non-goals

- A specific catalog/index schema, partition layout, identifier family or UI
  copy.
- Publication transport, authority/auth, moderation or engagement.
- A guarantee that every failure injection was owner-tested.

## Harvest / maturity update

- Upgrade evidence: none outstanding — owner real-host convergence/reload is
  recorded (2026-09-13).
- Downgrade to `stale` if Core search/availability semantics change, if the
  bridge search action changes shape, or if the app index schema invalidates the
  reconciliation/repair contract.
- Do not extend to a different platform without separate evidence.
