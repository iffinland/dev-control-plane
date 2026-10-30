# Qortal Q-App host compatibility notes

Status: **candidate reference**, derived from a third-party guide dated
2026-10-29. It records what a legacy Qortal dApp audit should verify. It does
**not** establish current platform behavior.

Before use, resolve current Core, Hub and GO source/runtime through
[`ENVIRONMENT.md`](../../../ENVIRONMENT.md). Where an item conflicts with a
verified skill, the verified skill plus its recorded runtime evidence wins until
the boundary is re-checked.

## Version pins claimed by the source

| Component | Claimed version | Status |
| --- | --- | --- |
| Qortal Core | 6.1.9 live / 6.1.4 source with diff checked | VERSION-SENSITIVE |
| Qortal Hub | 3.0.3 released; `develop` at 2026-10-29 | VERSION-SENSITIVE |
| Qortal GO | 3.0 (Capacitor, Android System WebView) | VERSION-SENSITIVE |

Do not repeat these versions as current. Record what is actually running.

## 1. Boot, serving and routing

Audit each item against the current host and a real render:

- **Host detection:** the guide claims `qortalRequest` is a global lexical
  binding, so `typeof qortalRequest === 'function'` works while
  `window.qortalRequest` does not. Verify in the current `q-apps.js`.
- **Outside-host fallback:** an app opened in a plain browser should show a
  truthful "open in Hub/GO" state instead of crashing.
- **Asset base:** relative asset paths (`base: ""`) are required. Absolute
  `/assets/...` collides with Core's own API. Check the built HTML, not only the
  source config.
- **Serving context:** `APP` serves `index.html` for unknown paths; `WEBSITE`
  does not. Confirm path vs hash routing accordingly.
- **Injected globals:** `_qdnContext`, `_qdnTheme`, `_qdnLang`, `_qdnService`,
  `_qdnName`, `_qdnIdentifier`, `_qdnPath`, `_qdnBase`,
  `_qdnBaseWithPath` are claimed to be injected. Verify names, encoding and
  Dev Mode values.
- **Router basename:** derive it from `_qdnBase`; tolerate `+` vs `%2B` and
  non-ASCII name encoding. Never hard-code the published name.
- **Non-default APP identifiers:** the guide warns that Core adds
  `?identifier=` only to static tags, so dynamic chunks can resolve to the
  default resource. Verify before publishing an APP under a non-default
  identifier.
- **Deep links:** an `APP` deep link should render; a `WEBSITE` deep link needs
  hash routes or real files.

## 2. Host messages, navigation and back

- Listen for `THEME_CHANGED`, `LANGUAGE_CHANGED` and `NAVIGATE_TO_PATH` from an
  ancestor window; ignore unknown messages.
- On `NAVIGATE_TO_PATH`, navigate and reply with
  `{action:'NAVIGATION_SUCCESS', path}` immediately. The claimed window is
  about 200 ms, after which the host may reload the frame and lose state.
  VERSION-SENSITIVE.
- Never use `window.history.back()` or `navigate(-1)` as the app's Back button;
  all host tabs may share one browser history. Keep an in-app stack.
- Verify share links reconstruct correctly after stripping host-added query
  keys (`theme`, `lang`, `identifier`, `time`, `isManualNavigation`,
  `goWidget`).
- `qortal://` link rules claimed: app-name segment raw except spaces as `%20`;
  each path segment `encodeURIComponent`; `+` stays literal. Test real names
  containing `+`, spaces, `/`, non-ASCII and reserved characters.

## 3. Theme, frame and mobile

- Paint theme before the app bundle: `?theme=` → remembered value → OS
  preference. A reload without `?theme=` reportedly defaults to light.
- Re-theme live on `THEME_CHANGED`; define colours as tokens, not per-component
  hard-coded values.
- Size from the actual frame height (`window.innerHeight`/`--app-height`), not
  `100vh`.
- Test at least: 360×740, 390×844, 844×390, ~700 wide, 1280+; touch and
  keyboard-open states; Android Back; public node.
- Check 44 px touch targets, focus visibility, no hover-only actions, no
  sideways scroll, safe-area insets and dialog actions that stay visible.
