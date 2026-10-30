---
name: qortal-cross-app-video-publishing
description: Use when a Qortal app must publish a public video to QDN so current Q-Tube-compatible consumers discover and play it, while the app keeps its own authoritative video entity and publishes the media bytes only once.
---

# Qortal cross-app video publishing (Q-Tube-compatible)

- Platform: `qortal`
- Maturity: `verified-runtime`
- Last checked: `2026-09-13`
- Owner: shared capability library

## Use when

- A Qortal app publishes public video content that must appear in the current
  Q-Tube application, without importing, vendoring or depending on Q-Tube.
- One canonical `VIDEO` byte payload must be referenced by both the app's own
  entity and a Q-Tube-compatible metadata artifact.
- You need the exact Q-Tube metadata/identifier/discovery/validity contract, or
  the truthful partial-failure semantics of a multi-resource host write.

## Do not use when

- The consumer is Qortium, the archived `qortal-ui`, or a generic web host.
  Qortal node/bridge behavior is not transferable.
- The task is engagement (comments/likes/tips), edit/delete/tombstone, playlist
  management, transcoding, or large-file pipelines beyond the verified host
  ceiling — none of those are established here.
- You need SubWire **article** or Quitter announcement interoperability; use
  those dedicated skills instead.
- You intend to treat `qtube_vid_` or Q-Tube's metadata schema as a timeless
  Qortal platform contract. It is a dated community-app convention.

## Authoritative evidence

| Source | Revision | Paths / contract proved |
| --- | --- | --- |
| `Qortal/q-tube` `main` | `68c3ea706c4ab110ffa44a7f55f8e09bdf7e85ff` | `useVideoPublishingWorkflow.tsx` (two-resource publish, `tag1`), `src/utils/checkStructure.ts` `isValidVideoMetadata`, `src/pages/Home/Components/VideoList.tsx` (display gate), `VideoContent-State.ts` (playback resolves `videoReference`), `VideoCardImageContainer.tsx` (empty-`extracts` hover blank), `Home.tsx`/`Search.tsx` (discovery query shapes). |
| `Qortal/Subwire` `master` | `a933a6c44d60db19cd219408e36c747aebcce994` | shares the `qtube_vid_` public-video family; `src/utils/articleQdn.ts` encodes media identifier = metadata identifier minus `_metadata`. |
| `Qortal/Qortal-Hub` `develop` | `12a573b27246e8a626b24794830c6bc432d1b05d` | `src/qortal/get.ts` `publishMultipleQDNResources`: `tags[i] → tag{i+1}`, per-resource `file` host-encoded, per-resource `unsuccessfulPublishes`, `fee × resources.length`, one approval dialog, `identifier == null → 'default'`. |
| `Qortal/qortal` (Core 6.1.9) `master` | `108bf191d42d710ec617f535af30cfd82fc03c87` | `SEARCH_QDN_RESOURCES` `LATEST` vs `ALL` grouping, identifier substring semantics, Core metadata caps, node search-index vs data availability. |
| `Qortal/qapp-core` `master` | `0f9d6ac5134ef2f82c1444a74e78471ddc7eb7df` | host framework helpers (reference only; Hub/Core remain the authority). |

Runtime evidence (why maturity is `verified-runtime`):

- Read-only Qortal mainnet nodes `127.0.0.1:24991` / `:24992`, Core
  `qortal-6.1.9-108bf19`, heights 2722895–2723000 (2026-09-13): the live
  discovery query returned 20 real `qtube_vid_` metadata resources, and a live
  payload matched the recorded adapter contract field for field.
- Owner real-host acceptance **2026-09-13**: publish in the app → app
  discovery/detail/playback → native Q-Tube discovery/playback
  `OWNER-RUNTIME PASS`.
- Evidence reports (reference these, do not copy them):
  `docs/shadow-archives-webportal/validation/2026-09-13-video-qtube-contract-live-read-only-validation.md`,
  `docs/shadow-archives-webportal/implementation/2026-09-13-video-owner-publishing-implementation-report.md`,
  `docs/shadow-archives-webportal/handoffs/2026-09-13-owner-runtime-checkpoint.md`
  under `/home/iffi/dev-workspace/projects/qortal-dev-workspace/`. Some
  evidence files are on the preserved Qortal evidence branch recorded in
  `/home/iffi/dev-workspace/control-plane/platforms/qortal/README.md`; verify the exact branch before citing.

## Scope classification

- **Verified Qortal platform behavior:** `SEARCH_QDN_RESOURCES` `mode`
  semantics (`LATEST` groups per `(name, service)`, `ALL` returns all), identifier
  substring matching when no `prefix` flag is set, the Qortal service set, Core
  metadata length caps, `PUBLISH_MULTIPLE_QDN_RESOURCES` tags/file/per-resource
  failure handling, and node resource availability states
  (`READY`/`DOWNLOADING`/`MISSING_DATA`).
- **Current community-app convention (dated, not platform):** the `qtube_vid_`
  identifier family, the `_metadata` suffix with media = metadata minus suffix,
  Q-Tube's `VideoMetadata` field set, Q-Tube's Core title/description mirror
  strings, and category-tab `description` filtering.
- **Project-local implementation pattern (not shared):** Shadow Archives'
  `saw_*` identifiers, catalog/partitions, owner-mode UI and poster policy. Do
  not promote those into an interoperability contract.

## Reusable contract / procedure

1. **Publish media bytes once.** Service `VIDEO`, identifier in the
   `qtube_vid_…` family, `tag1 = 'qtube_vid_'`, `filename = <original name>`.
   Send the media as a `File` in a grouped publish; do not materialise a second
   base64 copy of large media client-side.
