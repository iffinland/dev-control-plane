# Qortal QDN, Bridge and Host Integration

## Purpose

Guide safe integration with the current Qortal runtime: the `qortalRequest()`
bridge, the node API, the QDN resource model, the host rendering context, and
local development. Define the contract from current source, not from memory.

## Use when

Use for bridge detection, identity, reading or publishing QDN data, routing,
deep links, clipboard, display settings, CSP-constrained assets, host
integration, or local development/host runtime failures.

## Do not use when

Do not use this guide to define business authority (see
[`qortal-architecture-and-data-integrity.md`](qortal-architecture-and-data-integrity.md))
or discovery scaling (see
[`qdn-publication-discovery-and-scaling.md`](qdn-publication-discovery-and-scaling.md)).
Do not infer a bridge action from a node API capability.

## Prerequisites

- Current checked-out Qortal Core (`Qortal/qortal`) revision.
- Current host source for host behavior (`Qortal/Qortal-Hub`).
- Current framework source (`Qortal/qapp-core`) when used.
- The application's current runtime context (`_qdn*`) and account.

## Required inputs

- Desired read/write operation.
- Exact identity / publishing-name requirement.
- Expected approval/signing boundary.
- Required timeout, retry and recovery semantics.
- Routing, share, display and asset requirements.

## Verified runtime model

These statements are traced to the revisions in the standard's Reference
revisions table.

- **VERIFIED.** A Q-App is published under the `APP` (or `WEBSITE`) service and
  rendered by a host inside an iframe from `/render/{service}/{name}[/{path}]`.
- **VERIFIED.** Core injects `<base href="...">`,
  `<script src="/apps/q-apps.js">`, and a script defining `_qdnContext`,
  `_qdnTheme`, `_qdnLang`, `_qdnService`, `_qdnName`, `_qdnIdentifier`,
  `_qdnPath`, `_qdnBase`, `_qdnBaseWithPath`
  (`HTMLParser.addAdditionalHeaderTags`).
- **VERIFIED.** `APP` resources route unknown paths to `index.html`; `WEBSITE`
  resources return 404 (official Q-Apps API docs).
- **VERIFIED.** Public/idempotent node reads are handled by `q-apps.js`
  directly against the node API; permissioned account/authentication
  operations such as `GET_USER_ACCOUNT` are host-mediated; signed/write
  operations are host-mediated and approval/signing-gated (see §2).
- **VERIFIED.** The production render path CSP is
  `default-src 'self' 'unsafe-inline' 'unsafe-eval'; font-src 'self' data:;
  media-src 'self' data: blob: http://127.0.0.1:* http://localhost:*;
  img-src 'self' data: blob:; connect-src 'self' wss: blob:`.
- **VERIFIED.** Rendering requires prior authorization unless
  `qdnAuthBypassEnabled` or gateway mode
  (`Security.requirePriorAuthorization`, `Settings.isQDNAuthBypassEnabled`).
- **VERIFIED.** Node API default ports: 12391 mainnet, 62391 testnet.
- **VERIFIED.** The host may be a desktop/web/mobile Hub, a hosted Hub
  (`hub.qortal.link`), or a gateway node. `_qdnContext` distinguishes
  `render`, `proxy`, `gateway` and `domainMap` contexts.

## Workflow

### 1. Detect the bridge safely

`qortalRequest` is injected as a global. Detection MUST NOT throw or crash
startup when the app runs outside a host (for example a plain dev server or a
unit test):

- check `window.qortalRequest` / `globalThis.qortalRequest` and the declared
  global, in a `typeof` guard;
- expose a single typed wrapper; never call the raw global from UI components;
- represent explicit states: unavailable, ready, malformed response, timeout,
  rejected, error.

**UNKNOWN/legacy caution.** The reference app probes `window.parent.qortalRequest`
and `window.top.qortalRequest`. Current Core injects the function into the app's
own window; parent probing is not the verified mechanism and cross-origin access
may throw. Do not depend on parent probing.

### 2. Classify actions by approval boundary

Do not reduce the model to "reads vs writes". Distinguish at least three
classes, because they have different approval, timeout and retry semantics.

**1. Public / idempotent node reads.** `SEARCH_QDN_RESOURCES`,
`FETCH_QDN_RESOURCE`, `GET_QDN_RESOURCE_STATUS`, `GET_QDN_RESOURCE_URL`,
`GET_NAME_DATA`, `GET_ACCOUNT_NAMES`, `GET_ACCOUNT_DATA`, block/transaction
reads and similar actions are handled by `q-apps.js` against the node API with
no host approval. They are idempotent and MAY be retried with a short bounded
deadline when the failure mode permits.

**2. Permissioned host-mediated reads / authentication.** `GET_USER_ACCOUNT`
is **not** an approval-free read. **VERIFIED** (Hub `src/qortal/get.ts`): the
host first checks a saved permission and a session permission; otherwise it
calls `getUserPermission`, which opens a user approval dialog, and returns the
address/public key only when the user accepts or has previously permitted it.
Rejection is an error. Core `q-apps.js` gives `GET_USER_ACCOUNT` (together with
`SAVE_FILE`, `SIGN_TRANSACTION`, `DECRYPT_DATA`) a one-hour default timeout
precisely because the user may take a long time to accept or deny the popup.
`GET_PRIMARY_NAME` is also dispatched by the host
(`Qortal-Hub/src/qortal/qortal-requests.ts`), so "all reads are handled
locally by `q-apps.js`" is not an accurate dispatch rule.