- `overflow-x: clip` belongs on the app root, not `html`/`body`, per the guide.

## 4. Reads, search and data availability

These are the highest-value legacy defect checks:

- **Lists need `mode=ALL`:** the claimed default is `LATEST`, one row per
  (name, service). Confirm against the current node.
- **Always send an explicit `limit`:** a missing or zero limit is claimed to
  return everything. Page with `offset`.
- **Search is contains-match by default.** `prefix=true` changes every text
  term (identifier, name, title, description, query) to starts-with. Re-check
  exact identity in code.
- **Names and identifiers must be encoded by the app.** The guide claims
  `q-apps.js` concatenates parameters without encoding. Use `fetch` +
  `URLSearchParams`/`encodeURIComponent` for user-supplied values.
- **Trust the search row for publisher identity and coordinates,** not the body.
  Validate and normalize every body.
- **Data may not be on the node yet.** Use async/status, bounded backoff,
  "Fetching from peers…", then a truthful "not available" state. Never cache a
  failure as "does not exist" for the session.
- **Status:** `DOWNLOADED` may need `build=true`; tiny resources can report odd
  chunk counts; `NOT_PUBLISHED` can be temporary for a just-published item.
- **Avatars/images:** build `/arbitrary/...` URLs directly, lazy-load, and
  distinguish "not published" from "still fetching".
- **REST vs bridge:** prefer app-built REST reads where encoding, paging and
  caching matter; use bridge actions when the host contract is the point.

**CONFLICT:** the guide says `exactmatchnames=true` / `exactMatchNames` filters
exactly. The verified `qortal-qdn-content-crud` skill recorded that
`names=...&exactMatchNames=true` did not filter on an observed node and
returned foreign rows. Do not rely on the guide here; re-check on the target
node and filter the exact `(name, service, identifier)` in code.

## 5. Writes, publish and money

- Check signed-in state, name ownership, balance and the fee **before** showing
  the final write action; show the cost.
- Every publish is claimed to cost 0.01 QORT and require a registered name.
  Confirm current fees from the node rather than hard-coding them.
- Never publish automatically: not at boot, not to initialize an index, not on
  a failed read, not in a loop.
- The account limit is claimed at 25 unconfirmed transactions. Batch writes
  conservatively, wait for room, put a derived index last, and retry only
  reported failed items with the same identifiers.
- **A timeout is unknown, not failure.** The host may still complete the write
  after the app times out. Look up the resource/transaction before offering
  Retry. Never pay or publish twice.
- A user decline is a quiet cancel, not a red error. Normalize all host error
  shapes; never render `[object Object]`.
- Money moves only after an explicit tap showing amount, coin and recipient.
  Validate recipient, asset, balance, fee and unconfirmed count first. Resolve
  names to the current owner at pay time.
- Record pending money state locally before asking the host, and verify a
  payment on chain before marking an order paid.
- The guide claims `PUBLISH_MULTIPLE_QDN_RESOURCES` partial failure rejects with
  `error.unsuccessfulPublishes`. Our verified skill recorded that the host can
  also **resolve** with that list. Normalize both shapes; never treat a partial
  result as success.

## 6. Encryption, security and data contracts

- `*_PRIVATE` services must receive encrypted data; public services must not.
  The guide claims Core checks only some single-file services and does **not**
  enforce encryption for `FILE`, `IMAGE`, `DOCUMENT` and their private forms on
  6.1.9. Verify on the target Core; the app must encrypt regardless.
- Metadata (title, description, tags) is public even for encrypted resources.
- Do not put secrets, recipients' private data or a top-level `error` key in
  stored JSON.
- UTF-8 safe base64 only; never `btoa(JSON.stringify(...))`.
- Validate every field on read; render user content as text or sanitize with a
  maintained library and DOM post-processing. Do not regex over sanitized HTML.
- All apps on a node share an origin: prefix storage keys with the app slug and
  store no secrets there.
- Identifiers: app-prefixed, `[A-Za-z0-9_-]`, at most 64 UTF-8 bytes, unique
  per item; new data kinds get new prefixes.
- Data changes are additive and versioned. Preserve existing services,
  identifier schemes, JSON shapes, encryption and tombstones for compatibility.
