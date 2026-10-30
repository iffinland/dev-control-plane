---
name: qortal-subwire-article-publishing
description: Use when a Qortal app must publish an article as a SubWire-compatible QDN DOCUMENT so the current SubWire application discovers and renders it, including the qapp-core identifier math, payload shape, bare-base64 WebP cover, prefix discovery and the unsanitized-renderer constraint.
---

# Qortal SubWire-compatible article publishing

- Platform: `qortal`
- Maturity: `verified-runtime`
- Last checked: `2026-09-13`
- Owner: shared capability library

## Use when

- A Qortal app publishes long-form editorial content that must be discoverable
  and renderable in the current SubWire application, without importing or
  depending on SubWire.
- You need the exact SubWire article identifier prefix, `DOCUMENT` payload
  schema, cover encoding, prefix-discovery request or deep-link form.
- You need to know which artifact is safe to hand to an unsanitized downstream
  Markdown renderer.

## Do not use when

- The consumer is Qortium or a different Qortal app with its own article schema.
- You need video/Q-Tube interoperability or the Quitter announcement — use those
  dedicated skills.
- You want to standardize a rich-text editor. The contract is the artifact
  (GFM Markdown in a JSON envelope), **not** TipTap or any other editor.
- You intend to treat SubWire's payload/renderer as a timeless Qortal platform
  contract. It is a dated community-app convention with no compatibility gate on
  the SubWire side.

## Authoritative evidence

| Source | Revision | Paths / contract proved |
| --- | --- | --- |
| `Qortal/Subwire` `master` | `a933a6c44d60db19cd219408e36c747aebcce994` | `src/constants/qdn.ts` (identifier family), `src/utils/articleQdn.ts` (article identifier + media = metadata minus `_metadata`), `pages/DiscoverPage.tsx` (`prefix: true`, `mode: 'ALL'`, `reverse: true`, `limit: 20`), `ArticleCard`/`ArticlePage` (`marked.parse(content, { breaks: true, gfm: true })` + `dangerouslySetInnerHTML` with **no sanitizer**), `truncateByBytes` Core metadata mirror. |
| `Qortal/qapp-core` `master` | `0f9d6ac5134ef2f82c1444a74e78471ddc7eb7df` | `hashWord(word, strength, publicSalt) = safeBase64(sha256(publicSalt + word)).slice(0, strength)`, `safeBase64` mapping (`+`→`.`, `/`→`~`, `_`→`!`, strip `=`), `buildIdentifier = ${appHash}-${entityPrefix}-${parentRef}-${uid}-v1`; discovery adds `mode: 'ALL'`, `excludeBlocked: true`, drops hits with `size === 32` or `>= 5 MiB`. |
| `Qortal/qortal` (Core 6.1.9) `master` | `108bf191d42d710ec617f535af30cfd82fc03c87` | `q-apps.js` `interceptClickEvent`/`extractComponents` deep-link resolution; Core metadata caps `MAX_TITLE_LENGTH=80`, `MAX_DESCRIPTION_LENGTH=240`, `MAX_TAG_LENGTH=20`, `MAX_TAGS_COUNT=5`. |
| `Qortal/Qortal-Hub` `develop` | `12a573b27246e8a626b24794830c6bc432d1b05d` | current host bridge authority for the injected shim and publish transport. |

Runtime evidence (why maturity is `verified-runtime`):

- Read-only Qortal mainnet nodes `127.0.0.1:24991` / `:24992`, Core
  `qortal-6.1.9-108bf19`, height 2723000 (2026-09-13). The derived prefix
  `7l1NGsWiY0SgPb-FJVWQM-T60ZadsfPsbLTh-` returned 20 real SubWire `DOCUMENT`
  hits, and a real article served at `:24992` passed the mirrored gate with a
  bare-base64 (non-`data:`) WebP cover of 229 236 chars.
- Owner real-host acceptance **2026-09-13**: publish in the app → app
  discovery/detail/render → native SubWire discovery/render `OWNER-RUNTIME PASS`.
- Evidence reports (reference these, do not copy them):
  `docs/shadow-archives-webportal/validation/2026-09-13-blog-subwire-quitter-contract-live-read-only-validation.md`,
  `docs/shadow-archives-webportal/implementation/2026-09-13-blog-subwire-quitter-owner-publishing-implementation-report.md`,
  `docs/shadow-archives-webportal/handoffs/2026-09-13-owner-runtime-checkpoint.md`
  under `/home/iffi/dev-workspace/projects/qortal-dev-workspace/`. Some
  evidence files are on the preserved Qortal evidence branch recorded in
  `/home/iffi/dev-workspace/control-plane/platforms/qortal/README.md`; verify the exact branch before citing.
  Live evidence JSON:
  `docs/shadow-archives-webportal/live-evidence/2026-09-13-blog-subwire-quitter-live-read-only.json`.

## Scope classification

- **Verified Qortal platform behavior:** Core metadata length caps, deep-link
  `qortal://APP/<app>/…` resolution via `LINK_TO_QDN_RESOURCE`, `DOCUMENT`
  service, `SEARCH_QDN_RESOURCES` `prefix`/`mode`/`excludeBlocked` semantics, and
  QDN resource availability states.
- **Current community-app convention (dated, not platform):** the qapp-core
  identifier math and salts, the SubWire article prefix, the article JSON payload
  fields, bare-base64 WebP cover, the deep-link route string, and the
  unsanitized `marked` renderer.
- **Project-local implementation pattern (not shared):** the publishing app's own
  entity schema, catalog/partitions, editor choice (TipTap), owner UI and
  `saw_*` identifiers.

