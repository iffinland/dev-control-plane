---
name: qortal-qdn-content-crud
description: Use when a Qortal dApp publishes, updates, reorders or tombstones its own QDN entities under a registered name through the host bridge - covers the revision-in-payload contract, read-back verification, media-before-entity ordering, the single-file media URL rule and prefix discovery.
---

# Qortal QDN content CRUD under the app's own registered name

- Platform: `qortal`
- Maturity: `verified-runtime`
- Last checked: `2026-10-01`
- Owner: shared capability library

## Use when

- A Qortal app owns an editable QDN data set (site content, listing entries,
  catalogue rows) published under **one registered name**, one resource per
  entity, and needs Create / Read / Update / Delete plus ordering.
- You need the verified publish path: `PUBLISH_QDN_RESOURCE` through the host
  bridge, one signed transaction per entity, approval dialog per write.
- You need the verified **read-back verification** rule: a write is only
  "verified" after the app re-reads the resource and confirms the new revision.
- You need the verified **media ordering** rule and the media URL contract.
- You need the verified **discovery** rule for finding all of an app's entities
  under its own name.

## Do not use when

- The platform is Qortium. QDN equivalent APIs differ; do not transfer this
  skill on API-name similarity.
- You need a QDN *delete*. Qortal exposes no app-accessible delete; the only
  available operation is a **tombstone republish** (see the contract below).
- You are publishing an immutable artifact (a built `WEBSITE`/`APP` bundle).
  That is a single multi-file publication, not per-entity CRUD; the multi-file
  read path rule below still applies.
- You need the bridge response-shape normalization rule; that is the separate
  `bridge-fetch-qdn-resource-normalization` skill.

## Authoritative evidence

| Source | Revision | Paths / contract proved |
| --- | --- | --- |
| Qortal Web Builders (donor app, real host) | `agent/qwb/phase-3` @ `911b44f3e57c39c46048c950274c89bdd04596f5`; runtime-fix branch `agent/qwb/phase-4-runtime-fix` @ `741754becb79a131c699f2468fe096fdacd00c19` (the revision all runtime evidence above was produced at, pushed); read path extended at `7fd03fc5b2d39d80b20ccaa9c7a07355d85dc94a` (local, Phase 4 checkpoint - see the workspace report named under *Harvest / maturity update*) | `src/content/media.ts` (`qdnMediaUrl`), `src/qortal/bridge.ts`, `src/owner/flows.ts`, `src/owner/writes.ts` - publish/verify/tombstone/reorder and media URL construction; `src/content/qdn-source.ts` - discovery and the per-entity shipped-default baseline (contract 8). |
| Qortal Core 6.1.9 (node authority) | `qortal-6.1.9-108bf19`, mainnet, `127.0.0.1:24991` (node A) and `127.0.0.1:24992` (node B), `syncPercent` 100 | `/arbitrary/…` serve + metadata + `resource/status` + `resources/search` behaviour recorded below. |
| Qortal Hub 3.0.3 (host authority) | Linux/Electron build, 2026-09-16 | `PUBLISH_QDN_RESOURCE` approval dialog, flat `0.01 QORT` fee for these writes, decline semantics. |
| Shadow Archives (owner runtime) | `agent/shadow-archives/blog-publish-partial-outcome-20261001` @ `adfb91f841f10c796b462e045fc6520f6682b126`, mainnet node `127.0.0.1:24992`, 2026-10-01 | Hub can resolve `PUBLISH_MULTIPLE_QDN_RESOURCES` with `error.unsuccessfulPublishes`; the app must normalize that as partial/failed before claiming success. Owner then published a new canonical Blog `DOCUMENT`, confirmed by read-only node discovery. |

Real-host runtime evidence (why maturity is `verified-runtime`), 2026-09-16,
staging target `WEBSITE / Q-Website / default`, owner `QNwV9VV82UUZmMkDZZbEMAKPpCx7otnnsi`,
all writes synthetic and published under the app's own name:

- **Create** - new entity `JSON / Q-Website / qwb_svc_build-service-…`, toast
  `"<title>" was published and verified as revision 1`, node payload
  `rev 1, state "active"`; visible after a hard reload.
- **Update** - same identifier advanced `rev 1 → rev 2 (→ 3 … → 7)`; each save
  produced exactly one signature and the edited value survived a hard reload.
- **Reorder** - one publish per move, exactly one revision increment, new
  `order` value read back from the node and the on-screen order matched after
  reload.
- **Tombstone delete** - `rev 3` written with `state:"deleted"`, `payload:null`;
  the row disappeared from the app after reload and the control no longer
  existed. No node-admin delete was used.
- **Read-back verification** - `Publishing status` listed
  `build service: <title> — Submitted to the host (availability: verified):
  Published and verified (signature 3D6TqkhSPrgQ…): the node serves revision 7.`
  and `Pending writes: 0.`
