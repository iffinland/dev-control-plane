---
name: qortal-host-bridge-contract
description: Use when a Qortal Q-App must detect qortalRequest, classify read/authentication/write actions, handle host approval, routing, CSP or local Developer Mode without inventing platform behavior.
---

# Qortal Host and Bridge Contract

- Platform: `qortal`
- Maturity: `verified-reference`
- Last checked: `2026-11-01`
- Owner: shared capability library

## Use when

Use for `qortalRequest` detection, `GET_USER_ACCOUNT`/name resolution, host
approval flows, QDN reads/writes, routing and deep links, CSP-constrained assets,
theme/language events, or local Hub Developer Mode.

## Do not use when

Do not use this skill to define business authority, discovery scaling or release
policy. It is not a Qortium bridge contract. Do not infer a bridge action from a
node API endpoint without reading current Core `q-apps.js` and host source.

## Authoritative evidence

- Qortal Core `src/main/resources/q-apps/q-apps.js` and the Core source revision
  under test.
- Qortal Hub `src/qortal/qortal-requests.ts` and `src/qortal/get.ts` for host
  mediation and permission behavior.
- Qortal Core `HTMLParser`, `ArbitraryDataRenderer`, `Settings` and
  `Security.requirePriorAuthorization`.
- Migrated detail:
  [`qortal-qdn-and-bridge.md`](../../../platforms/qortal/guides/agents/qortal-qdn-and-bridge.md)
  and the
  [`Qortal dApp Development Standard`](../../../platforms/qortal/guides/docs/architecture/qortal-dapp-development-standard.md).

## Reusable contract / procedure

1. **Detect safely.** Use a `typeof` guard on `window.qortalRequest` /
   `globalThis.qortalRequest`; never probe `window.parent` or `window.top` as a
   verified mechanism. Expose one typed wrapper and explicit states:
   unavailable, ready, malformed, timeout, rejected, error.
2. **Classify by approval boundary, not "read vs write".**
   - Public/idempotent node reads: `SEARCH_QDN_RESOURCES`, `FETCH_QDN_RESOURCE`,
     `GET_QDN_RESOURCE_STATUS/URL`, `GET_NAME_DATA`, `GET_ACCOUNT_NAMES`, block
     and transaction reads. Bounded retry is allowed for these only.
   - Permissioned host-mediated reads/authentication: `GET_USER_ACCOUNT` and
     `GET_PRIMARY_NAME`. The host may use saved/session permission or an
     approval dialog. Distinguish first-time, remembered, session, rejected and
     unresolved states; deduplicate concurrent callers; never auto-retry a
     rejection and never apply a short read deadline to an unresolved dialog.
   - Signed writes: `PUBLISH_QDN_RESOURCE`, `PUBLISH_MULTIPLE_QDN_RESOURCES`,
     `SEND_CHAT_MESSAGE`, name operations and transactions. Host approval and
     signing apply; ambiguous writes are not automatically retryable.
3. **Verify the exact action contract.** Read Core `q-apps.js` plus the host
   handler before implementing. `GET_USER_ACCOUNT` returns only
   `{address, publicKey}`; a name is separate. `SEARCH_QDN_RESOURCES` uses
   camelCase bridge fields, not the lowercase node query names.
4. **Identity.** The app publisher name is `_qdnName` (percent-encoded by Core;
   decode before comparison). Resolve current name ownership per session; never
   hardcode an owner name or address and never trust payload `author` fields.
5. **Routing.** Use `window._qdnBase` as router `basename` and Vite `base: ''`.
   Keep navigation inside the iframe and let the host handle `qortal://` links.
6. **CSP.** The production render CSP allows `self`, inline/eval, local media
   and `data:`/`blob:` images; third-party origins and HTTPS APIs are not
   generally available. Design media and network paths to fit it.
7. **Developer Mode.** Hub uses a local node and `POST /developer/proxy/start`.
   The proxy context has empty `_qdnName`/`_qdnIdentifier`, a different CSP and
   does not forward POST bodies. Never treat proxy behavior as proof of
   published-app behavior.

## Freshness and compatibility gate

Before reuse, record the current Core and Hub revisions and re-read the exact
action handler. Compare the observed `qortalRequest` fields and response shape
with this skill. If `q-apps.js` or the host dispatch changed, demote or update
this skill rather than assuming the contract still holds. Verify current CSP and
`_qdn*` injection in Core source. A stale or absent revision blocks dependent
claims.

## Validation

- No-bridge startup in a plain browser/dev server must not crash.
- Typed wrapper tests for success, malformed/empty, timeout, rejection and
  permission dialog states.
- Concurrent authentication calls share one in-flight request; no duplicate
  prompts.
- Multiple names and wrong-name rejection.
- Theme/language event races do not let an older value overwrite a newer event.
- Real-host test with a real account for identity, approval and write behavior.
- Proxy and render contexts are reported separately.

## Known failure modes

- Calling the raw global from UI components or letting parser failure become a
  valid empty/zero/accepted state.
- Treating `GET_USER_ACCOUNT` as an approval-free read, timing out the dialog
  and retrying into a prompt loop.
- Retrying an ambiguous publish or claiming a `READY` resource proves a new
  revision is served.
- Hardcoding the owner name, not decoding `_qdnName`, or navigating the iframe
  away for external links.
- Using the dev proxy's CSP or empty identity variables to justify production
  behavior.

## Non-goals

Not a business-authority model, discovery budget, release process or Qortium
contract. It does not authorize writes, publication, signing or transactions.

## Harvest / maturity update

Created 2026-11-01 from the legacy `qortal-dev-workspace` QDN/bridge and
development-standard guides at
`b8fd2f6fbfcff88c0ab9bc8fd116d5548679d2d2`. Maturity is `verified-reference`:
the source claims were source-linked at that revision but not re-run against a
current live host in this migration. Promote only after a fresh Core/Hub
freshness check and recorded host evidence.
