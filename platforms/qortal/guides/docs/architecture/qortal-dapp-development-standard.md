# Qortal dApp Development Standard

## Purpose

Define the durable, cross-project rules for building, reviewing, validating and
releasing Qortal Q-Apps (dApps) and QDN-backed web applications.

This standard is evidence-based. Every platform statement is either traceable to
a current Qortal source inspected on the date recorded in
[Reference revisions](#reference-revisions), or is explicitly marked as
inference, unknown, or owner decision.

## Scope

Applies to:

- new Qortal Q-Apps and webportals;
- audits and refactors of existing Qortal applications;
- QDN publication, discovery and engagement data models;
- runtime performance and diagnostics work; and
- release, provenance and deployment records for published apps.

Does not apply to Qortal Core development, consensus changes, or the internal
implementation of Qortal Hub, except where integration behavior must be read
from them.

## How to read the fact labels

- **VERIFIED** — traced to a specific current source path or measured behavior,
  with the revision recorded.
- **INFERENCE** — supported by evidence but not directly proven for the target
  case.
- **UNKNOWN** — evidence unavailable or not inspected. Blocks any dependent
  claim.
- **OWNER DECISION** — product or authorization choice not derivable from
  source.

## 1. A real Qortal host is the final truth

Static review, typecheck, lint, unit tests, mocked bridge tests, local Vite
preview, and a successful build do **not** prove that an app works inside
Qortal.

**VERIFIED.** Qortal Core renders Q-Apps through `/render/{service}/{name}` and
injects `/apps/q-apps.js` plus `_qdn*` context variables
(`src/main/java/org/qortal/api/HTMLParser.java`,
`src/main/java/org/qortal/api/restricted/resource/RenderResource.java`, Core
revision recorded below). A plain Vite dev server has no such bridge.

The completion gate for runtime behavior is the app running in a real Qortal
host:

- **Qortal Hub** (desktop/web/mobile client) — `Qortal/Qortal-Hub`;
- a hosted Hub instance such as `hub.qortal.link`; or
- a Qortal node in gateway mode, when gateway behavior is what is claimed.

Legacy `qortal-ui` MUST NOT be used as the validation host or as authority — it
is archived and no longer supported after Core 5.0.

## 2. Do not invent the platform; read it

Before implementing platform integration, read the current sources:

| Question | Read first |
| -------- | ---------- |
| Which `qortalRequest` actions exist and what do they accept? | Core `src/main/resources/q-apps/q-apps.js` and Hub `src/qortal/qortal-requests.ts` |
| What does a read return? | Core API resource class under `src/main/java/org/qortal/api/resource/` |
| What services/limits exist? | Core `src/main/java/org/qortal/arbitrary/misc/Service.java` |
| What statuses exist? | Core `src/main/java/org/qortal/data/arbitrary/ArbitraryResourceStatus.java` |
| What does the framework provide? | `Qortal/qapp-core` (hooks, queues, caches, components) |
| What is the current starter? | `Qortal/qapp-templates` + `Qortal/create-qortal-app` |

Do not assume that documentation matches source. **VERIFIED discrepancy
example:** the published Q-Apps API page documents only `_qdnTheme` and
`_qdnContext`, while Core's `HTMLParser` injects `_qdnContext`, `_qdnTheme`,
`_qdnLang`, `_qdnService`, `_qdnName`, `_qdnIdentifier`, `_qdnPath`, `_qdnBase`
and `_qdnBaseWithPath`. Treat source as authoritative and report the
discrepancy rather than silently choosing one.

## 3. Q-App runtime model

**VERIFIED.** A Q-App is a static JavaScript bundle published to QDN under the
`APP` (or `WEBSITE`) service. A host loads it in an iframe from the node's
`/render/...` route. Core then:

1. injects `<base href="...">` so relative asset URLs resolve against the
   resource path;
2. injects `q-apps.js`, which defines `qortalRequest()`; and
3. injects `_qdn*` variables describing the app's own context.

Consequences:

- The app's `_qdnName`, `_qdnService` and `_qdnIdentifier` identify **the
  published app**, and `_qdnName` is the publishing name that owns it.
- In the normal case the iframe origin is the node API origin, so relative
  requests (`/arbitrary/...`, `/names/...`) resolve to the node API.
- **VERIFIED.** `APP` resources auto-route unhandled paths to `index.html`;
  `WEBSITE` resources return 404 for missing paths (official Q-Apps API
  documentation, "Routing").
- **VERIFIED.** The production render path sets
  `Content-Security-Policy: default-src 'self' 'unsafe-inline' 'unsafe-eval';
  font-src 'self' data:; media-src 'self' data: blob: http://127.0.0.1:*
  http://localhost:*; img-src 'self' data: blob:; connect-src 'self' wss:
  blob:` (Core `ArbitraryDataRenderer.java`). Design assets, media and network
  calls to fit this policy; external HTTPS APIs and image CDNs are not
  available by default.
- **VERIFIED.** Rendering requires prior authorization
  (`Security.requirePriorAuthorization`) unless `qdnAuthBypassEnabled` is set or
  the node is in gateway mode (`Settings.isQDNAuthBypassEnabled`). Do not claim
  that a bare `/render/...` URL proves app behavior.

## 4. Reads: prefer the node API through `qortalRequest`

**VERIFIED.** Core's injected `q-apps.js` handles these read actions locally
(no host approval) by calling the node API: `GET_ACCOUNT_DATA`,
`GET_ACCOUNT_NAMES`, `SEARCH_NAMES`, `GET_NAME_DATA`, `GET_QDN_RESOURCE_URL`,
`LIST_QDN_RESOURCES`, `SEARCH_QDN_RESOURCES`, `FETCH_QDN_RESOURCE`,
`GET_QDN_RESOURCE_STATUS`, `GET_QDN_RESOURCE_PROPERTIES`,
`GET_QDN_RESOURCE_METADATA`, `SEARCH_CHAT_MESSAGES`, `LIST_GROUPS`,
`GET_BALANCE`, block/transaction fetches, and others.

`qortalRequest()` is preferred over raw `fetch()` because the action contract is
kept stable while internal endpoints can change. Direct same-origin reads are
acceptable for simple, stable endpoints when the app must avoid the bridge
(e.g. `<img src="/arbitrary/THUMBNAIL/...">`).

**VERIFIED** identity caution: `GET_USER_ACCOUNT` returns `{address, publicKey}`
only. It does **not** return a name. A publishing name must be resolved
separately (`GET_PRIMARY_NAME`, `/names/address/{address}`) and the user may own
several names.

**VERIFIED — permissioned authentication is not an approval-free read.**
`GET_USER_ACCOUNT` is dispatched by the host, not handled locally by
`q-apps.js`. At the inspected Hub revision (`src/qortal/get.ts`) the host checks
a saved permission and a session permission first; otherwise it opens a user
approval dialog (`getUserPermission`) and returns the address/public key only
when the user accepts or has previously permitted it. Rejection is an error.
Core `q-apps.js` gives the action a one-hour default timeout because the user may
be deciding the popup, and `GET_PRIMARY_NAME` is likewise dispatched by the host
(`Qortal-Hub/src/qortal/qortal-requests.ts`). Wrapper guidance MUST therefore
distinguish three classes — public/idempotent node reads, permissioned
host-mediated reads/authentication, and signed writes — and MUST implement
first-time, remembered, session, rejected and unresolved permission states, no
duplicate concurrent prompts, and no automatic retry after rejection. The full
contract is in
[`../../agents/qortal-qdn-and-bridge.md`](../../agents/qortal-qdn-and-bridge.md) §2.

## 5. Writes require the host's approval and signing boundary

**VERIFIED.** Write actions such as `PUBLISH_QDN_RESOURCE`,
`PUBLISH_MULTIPLE_QDN_RESOURCES`, `SEND_CHAT_MESSAGE`, name registration and
transactions are forwarded to the host UI, which shows an approval dialog and
performs signing. Permissioned account/authentication actions
(`GET_USER_ACCOUNT`) follow the same host-mediated approval boundary with their
own saved/session permission model; they are not approval-free reads (see §4).

Rules:

- Never retry an ambiguous write automatically. QDN publication spends a fee
  and can take a long time; a timeout does not mean the write did not happen.
- Never treat `published` as `confirmed`, and never treat a `READY`/available
  status as proof of the intended revision. `GET_QDN_RESOURCE_STATUS` reports
  the state of the resource the node already knows about; an existing resource
  can remain `READY` and schema-valid while a newly submitted update is absent
  or unconfirmed. Separate publication submission, transaction confirmation
  (where applicable), resource availability/status and intended-revision
  verification, and compare the served resource against the intended
  operation/content with an appropriate
  revision/version/content-hash/exact-relevant-payload check.
- Never assume a user has a publishing name. Accounts without a registered name
  cannot publish to QDN from a Q-App.
- Never assume writes are atomic. `PUBLISH_MULTIPLE_QDN_RESOURCES` groups
  resources into one approval but performs independent transactions and returns
  partial success/failure information.

## 6. Identity, ownership and authority

QDN resources are owned by a **registered name**, not by the app.

**VERIFIED.** To publish or overwrite a resource, the authenticated account must
currently own the `name` used. If the name is sold or transferred, update
authority moves with it. A resource is addressed by
`(name, service, identifier)`, and re-publishing the same triple overwrites it.

Verified rules for owner/authority logic:

- The app publisher name comes from `_qdnName`. Do not hardcode it.
- Establish "is the current user the owner?" by resolving the account's names
  (`GET_ACCOUNT_NAMES` / `/names/address/{address}`) or by comparing the
  `/names/{name}` owner address against the connected account address.
- Ownership can change. Resolve it for the session; do not cache it forever.
- An embedded `author`/`owner` field inside a payload is **untrusted data**.
  Display names and payload claims are not proof of authority.
- QDN is permissionless. **VERIFIED** (official docs): it is not possible to
  verify that a resource was published by a particular app. Validate resource
  contents against an expected schema rather than trusting the publisher.
- Derived indexes, caches and lists never establish ownership.

**OWNER DECISION.** Any allowlist, role model, or moderation authority beyond
"owner of the publishing name" must be explicitly approved and documented in the
project context.

### Rendering safety is a separate gate

Schema validation, publisher/authority validation and rendering safety are three
separate concerns. Satisfying the schema and proving name ownership does NOT
make untrusted content safe to render.

- **PLAIN TEXT** — escape and render as text; never interpolate as trusted
  HTML.
- **RICH HTML** — sanitize untrusted or stored HTML with a maintained
  sanitizer, or render a constrained safe document model. Block or remove
  scripts, event-handler attributes and other executable markup; validate
  allowed URL schemes; handle `javascript:`, `data:` and other dangerous URLs
  intentionally; and ensure transformations after sanitization do not
  reintroduce unsafe markup.

The reusable requirement, including its application to comments, rich-text
posts, imported content, owner preview and cached/stored content from any
publisher, is defined in
[`../../agents/qortal-architecture-and-data-integrity.md`](../../agents/qortal-architecture-and-data-integrity.md)
§11. Owner-authored content is not exempt. The sanitizer/editor choice stays a
project decision.

## 7. QDN services: use the correct one

**VERIFIED** (Core `Service.java`). Frequently relevant public services and
their limits:

| Service | Notes |
| ------- | ----- |
| `APP` | Multi-file app bundle, auto-routes to `index.html`; 50 MB |
| `WEBSITE` | Multi-file site, 404 on missing paths; requires an index file |
| `DOCUMENT` | Generic document/JSON-ish content used by many apps |
| `JSON` | Validated JSON, single, 25 KB; useful for small records |
| `IMAGE` | Single, 10 MB |
| `THUMBNAIL` | Single, 500 KB; `qortal_avatar` identifier is the conventional avatar |
| `VIDEO` | Media streaming friendly |
| `AUDIO` / `PODCAST` | Media services |
| `METADATA` | Single; used for resource metadata sidecars |
| `LIST` / `PLAYLIST` | Single; the natural fit for ordered index/catalog resources |
| `BLOG` / `BLOG_POST` / `BLOG_COMMENT` / `COMMENT` | Blog-style services with size limits |
| `MAIL` / `MAIL_PRIVATE` | Mail; `MAIL_PRIVATE` is encrypted to recipients, 5 MB |
| `MESSAGE` / `MESSAGE_PRIVATE` | Message services, 1 MB |
| `CHAIN_COMMENT` | ≤239 bytes, stored fully on-chain |

Private variants (`*_PRIVATE`) are encrypted to recipient public keys.

**VERIFIED.** Publishing metadata supports `title`, `description`, `category`
and up to five tags (`tag1`..`tag5`). Categories are a fixed enum (see Core
`Category`, mirrored in the official Q-Apps API docs).

**OWNER DECISION / PROJECT** which services and identifier scheme a given app
uses. The scheme MUST be documented in `projects/<project>.md`.

## 8. Identifiers, app namespacing and discovery

**VERIFIED** (official Q-Apps API documentation): use an app-specific prefix on
identifiers (e.g. `myapp_...`) so an app can find its own records with
`SEARCH_QDN_RESOURCES` using `identifier` + `prefix: true`.

**VERIFIED — node endpoint query parameters** (Core `ArbitraryResource.java`,
`GET /arbitrary/resources/search`). Query names are lowercase: `service`,
`query`, `identifier`, `name` (repeatable list), `title`, `description`,
`keywords` (repeatable list), `prefix`, `exactmatchnames`, `default`, `mode`
(`ALL`/`LATEST`), `minlevel`, `namefilter`, `followedonly`, `excludeblocked`,
`includestatus`, `includemetadata`, `before`, `after`, `limit`, `offset`,
`reverse`.

**VERIFIED — `SEARCH_QDN_RESOURCES` bridge fields are different.** The
`qortalRequest` action accepts camelCase fields that `q-apps.js` translates to
the node query names above (`includeStatus` → `includestatus`,
`includeMetadata` → `includemetadata`, `exactMatchNames` → `exactmatchnames`,
`minLevel` → `minlevel`, `nameListFilter` → `namefilter`) and accepts `names`
(array, each emitted as `name=`) in addition to the singular `name` string.
Lowercase REST query names passed to the bridge action are silently ignored; use
the bridge field names for `SEARCH_QDN_RESOURCES`. Identifier matching is
substring matching unless `prefix: true` is set, so an exact resource identity
MUST be verified by post-filtering the returned `service`, `name` and
`identifier`; distinguish a null/default identifier from an explicit one.

Important limits:

- `query` searches name, identifier, title and description metadata. It does
  **not** search full body/content text. Full-text body search must be built
  from an app-maintained index or catalog resource, not from Core search.
- `limit=0` is used by current apps to request no limit; use explicit budgets
  and pagination regardless (see §9).

## 9. N+1 QDN discovery is an architecture risk

A design that issues one status query, one like query and one comment query per
card does not scale. For 20 cards that is 60+ requests, each of which may trigger
network/peer work on the node.

Required patterns:

- Prefer one paginated `SEARCH_QDN_RESOURCES` with the bridge fields
  `includeMetadata` and `includeStatus` over per-item metadata fetches.
- Batch identity resolution. **VERIFIED.** Core exposes
  `POST /names/list` (primary names for a list of addresses) and
  `/names/address/{address}`; use them instead of one call per author.
- Keep a rebuildable, partitioned catalog/index resource (`LIST`/`JSON`) or a
  derived index, and treat it as non-authoritative: it may be stale, partial or
  unavailable, and it never proves ownership.
- Bound concurrency with a queue. **VERIFIED.** `qapp-core` ships
  `RequestQueueWithPromise` and uses it for search/fetch queues; current apps
  also cache primary names and profiles in IndexedDB with TTLs.
- Cache with explicit key, success TTL, failure TTL, invalidation and stale
  behaviour. Never let a failed or empty response poison a later success.
- Record and expose partial/unavailable discovery instead of silently reporting
  an empty or complete result.

## 10. Engagement data model

Distinguish a **content entity** (a post, video or article owned by its
publisher name) from an **interaction/operation resource** (a like, comment,
tip or share created by the actor who performs the action). Authority applies to
the operation resource being created or updated; the target/parent reference
must be validated independently and need not be owned by the actor. Liking or
commenting on another author's content therefore does not require owning the
target content.

**VERIFIED** current Qortal pattern (Quitter / Q-Tube, revision-scoped): a like
is a small resource whose identifier is derived from the target, published once
per acting name. "Has the current user liked this?" is a scoped lookup
(`{identifier, service, name}`).

Rules:

- **Like counts.** A raw count of matching QDN resources is NOT automatically
  the active-like count. Tombstoned/inactive state must be interpreted using the
  framework's current convention before counting, and the exact target identity
  (`service`, `name`, `identifier`) must be validated.
- **Uniqueness.** The current reference guidance is one active like per
  (content, acting name). This is revision-scoped reference behavior, not a
  timeless Core rule; document the app's chosen scope.
- **OWNER DECISION / PROJECT.** Whether "one like per user" means one per Qortal
  account/address or one per acting registered name is an application-level
  choice. It MUST be recorded explicitly and MUST NOT be silently redefined.
- **VERIFIED.** QDN has no on-chain delete. `DELETE_HOSTED_DATA` removes
  locally hosted data only and is refused on public/gateway nodes; the on-chain
  record remains. The current framework "unlike"/tombstone convention is to
  overwrite the resource with a small placeholder payload and filter it back out
  on read (revision-scoped, not a Core rule).
- Therefore: never claim that user data was deleted, and never claim a
  moderation action removed content from the network. Show honest states such as
  "hidden in this app" or "unliked / deactivated here".
- **Comments.** Comment authorisation is by publishing name: a user may edit
  only comments published under their own name. Do not trust an `author` field
  in the payload; commenting on another author's content does not require owning
  the target.
- **Transport is operation-specific.** Do not prescribe QDN publication as the
  transport for every interaction. Tips, shares and similar actions are
  operation-specific and may use a different verified mechanism.
- Engagement discovery is the primary N+1 risk surface; see §9.

## 11. Performance is a first-class requirement

Users should see a useful shell before all QDN/media content is available.

Establish patterns from current apps rather than inventing budgets:

- route-level code splitting and dynamic imports;
- lazy media loading; never download video that is not visible;
- application shell first, then progressive content;
- bounded, batched, paginated QDN discovery;
- catalog/index strategy for scalable listing;
- IndexedDB/cache for repeat visits and expensive lookups;
- background refresh with visible staleness;
- route/content prefetching only where it does not waste bandwidth;
- skeleton/partial/empty/error states.

Do not set arbitrary performance budgets. Measure first (see
[`../../agents/runtime-diagnostics-and-performance.md`](../../agents/runtime-diagnostics-and-performance.md))
and record the environment.

## 12. Local development and host validation

**VERIFIED.** Qortal supports real-time local development through a **local
Qortal node**:

- Hub Developer Mode requires the local node
  (`core:message.generic.devmode_local_node`);
- Hub calls `POST /developer/proxy/start` with the dev server address
  (e.g. `127.0.0.1:5173`);
- the node starts a proxy (`DevProxyManager`, `DevProxyServerResource`) that
  forwards to the dev server and injects `q-apps.js` and the `_qdn*` variables,
  with `qdnContext = "proxy"`;
- `POST /developer/proxy/stop` stops it.

Verified consequences:

- The dev proxy's CSP is `default-src 'self' 'unsafe-inline' 'unsafe-eval';
  media-src 'self' data: blob:; img-src 'self' data: blob:; connect-src 'self'
  ws:; font-src 'self' data:`.
- The proxy does not forward POST bodies to the source server (Core TODO), so
  do not rely on form POSTs during dev proxy validation.
- Node API default ports are **12391** (mainnet) and **62391** (testnet)
  (Core `Settings.java`). A node may be configured otherwise, and the host may
  select or override a node. Record the node and environment actually used; do
  not freeze one port as a platform constant.

A verified tunnel may provide read-only node access. It does not replace the
local-node Developer Mode contract or real-host validation. Follow the universal
environment registry; SSH configuration requires its own authorization.

## 13. Reference-first integration

When integrating with an existing Qortal feature (Q-Mail, engagement, avatars,
media, names), find a current working implementation first and verify the
contract:

- prefer current `Qortal/*` app repositories and `qapp-core`;
- treat `iffinland/iffi-vaba-mees-QORTAL` as a useful but non-optimal reference:
  it hardcodes an owner name and chat address, hand-rolls sanitization, and uses
  a legacy router. Do not copy those patterns.
- Treat community app conventions (for example Q-Mail's identifier and payload
  shape) as **conventions of that app at a pinned revision**, not as Core API.
  Verify them before relying on interoperability.

## 14. Validation layers are not interchangeable

Plan and report each applicable layer separately:

1. static and automated checks (typecheck, lint, unit tests);
2. local runtime/browser;
3. read-only node API evidence;
4. the app rendered in a real host (Hub, hosted Hub, gateway) with the real
   bridge and the real account;
5. exact published QDN resource behavior;
6. adversarial agent review;
7. owner product/runtime acceptance.

A passing layer never stands in for a different layer.

For any feature that renders untrusted or stored content, the static/automated
layer MUST include malicious HTML and URL fixtures: script tags, event-handler
attributes, unsafe `javascript:`/`data:` URLs, and post-sanitization
transformation cases. See §6.

## 15. One objective per task; evidence before implementation

One task controller has one primary outcome and one observable exit criterion.
Group findings only when they share architecture/domain, acceptance evidence and
regression scope.

Sequence:

```text
owner outcome or observed symptom
-> repository and working-tree baseline
-> current authoritative source and project context
-> real flow trace
-> first confirmed mismatch or approved design boundary
-> smallest coherent change
-> required validation layers
-> adversarial self-audit
-> remediation of confirmed in-scope BLOCKER/HIGH findings
-> truthful handoff
```

## 16. Evidence-based disagreement

Agents MUST NOT agree by default. When a requested method conflicts with source,
measured behavior, approved architecture, safety, data integrity or a materially
better path, the agent MUST state the evidence, explain the consequence,
recommend the better bounded alternative, and identify any owner decision still
required. Disagreement does not authorize scope expansion or external mutation.

## 17. Status vocabulary and completion gates

Report exactly one status:

- `COMPLETE` — objective met, all required layers verified.
- `PASS WITH OWNER VALIDATION REQUIRED` — automated work verified; named owner
  or live-host check still required.
- `CHANGES REQUIRED` — implementation or validation failed within scope.
- `ESCALATE TO CODEX` — high-risk, repeated-failure, or independent-audit case.
- `BLOCKED` — required evidence or authority is unavailable.
- `NOT VERIFIED` — a stated layer was not reached; say which.

`COMPLETE` requires: exit criterion met, required layers verified, no unresolved
BLOCKER/HIGH finding, the diff reviewed, and any external actions having
explicit authorization.

## 18. External actions require explicit authority

Reads never imply writes. Full filesystem/command access never implies
authority to commit, push, tag, publish to QDN, deploy, release, transact,
mutate GitHub issues/projects/PRs, or perform other external or destructive
actions. Absent explicit request, do not perform them.

## 19. Reporting and closure

Reports follow
[`../workflows/report-storage-policy.md`](../workflows/report-storage-policy.md).
Every final response MUST state the exact absolute report path. Issue closure
and other external mutations require explicit owner authorization.

## Reference revisions

Verified on **2026-09-11** (read-only clones/pages). Re-verify before any
dependent work; do not treat these as permanent.

| Source | Revision / date | Used for |
| ------ | --------------- | -------- |
| `Qortal/qortal` | `108bf191d42d710ec617f535af30cfd82fc03c87` (v6.1.9, 2026-07-08) | bridge shim, services, statuses, API, CSP, dev proxy, ports |
| `Qortal/Qortal-Hub` | `12a573b27246e8a626b24794830c6bc432d1b05d` (2026-08-23) | host request handling, approvals, dev mode |
| `Qortal/qapp-core` | `0f9d6ac5134ef2f82c1444a74e78471ddc7eb7df` (1.0.79, 2026-05-25) | framework hooks, queues, caches |
| `Qortal/qapp-templates` | `143cc7bffd265f543f96ef25bf1b58ef7bb04472` (2026-05-25) | current starter + router pattern |
| `Qortal/q-mail` | `ddf3aa928e0b51f89e2a6a7e86e5b44bdfd7b6d0` (3.2.1, 2026-05-28) | mail services, identifier/payload convention |
| `Qortal/q-tube` | `68c3ea706c4ab110ffa44a7f55f8e09bdf7e85ff` (2.1.0, 2026-07-15) | video/media + media services |
| `Qortal/Quitter` | `4e4246c3283bcbc8e05e683260692ed36144f862` (2026-05-25) | like/engagement model |
| `Qortal/Subwire` | `a933a6c44d60db19cd219408e36c747aebcce994` (2026-06-27) | publishing, caches, index patterns |
| `Qortal/create-qortal-app` | `ea9d720bb31fa42b777659aceccd69ad20393abb` (2025-05-12) | scaffolding |
| Q-Apps API docs | `https://qortal.dev/docs/q-apps` (2026-09-11) | services, routing, identifier guidance |
| `iffinland/iffi-vaba-mees-QORTAL` | `64f55bf7b6f4a1a093f19413d3a985e61a9fad37` (2026-06-11) | reference implementation (non-optimal) |

## Related guides

- [`../../agents/00-SESSION-START.md`](../../agents/00-SESSION-START.md)
- [`../../agents/01-TASK-CLASSIFICATION.md`](../../agents/01-TASK-CLASSIFICATION.md)
- [`../../agents/qortal-qdn-and-bridge.md`](../../agents/qortal-qdn-and-bridge.md)
- [`../../agents/qortal-architecture-and-data-integrity.md`](../../agents/qortal-architecture-and-data-integrity.md)
- [`../../agents/qdn-publication-discovery-and-scaling.md`](../../agents/qdn-publication-discovery-and-scaling.md)
- [`../../agents/live-qdn-validation.md`](../../agents/live-qdn-validation.md)
- [`../workflows/workflow-v2.md`](../workflows/workflow-v2.md)