- **Media ordering** - the `THUMBNAIL` approval dialog appeared **before** the
  entity dialog; the thumbnail was published and READY first, then the entity
  referenced it.

## Scope classification

- **Verified Qortal platform behaviour** (Core 6.1.9 + Hub 3.0.3, this revision
  only): per-entity publish is one signed transaction; the fee observed for
  these small JSON and single-image writes was `0.01000000 QORT`.
- **Reusable app-side contract:** revision-in-payload compare-and-swap-free
  updates, truthful availability vocabulary, media-before-entity ordering.
- **Dated revision pin:** revalidate against current Core/Hub before reuse.

## Reusable contract / procedure

**1. Entity envelope.** Store the revision inside the payload, because Qortal
offers no compare-and-swap:

```json
{"schema":1,"id":"<identifier>","kind":"<entity-kind>","rev":7,"state":"active",
 "createdAt":0,"updatedAt":0,"deletedAt":null,"order":50,"title":"…","payload":{}}
```

`state` is `"active"` or `"deleted"`; a tombstone is
`{"rev":n+1,"state":"deleted","payload":null}` republished to the **same
identifier** — the row disappears from the app while the older bytes stay
retrievable on the network.

**2. Identifier scheme.** Prefix every app entity with a stable namespace
(`qwb_svc_<kind>-<slug>-<suffix>`, `qwb_step_<kind>-…`) so discovery is a bounded
prefix query and cross-app collisions are impossible.

**3. Publish.** One `PUBLISH_QDN_RESOURCE` per entity revision; the host surfaces
one approval dialog per request, and the app must not treat the dialog as the
result.

**3a. Grouped publish outcome.** `PUBLISH_MULTIPLE_QDN_RESOURCES` is a grouped
approval over independent writes. The Hub may reject its promise with an
`error.unsuccessfulPublishes` list **or resolve** with an object containing that
same list. Normalize either shape into `partial` or `failed` before generic
success handling. Preserve the identities of resources that did land, do not
claim the batch succeeded, and never automatically retry an ambiguous or
partial result.

**4. Verify before claiming.** After approval, re-read the resource through the
bridge and only report published when the read-back revision matches the
revision that was submitted. Vocabulary that worked:

- in flight -> `Submitted to the host`
- confirmed -> `Published and verified (signature <sig>): the node serves revision <n>`
- declined/refused -> `Rejected by the host — nothing was published`
- no confirmation -> availability `unverified`, never `verified`

**5. Media before entity.** When an entity references an image, publish the
single-file media resource **first**, verify it, and only then publish the entity
that points at it. If the media step fails, do not publish the entity and keep
the draft open. Image resources carry a **bare base64 payload**, not JSON.

**6. Single-file media URL rule (the load-bearing detail).** A single-file QDN
resource is served at the **bare identifier path only**:

- correct: `GET /arbitrary/THUMBNAIL/<name>/<identifier>` -> `200`, the bytes
  (`Content-Length: 3016`, WebP `RIFF….WEBP`)
- wrong: `/arbitrary/THUMBNAIL/<name>/<identifier>/<stored filename>` -> `404`.
  Core does **not** serve the stored filename for a single-file resource.
- wrong: `?filepath=<stored filename>` -> this is the **multi-file** lookup and
  returns `{"error":1401,"message":"No file exists at filepath: <filename>"}`.

Keep the stored filename in the app's own record (it is part of the publish
request), but never append it to the read URL. For a multi-file resource such as
a built `WEBSITE`, the reverse holds: the bare resource path `404`s and the bytes
must be fetched with `?filepath=index.html`.

**7. Discovery.** `GET /arbitrary/resources/search?service=<service>&mode=ALL&name=<name>&identifier=<prefix>`
returns every prefix match; without `mode=ALL` the default `LATEST` mode returned
only the newest row. Do **not** rely on `names=<…>&exactMatchNames=true`; on the
observed node it did not filter and returned foreign rows, so re-filter
client-side on the exact `(name, service, identifier)`.

**8. Shipped defaults and the pre-publication bootstrap (read path).** When the
app ships default content that its owner is expected to replace **in place, one
entity at a time**, discovery must not replace a whole kind with its QDN result.
Merge the shipped default per **identifier**, and only for a kind whose discovery
answered without hitting the page budget:

- add a shipped item only when discovery did **not** report its identifier at
  all; a reported identifier (active, tombstoned, invalid or unreadable) is never
  replaced by its shipped default, so "exists but failed to load" stays a
  reported failure and a tombstone cannot resurrect;
- a discovery that failed or hit the page budget contributes no default, because
  a partial scan proves nothing about what exists (and partial discovery must not
  grant authority);
- the baseline then ends by itself once every shipped identifier has been
  published or tombstoned - it is not a mode, a flag or a migration;
- report it: the app should say how many shipped items still render this way.