2. **Publish one derived `DOCUMENT` metadata artifact** at
   `<media identifier>_metadata`, `filename = 'video_metadata.json'`,
   `tag1 = 'qtube_vid_'`. Body (`VideoMetadata`): `title`, `version: 1`,
   `fullDescription`, `htmlDescription`, `videoImage` (data URL),
   `videoReference { name, identifier, service }`, `extracts[]`, `commentsId`,
   `category`, `subcategory`, `code`, `videoType`, `filename`, `fileSize`,
   `duration`. Mirror Core metadata so category tabs keep working:
   `title` = first 50 chars and
   `description = '**category:<id>;subcategory:<sub>;code:<code>**' + first 150
   chars`, with `tags: ['qtube_vid_']`.
3. **`videoReference` is the real cross-app link.** Its `identifier` must equal
   the metadata identifier minus `_metadata`, `name` must be the publishing
   name, and `service` must be `VIDEO`. Bytes published at any other coordinate
   force a duplicate copy or a consumer change.
   Note: Q-Tube's own media identifiers have the shape `qtube_vid_<slug>_<short
   id>`; that inner shape is Q-Tube's own convention and is **not** required by
   the consumer, which follows `videoReference`. The shared cross-app rule is
   only the `qtube_vid_…` family plus the `_metadata` suffix.
4. **Discovery request:** `SEARCH_QDN_RESOURCES { service: 'DOCUMENT',
   identifier: 'qtube_vid_', mode: 'ALL', reverse: true, limit: 20 }`.
   `mode: 'ALL'` is required. Category tabs add `description: 'category:<id>;'`.
5. **Validity/display gate:** the consumer requires `title`, a `videoReference`
   with non-empty `name`/`identifier`/`service` from the Qortal service set, and
   a non-empty `filename`; `duration`/`fileSize` are optional. Payloads failing
   the gate are dropped, so the consumer's gate — not your own validation — is
   the real display condition. Run the same gate before writing.
6. **Grouped publish handling:** assume one approval dialog, `fee × count`,
   `tags[i] → tag{i+1}`, host-side `file` encoding, and per-resource
   `unsuccessfulPublishes` (genuine partial success, never a rollback).
7. **Partial-publish semantics:** exactly one publish call per stage; a timeout
   is `ambiguous` and is **never** auto-retried; report
   `published | index-incomplete | partial | ambiguous | failed` truthfully;
   always return the exact identifiers; fail closed (validate, encode,
   self-check) before the first write; a retry must reuse the same identity so it
   overwrites instead of minting a duplicate video.
8. **Empty-`extracts` trap:** the hover card iterates `extracts` with
   `index % extracts.length`, so an empty array blanks the card image. Seed
   `extracts` with at least the poster frame; a single-element array is safe.

Safe implementation pattern: keep every Q-Tube fact in a single adapter module;
import/vendor no Q-Tube code; keep the app's own entity authoritative and the
Q-Tube artifact derived and rebuildable; the app's own discovery must read only
its own identifier namespace.

## Freshness and compatibility gate

Before reuse:

1. Re-check `q-tube` `main` and `Qortal-Hub` `develop`/default branch heads and
   the running Core build; compare with the pins above.
2. Inspect changes to `isValidVideoMetadata`, the `VideoMetadata` shape, the
   discovery search calls, and `publishMultipleQDNResources`.
3. Run the smallest contract check: fetch one live `qtube_vid_` metadata
   resource, run the gate and the discovery query, and compare fields.
4. Mark the result `compatible`, `needs-delta-audit`, or `stale`.

Do not repeat a full audit when these boundaries are unchanged.

## Validation

- Static/unit: gate parity tests, identifier round-trips, category mapping,
  live-shape regression fixtures.
- Local runtime: staged publish sequence, truthful partial/ambiguous outcomes,
  exactly one write per stage, verify path.
- Host/bridge: a real owner-authorized publication where a `File` survives the
  host bridge and the grouped approval accepts the media group.
- Cross-app: the publication appears/opens in native Q-Tube (Home, Search and a
  category tab), and a live node returns the new metadata resource.

## Known failure modes

- **Bytes at the wrong coordinate:** the consumer resolves `videoReference`
  exactly, so the media identifier must be metadata-minus-`_metadata`.
- **`mode: 'LATEST'` discovery:** silently shows only one video per publisher.
- **Substring vs prefix confusion:** without a `prefix` flag the identifier is a
  substring match, so an unrelated identifier containing `qtube_vid_` can match.
- **Empty `extracts`:** hover card image goes blank.
- **Search-index lag:** a freshly published metadata resource may not be returned
  immediately; report "not returned yet", do not report failure.
- **Host size ceiling:** 2 GB for a local node vs 500 MB when the Hub runs as a
  public gateway; larger media is refused at approval time.
- **Browser codec/container variance:** a container the client cannot decode
  plays in neither the app nor Q-Tube; report it before publishing.
- **Auto-retry of an ambiguous write:** risks duplicate coordinates and double
  fees.

## Non-goals

- Q-Tube engagement, edit/delete/tombstone, playlists, or a general Qortal
  video API.
- SubWire article or Quitter behavior (separate skills).
- Deep links, APP publication, or release procedures.

## Harvest / maturity update

- Upgrade evidence: none outstanding — owner real-host cross-app playback is
  already recorded (2026-09-13).
- Downgrade to `stale` when the Q-Tube gate/discovery/metadata shape changes,
  when Core search `mode`/identifier semantics change, or when the Hub grouped
  publish contract changes.
- Do not extend this skill to engagement/edit semantics without new runtime
  evidence.