Required behavior for account/authentication requests:

- **first-time request** — show a clear pending state and wait for the user;
  never apply an ordinary short background-read deadline to an unresolved
  permission dialog;
- **previously remembered permission** — the host may return the account
  without a new prompt; treat this as the accepted path;
- **session permission** — the host may be configured to authenticate for the
  session after an earlier acceptance; do not prompt again unnecessarily;
- **user rejection** — surface a distinct rejected state and do **not**
  automatically retry;
- **unresolved / pending approval** — keep one pending request, show the
  pending state, and let the user cancel; do not time out into a retry loop and
  do not open a second prompt.

Account/authentication requests MUST be deduplicated: concurrent callers MUST
share one in-flight promise so the user never sees duplicate simultaneous
permission prompts.

**3. Signed / approved writes.** `PUBLISH_QDN_RESOURCE`,
`PUBLISH_MULTIPLE_QDN_RESOURCES`, `SEND_CHAT_MESSAGE`, name operations,
transactions and other signing actions go through host approval and signing.
They are **not** automatically retryable.

### 3. Verify the exact contract before implementing

For any action, read Core `q-apps.js` (request params and URL construction) and
the host handler (`Qortal-Hub/src/qortal/qortal-requests.ts` +
`src/qortal/get.ts`) before implementing. Record the accepted fields and the
returned shape.

Known traps:

- `GET_USER_ACCOUNT` returns only `{address, publicKey}`.
- `GET_QDN_RESOURCE_URL` first checks status and then builds a URL; it errors
  when the resource is not published.
- `SEARCH_QDN_RESOURCES`/`LIST_QDN_RESOURCES` request params are camelCase and
  are translated to the node's query parameters.
- Response shapes may differ per action. Do not assume a single envelope.

### 4. Centralize a typed wrapper

One service boundary that:

- detects the bridge safely;
- accepts typed action payloads;
- validates error/empty shapes and distinguishes "missing data" from "error";
- applies action-appropriate timeouts and bounded retries only to genuinely
  idempotent public reads; never auto-retries a permissioned
  authentication request or an ambiguous write;
- emits safe diagnostics without secrets;
- tracks explicit states for permissioned authentication (first-time prompt,
  remembered permission, session permission, rejected, unresolved/pending);
- distinguishes public reads, permissioned reads/authentication and writes.

UI calls domain services, not the global.

### 5. Handle identity and names

- Resolve the connected account with `GET_USER_ACCOUNT`.
- Resolve names separately. Verify that a name's owner matches the account
  before treating the account as that name.
- The app publisher name is `_qdnName`. Do not hardcode it.
- **VERIFIED.** Core sets `_qdnName` from the resource name with spaces
  percent-encoded (`resourceId.replace(" ", "%20")` in
  `ArbitraryDataRenderer`). Decode it before comparing to a name or before
  sending it to `/names/{name}` (which expects the raw, encoded name).
- Ownership can change; resolve per session.
- An account with no registered name cannot publish.

### 6. Protect writes

- Preserve the host approval/signing boundary.
- Do not auto-retry an ambiguous write.
- After a write, verify the exact `(service, name, identifier)` resource rather
  than trusting the publish response.
- Treat `PUBLISH_MULTIPLE_QDN_RESOURCES` as grouped UI approval over independent
  transactions with possible partial success.
- Persist enough local state to let a user avoid duplicate submissions.

### 7. Routing and deep links

- The current official starter builds the router with
  `window._qdnBase` as `basename` and Vite `base: ''` (see
  `qapp-templates/react-default-template`), and current apps (Q-Tube, Subwire,
  Quitter, Q-Mail) use `createBrowserRouter`/`BrowserRouter` this way.
  **VERIFIED.** This is the current pattern.
- `HashRouter` still works and was used by the older reference app, but it is a
  legacy pattern here and is not the current template default.
- Internal app navigation must stay inside the app; do not navigate the iframe
  away from the app.
- `qortal://` links to other Q-Apps/resources are handled by the host:
  `q-apps.js` intercepts clicks and asks the host to open a new tab when the
  target app differs. Use `qortal://{service}/{name}/{identifier}/{path}` and
  let the host handle it.
- **VERIFIED.** `q-apps.js` also intercepts `qortal://` image `src` mutations.

### 8. Web2 / external links

The CSP blocks third-party origins, and navigating the iframe away would leave
the app. External-link behavior is a **project interaction decision**, not a
general Qortal rule. Each project MUST define an explicit external-link policy
in `projects/<project>.md` that is compatible with current host/platform
behavior and security rules:

- internal navigation stays in the app;
- Qortal internal links use `qortal://` and the host mechanism;
- for other `http(s)` links, document a single policy — for example copy to the
  clipboard with visible success/failure feedback, or open through a verified
  host action — rather than navigating the iframe away.

Verify the chosen policy against the current host. Clipboard access inside an
iframe can be restricted; use a supported path with a DOM-selection fallback and
never fail silently.

### 9. Display settings and embedded context

- Read `_qdnTheme`, `_qdnLang` at startup; listen for `THEME_CHANGED` and
  `LANGUAGE_CHANGED` messages from the host.
- A slower initial value MUST NOT overwrite a newer host event.
- Use `_qdnBase` for routing and asset base; never hardcode a path prefix.
- `_qdnContext === 'gateway'` changes URL shapes; do not assume `render`.

### 10. Local development and host validation

**VERIFIED.** Local development uses a **local Qortal node** plus Hub Developer
Mode:

1. run the app dev server (for example Vite on `127.0.0.1:5173`);
2. in Hub, add a dev app with that host/port;
3. Hub calls `POST /developer/proxy/start` with `host:port`;
4. Core's dev proxy forwards to the dev server and injects `q-apps.js` and the
   `_qdn*` variables (context `proxy`);
5. stop with `POST /developer/proxy/stop`.

Constraints: the proxy does not forward POST bodies; its CSP differs from the
production render CSP; and Developer Mode requires the local node, not a remote
one. During proxy context, `_qdnName` and `_qdnIdentifier` and `_qdnBase` are empty
(the proxy instantiates `HTMLParser` with an empty resource id and prefix, and
`_qdnService` is `APP`), so owner/identity logic that depends on `_qdnName` MUST
be exercised in a real published-app context before it is claimed to work.

A verified tunnel may provide node API access; it does not establish Developer
Mode, bridge or published-host compatibility. Follow the environment registry.

### 11. Mail and messaging interop

**VERIFIED.** Core provides distinct `MAIL` (public) and `MAIL_PRIVATE`
(encrypted) services, and separately `MESSAGE`/`MESSAGE_PRIVATE`.
`SEND_CHAT_MESSAGE` sends a Qortal **chat** message; it is not Q-Mail.

**VERIFIED convention (Q-Mail 3.2.1, revision in the standard).** Q-Mail interop
is a convention of the Q-Mail app, not a Core API:

- mail is published under the sender's own name with service `MAIL_PRIVATE`;
- the identifier is app-chosen and encodes the recipient, for example
  `_mail_qortal_qmail_<recipientName>_<recipientAddressLast6>_mail_<id>`;
- content is encrypted to the recipient's public key via
  `PUBLISH_MULTIPLE_QDN_RESOURCES` with `encrypt: true` and `publicKeys`;
- recipients discover mail by searching `MAIL_PRIVATE` with a query of the form
  `qortal_qmail_<name>_<addressLast6>_mail_`;
- the payload is base64-encoded JSON with `subject`, `createdAt`, `version`,
  `attachments`, `textContentV2` and thread references.

Because this is a community-app convention, it MUST be re-verified against the
current Q-Mail release before an app depends on interoperability. If it cannot
be verified, do not claim Q-Mail delivery; use a documented fallback and tell the
user the truth.

## Mandatory rules

- Bridge actions and fields MUST be re-verified before implementation.
- Bridge parser failures MUST NOT silently become valid domain values such as
  zero count, unknown owner, accepted write, or valid empty state.
- Read retries MUST be bounded and MUST apply only to genuinely idempotent
  public reads. Permissioned authentication requests and ambiguous writes MUST
  NOT be automatically retried, and a user rejection MUST NOT be replayed.
- Diagnostics MUST NOT include credentials, secrets, signatures or private
  content.
- No direct unmanaged `window.qortalRequest` calls in UI components.
- Asset and network URLs MUST respect the CSP; do not design around third-party
  origins without verified host support.
- Do not treat the dev proxy context as proof of published-app behavior.

## Validation

- Mock typed success, malformed, empty, rejection and timeout.
- Test no-bridge startup (plain browser/dev server).
- Test first-time authentication approval, remembered permission, session
  permission, user rejection and an unresolved pending request; verify there
  are no duplicate concurrent permission prompts, that an unresolved dialog is
  not failed by a short background-read deadline, and that a rejection is not
  automatically retried.
- Test multiple names and the wrong-name rejection path.
- Test theme/language event races.
- Verify routing with `_qdnBase` present and absent.
- Validate in a real host with a real account for identity/write behavior.

## Completion criteria

- The wrapper matches current verified Core/host behavior.
- UI contains no unmanaged bridge calls.
- Identity and write boundaries are explicit and fail closed.
- Local/no-bridge and real-host scenarios are both accounted for.

## Related files

- [`qdn-publication-discovery-and-scaling.md`](qdn-publication-discovery-and-scaling.md)
- [`qortal-architecture-and-data-integrity.md`](qortal-architecture-and-data-integrity.md)
- [`live-qdn-validation.md`](live-qdn-validation.md)
- [`../docs/architecture/qortal-dapp-development-standard.md`](../docs/architecture/qortal-dapp-development-standard.md)