Without this rule the first owner write hides every shipped item the owner has
not touched yet, and with it the only in-page control that could ever publish
that item - so a seeded site cannot be bootstrapped by progressive editing at
all. Validated 2026-09-16 in Qortal Web Builders by an integration test over the
real bridge, read and publish modules (zero content -> first write -> reload ->
second write, plus tombstone non-resurrection); that layer is test-validated, not
a separate real-host run. The write, owner-mode and inline-editing contracts
above remain the real-host-verified ones.

## Freshness and compatibility gate

- This contract is pinned to Core `qortal-6.1.9-108bf19` and Qortal Hub 3.0.3.
- Invalidation triggers: a Core change to `/arbitrary/` routing or
  `resources/search` modes; a Hub change to the approval dialog or fee
  calculation; any change to bridge action names.
- Smallest future compatibility check (bounded, no owner needed): build the
  donor app, publish one synthetic JSON resource, then compare
  `GET /arbitrary/<service>/<name>/<identifier>` (expect `200` + payload) with
  `…/<identifier>/<filename>` (expect `404`) and confirm `mode=ALL` still returns
  all prefix matches.

## Validation

- Structural: `python3 tools/validate_skills.py` in this repository.
- Runtime (required for `verified-runtime`, already executed 2026-09-16): real
  host + real node; create, update, reorder and tombstone each verified by a node
  read-back **and** a hard reload; media published before the entity and rendered
  from `/arbitrary/…`; no write claimed before its read-back matched.
- Negative: a declined approval must produce a truthful rejection, an unchanged
  node revision and no automatic retry.
- Negative: a resolved grouped response with `error.unsuccessfulPublishes` must
  produce `partial`/`failed`, not `submitted`.

## Known failure modes

- Claiming success from the host approval dialog instead of from the read-back —
  the classic false "saved" state.
- Appending the stored filename to a single-file media URL (404) or using
  `?filepath=` for a single-file resource (error 1401).
- Publishing the entity before its media, leaving an entity that points at a
  resource the node does not serve yet.
- Assuming `identifier=<prefix>` returns all rows without `mode=ALL`.
- Treating a tombstone as a real delete and expecting the bytes to vanish.
- Auto-retrying an ambiguous write; the correct behaviour is to stop and let the
  user re-issue it explicitly.
- Treating a resolved Hub `error.unsuccessfulPublishes` object as an ordinary
  submission, which can report a missing canonical entity or derived companion
  resource as published.
- Replacing a kind's whole rendered list with its discovery result while the owner
  is still replacing shipped content: the first write hides every untouched
  shipped item - including its edit control - and the seeded site can no longer
  be bootstrapped. Merge shipped defaults per identifier instead (contract 8).
- Letting a failed or page-budget-truncated discovery fall back to shipped
  defaults: a partial scan cannot distinguish "never published" from "tombstoned
  but unread", so it must contribute nothing.

## Non-goals

- Not a Qortium contract.
- Not the bridge `FETCH_QDN_RESOURCE` normalization rule (separate skill).
- Not the owner-recognition/owner-mode contract (separate skill).
- Not a node-admin or delete API.

## Harvest / maturity update

- Maturity `verified-runtime` on 2026-09-16 from the Qortal Web Builders Phase 4
  owner-runtime run. Report: `docs/qwb-qortal-web-builders/implementations/2026-09-16-qwb-phase-4-owner-runtime-validation.md`
  with evidence in `docs/qwb-qortal-web-builders/implementations/2026-09-16-qwb-phase-4-runtime-evidence/`
  (preserved Qortal platform source `projects/qortal-dev-workspace`; evidence on
  branch `origin/agent/qwb-qortal-web-builders/phase-4-checkpoint-docs-20260916`).
- Contract 8 (shipped-default baseline) added at the Phase 4 checkpoint,
  2026-09-16, from a production-bootstrap finding on the same app. Harvest level:
  app-side read-path contract, validated by unit/integration tests over the real
  bridge, read and publish modules - no new real-host run. Report:
  `docs/qwb-qortal-web-builders/implementations/2026-09-16-qwb-phase-4-checkpoint.md`
  with the application commit series in
  `…/2026-09-16-qwb-phase-4-checkpoint-evidence/`.
- Grouped-result normalization added on 2026-10-01 from Shadow Archives Blog
  owner-runtime evidence. The application fix is
  `src/qortal/publish.ts`; its focused tests cover resolved partial and
  all-failed responses. The owner published canonical resource
  `saw_post_lr6vjv48uo4u`, confirmed by node `127.0.0.1:24992`; this proves the
  target Blog post path, not the optional SubWire consumer path.
- Downgrade to `stale` if Core `/arbitrary/` routing, `resources/search` modes or
  the Hub approval flow change; the bounded compatibility check above is the
  promotion gate back to `verified-runtime`.