- There is no network-wide delete. A delete is a tombstone convention
  (`"D"` or a JSON `{deleted:true}`), and old bytes may remain elsewhere.
- Deadlines must use block time, not the publisher-signed resource `created`
  time.

## 7. Links, files and media

- The guide claims `http(s)` link clicks are blocked and popups are not
  allowed; copy the URL to the clipboard and say so.
- Build `/arbitrary/...` URLs rather than using `<img src="qortal://...">`.
- Downscale camera images before publishing; publish media before the entity
  that references it; keep single-file read URLs at the bare identifier.
- Claimed caps (VERSION-SENSITIVE): APP 50 MiB, IMAGE 10 MiB, THUMBNAIL 500
  KiB, JSON 25 KiB, and a 2 GB/500 MB host publish cap. Confirm current caps.
- PDFs may need a host PDF reader or a bundled viewer; verify in the target
  host rather than assuming inline embedding works.

## 8. Performance, testing and release gates

- Count first-load searches and body fetches. Merge identical in-flight
  requests, cache for a short session TTL, never cache failures, and fetch
  bodies only near the viewport.
- Avoid per-row media queries, tooltips, avatars or heavy components in long
  lists.
- Lazy-load routes and heavy libraries; keep the largest chunk and zip small.
- Handle stale chunks after an app update: a missing chunk may return
  `index.html` with status 200; retry once, reload once, then show a truthful
  error.
- Test with unit/integration mocks, a read-only real node, Hub Dev Mode and GO
  where applicable. Include decline, timeout, partial publish, public node,
  unavailable data, account switch, deep links, keyboard and update recovery.
- Release readiness requires the exact release artifact, zip layout check,
  published metadata file-list comparison, resource status `READY`, version and
  changelog, a retained rollback artifact, and owner acceptance. It does not
  authorize publication.

See [`legacy-app-audit-checklist.md`](legacy-app-audit-checklist.md) for the
operational checklist and evidence fields.

## 9. Claims requiring confirmation before reuse

The source itself marks several points unverified. Additional
version-sensitive or conflicting claims are listed here. Do not promote any of
these to a verified skill without current evidence.

| Claim | Why it is not verified |
| --- | --- |
| Exact CSP header and sandbox flags | Source claims a verified header, but the host can change per release. |
| 60 s dialog lifetime / late Accept still runs | The source says source reading plus field observation, not a controlled runtime test. |
| `GET_USER_ACCOUNT` hangs while Hub is locked | Reported, not traced. |
| Cold `/arbitrary/...` read duration and retry counts | Environment-dependent. |
| In-app Back then Android Back history effect | Traced in source, not observed in a running host. |
| Dev-proxy `/assets/*` 404 mechanism | Observed on one version; mechanism inferred. |
| `pollOptions` single-string behavior | Pinned to Hub 3.0.3/GO source; re-check newer hosts. |
| Hub `develop` webview model and new actions | Unreleased; parameters explicitly unverified. |
| DOMPurify minimum version | Third-party advisory claim; use a current maintained release and re-check. |
| `qapp-core` `publicSalt`/identity compatibility | Library-specific; inspect the app's actual dependency. |
| Service size caps and fee values | Version- and node-dependent; read current source/node. |
| `FILE`/`IMAGE`/`DOCUMENT` private-encryption enforcement | Core-version-specific; verify. |
| `exactmatchnames` behavior | Conflicts with our verified skill's observed node behavior. |
| `PUBLISH_MULTIPLE` result shape | Our verified skill observed both reject and resolve shapes. |

## 10. Qortal versus Qortium

These notes are **Qortal only**. Qortium Home/Core use their own bridge actions,
publishing tokens and QDN semantics. Do not transfer `qortalRequest`, Qortal
service/identifier rules, fee assumptions or host messages to Qortium.

Potentially reusable *practices* (not contracts) may be considered for Qortium
only after separate source/runtime validation:

- audit phases and evidence fields;
- explicit write/money gates and never-auto-retry rules;
- row/fetch availability distinctions;
- additive data versioning and tombstone compatibility;
- release artifact/served-bytes verification;
- accessibility, keyboard and responsive checklists;
- overnight-session integration discipline.