## Reusable contract / procedure

1. **Derive the identifier with the mirrored qapp-core math — never from
   memory.** For SubWire: `appName = 'subwire'`,
   `publicSalt = '0drEPfUciLNhQZF9NFBg6RLnwcff/g3Ic7mm3VrIJKw='`,
   `entityType = 'SUBWIRE_ARTICLE'` under `parentId = 'SUBWIRE_ROOT'`. The
   resulting article prefix is `7l1NGsWiY0SgPb-FJVWQM-T60ZadsfPsbLTh-`; the full
   identifier appends `<uid>-v1`.
2. **Choose the `uid` deliberately.** Consumers only use prefix discovery plus
   exact-identifier fetch, so the `uid` is opaque. Replacing qapp-core's random
   15-char uid with the publishing app's stable id makes a retry overwrite the
   same coordinate instead of minting a duplicate article.
3. **Write service `DOCUMENT`**, `name = <publisher>`,
   `data64 = base64(JSON article)`. Enforce the Core metadata mirror with
   SubWire's byte truncation: `title` ≤ 75 bytes, `description` ≤ 180 bytes;
   keep within Core's hard caps above.
4. **Payload schema:** `{ title, subtitle?, content (GFM Markdown),
   coverImage { name, src }, images?, media?, timestamp, name,
   type: 'essay'|'episode', published: true }`.
5. **Cover:** `coverImage.src` is **bare base64 of WebP bytes** (no `data:`
   prefix). SubWire renders it as literally `data:image/webp;base64,<src>`, so a
   non-WebP cover appears broken. Fail closed if the cover cannot be encoded as
   WebP.
6. **Discovery:** `SEARCH_QDN_RESOURCES { service: 'DOCUMENT', identifier:
   <prefix>, prefix: true, mode: 'ALL', reverse: true, limit: 20 }` (qapp-core
   adds `mode: 'ALL'` and `excludeBlocked: true`, and drops hits with
   `size === 32` or `>= 5 MiB`).
7. **No separate index/list resource is required** for discovery; the prefix
   search is sufficient. A derived app index is a convenience, never the
   authority.
8. **Deep link:** `qortal://APP/Subwire/article/<percentEncodedName>/<identifier>`
   resolves to SubWire's `article/:name/:identifier` route.
9. **Render safely for an unsanitized consumer.** Because SubWire has no
   sanitizer, derive a safe artifact: Markdown-escape literal text, allowlist
   link/image URL schemes (`http`/`https`/`qortal`/`mailto`), keep inline code
   spans literal, emit only a fixed set of raw HTML, cap the artifact below
   qapp-core's 5 MiB drop, and run the consumer's own renderable gate before
   publishing. Keep the canonical rich-text document (and its sanitized
   rendering) in the publishing app; the SubWire artifact is derived and
   rebuildable.
10. **TipTap is not part of this contract.** Any editor that produces the
    canonical document and a correct GFM Markdown artifact satisfies it.

## Freshness and compatibility gate

Before reuse:

1. Re-check `Qortal/Subwire` `master` and `Qortal/qapp-core` `master` heads and
   the running Core build against the pins above.
2. Recompute the article prefix from current source and confirm it still returns
   real SubWire resources on a live node.
3. Inspect `DiscoverPage`/qapp-core discovery params, the payload field names,
   the cover encoding, and whether SubWire has added a sanitizer (if it has, the
   safe-artifact rule may be relaxed but never violated).
4. Mark the result `compatible`, `needs-delta-audit`, or `stale`.

## Validation

- Static/unit: identifier-prefix tests against the qapp-core math; payload gate;
  Markdown-escaping and URL-scheme tests; cover-encoding fail-closed.
- Local runtime: derive prefix, build payload, run the mirrored SubWire
  renderable gate before any write.
- Host/live: read-only prefix search plus an exact-identifier fetch of an
  existing real SubWire article, compared field by field (including bare-base64
  cover and Core metadata mirror).
- Cross-app: an owner-authorized publication then discovered and rendered in
  native SubWire (not just the publishing app).

## Known failure modes

- **Prefix mismatch:** a mis-derived identifier is never found, and no app-side
  success message makes it visible.
- **Non-WebP cover:** SubWire hardcodes `data:image/webp`, so the cover breaks.
- **Oversized artifact:** `>= 5 MiB` is dropped by qapp-core discovery; a `size`
  of exactly 32 is also dropped.
- **Core metadata overflow:** exceeding Core's title/description caps can reject
  or silently truncate the discoverable mirror.
- **First-page displacement:** SubWire discovers globally with `limit: 20` and no
  name filter, so a publication can be pushed off the first page by newer
  articles.
- **Per-node propagation lag:** a fresh resource can return `404 Data
  unavailable` on one node while another serves it; report `present: false`
  truthfully.
- **Unsanitized renderer:** unescaped text or a non-allowlisted URL scheme turns
  into injection in SubWire's `dangerouslySetInnerHTML` boundary.

## Non-goals

- A general Qortal article/editor API, or any requirement to use a specific
  editor.
- SubWire UI, moderation, engagement, or playlist/`media` episodes beyond the
  article `DOCUMENT`.
- Quitter announcements or Q-Tube video.

## Harvest / maturity update

- Upgrade evidence: none outstanding — owner real-host SubWire discovery/render
  is recorded (2026-09-13).
- Downgrade to `stale` if the SubWire payload/prefix/discovery contract or the
  qapp-core identifier math changes, or if the renderer's sanitization behavior
  changes materially.
- Re-verify before claiming any surface beyond article discovery/render.
