---
name: qortal-quitter-announcement
description: Use when a Qortal app must publish an optional, owner-approved announcement of a published article as a Quitter-compatible QDN DOCUMENT, including the Quitter identifier namespace, payload shape, article deep-link text and the 280-character display constraint.
---

# Qortal Quitter announcement (SubWire-style cross-post)

- Platform: `qortal`
- Maturity: `verified-runtime`
- Last checked: `2026-09-13`
- Owner: shared capability library

## Use when

- After an app publishes an article, the owner may explicitly opt in to a
  Quitter-visible announcement that references that article.
- You need the exact Quitter post namespace/prefix, payload shape, image encoding
  and the verified SubWire-style share text.

## Do not use when

- You need a general Quitter or social API (timelines, chat, follow/like/reply,
  messaging, profile writes). This skill covers only the announcement write.
- You are publishing to Qortium. The Quitter namespace/salts are Qortal-specific.
- You want to make the announcement automatic or implicitly bundled with the
  article publication. It must stay optional, separately approved and
  independently reported.
- You need Q-Tube video or SubWire article publication — use those skills.

## Authoritative evidence

| Source | Revision | Paths / contract proved |
| --- | --- | --- |
| `Qortal/Quitter` `master` | `4e4246c3283bcbc8e05e683260692ed36144f862` | post payload/render contract, image handling (sniffs image magic bytes), `MAX_TEXT_LENGTH = 280` display truncation. |
| `Qortal/Subwire` `master` | `a933a6c44d60db19cd219408e36c747aebcce994` | `src/utils/quitterQdn.ts`: `appName = 'quitter'`, `publicSalt = '6hMqDBxky6j1G2wZEHgIiOeApj3x3CP8LQwg0Ok0RVc='`, `buildIdentifier(ENTITY_POST='POST', ENTITY_ROOT='ROOT', false)`; SubWire's own share text shape and single compressed cover image. |
| `Qortal/qapp-core` `master` | `0f9d6ac5134ef2f82c1444a74e78471ddc7eb7df` | `hashWord`/`buildIdentifier` identifier math (mirror it; do not reimplement from memory). |
| `Qortal/qortal` (Core 6.1.9) `master` | `108bf191d42d710ec617f535af30cfd82fc03c87` | `DOCUMENT` service and `qortal://APP/…` deep-link resolution. |

Runtime evidence (why maturity is `verified-runtime`):

- Read-only Qortal mainnet nodes `127.0.0.1:24991` / `:24992`, Core
  `qortal-6.1.9-108bf19`, height 2723000 (2026-09-13). The derived Quitter prefix
  `MhNiRYdzkaP9dz-kX47dT-XrFXaYetyErMdF-` returned 20 real `DOCUMENT` hits, and
  a real SubWire cross-post for an existing Shadow Archives article was read
  back: gate passed, first line `New publication: <title>`, referenced the
  SubWire article identifier, one image attached.
- Owner real-host acceptance **2026-09-13**: explicit Blog announcement with
  separate approval → Quitter discovery/render with article link and cover
  `OWNER-RUNTIME PASS`.
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

- **Verified Qortal platform behavior:** `DOCUMENT` service, deep-link
  resolution, identifier derivation math, QDN availability states.
- **Current community-app convention (dated, not platform):** Quitter's
  `quitter` appName/publicSalt and `POST`/`ROOT` entity derivation, the post
  payload field names, the 2-image limit, image magic-byte sniffing, and the
  `MAX_TEXT_LENGTH = 280` display truncation.
- **Project-local implementation pattern (not shared):** the publishing app's
  opt-in UI, prefilled text, cover pipeline and the covered article's deep link.

## Reusable contract / procedure

1. **Separate `DOCUMENT` write.** The announcement is its own QDN write in
   Quitter's namespace — not a SubWire resource and not a chat/social
   transaction in another service.
2. **Derive the identifier from current qapp-core math.** For the verified
   SubWire-style shape: `appName = 'quitter'`,
   `publicSalt = '6hMqDBxky6j1G2wZEHgIiOeApj3x3CP8LQwg0Ok0RVc='`,
   `buildIdentifier(ENTITY_POST='POST', ENTITY_ROOT='ROOT', false)`. The verified
   post prefix is `MhNiRYdzkaP9dz-kX47dT-XrFXaYetyErMdF-`; the full identifier
   appends `<uid>-v1`.
3. **Payload:** `{ text, timestamp, name, images?: [{ src: <bare base64> }] }`,
   `service = DOCUMENT`. At most 2 images; Quitter sniffs image magic bytes, so
   send real encoded image bytes as bare base64.
4. **Text shape:** `New publication: <title>` followed immediately by the
   article deep link, e.g.
   `qortal://APP/Subwire/article/<percentEncodedName>/<identifier>`; put any
   excerpt **after** the references.
5. **Respect the display constraint.** Quitter truncates displayed text at
   `MAX_TEXT_LENGTH = 280`, so a reference placed after a long excerpt can be
   hidden. Reference-first ordering is the safe pattern.
6. **Explicit opt-in and separate approval.** The announcement is an optional
   owner action with its own host approval; it must never be bundled silently
   into the article publication.
7. **Independent, truthful outcome.** Announcement success/failure is reported
   separately (`announced` / `ambiguous` / `failed` / `declined` by owner). An
   announcement failure must not invalidate the already-published article, and
   the article's existence is not proof the announcement succeeded.
8. **Never auto-retry an ambiguous write.** One write per action; a timeout is
   reported as ambiguous and requires an explicit owner decision.

## Freshness and compatibility gate

Before reuse:

1. Re-check `Qortal/Quitter` `master` and `Qortal/qapp-core` `master` heads and
   the running Core build against the pins above.
2. Recompute the post prefix and confirm it still returns real Quitter resources
   on a live node.
3. Inspect the payload field names, the image limit/encoding, and
   `MAX_TEXT_LENGTH`.
4. Mark the result `compatible`, `needs-delta-audit`, or `stale`.

## Validation

- Static/unit: prefix derivation, payload shape, image count/encoding, text
  ordering, truthful outcome states, exactly one write per action.
- Host/live: derive the prefix and fetch/compare an existing real Quitter
  cross-post read-only (text, referenced identifier, image count).
- Owner: explicit opt-in → separate approval → Quitter discovers/renders the
  announcement with its article link and cover.

## Known failure modes

- **Reference hidden by truncation:** a long excerpt placed before the link is
  cut off at 280 displayed characters.
- **Wrong namespace/prefix:** the post is never discovered, or is written into a
  resource no consumer reads.
- **Too many images or non-image bytes:** the write is rejected or the image
  does not render.
- **Auto-retry of an ambiguous write:** risks duplicate announcements.
- **Coupling the outcomes:** treating an announcement failure as an article
  failure (or the reverse) misreports the real state.

## Non-goals

- A general Quitter/social API: feeds, chat, follow/like/reply, DMs, profile
  writes.
- Automatic, non-optional, or retried announcements.
- More than one announcement shape; only the verified SubWire-style cross-post is
  covered.

## Harvest / maturity update

- Upgrade evidence: none outstanding — owner real-host announcement
  discovery/render is recorded (2026-09-13).
- Downgrade to `stale` if Quitter's payload/namespace or `MAX_TEXT_LENGTH`
  changes, or if qapp-core identifier math changes.
- Re-verify before claiming any Quitter surface beyond this announcement.
