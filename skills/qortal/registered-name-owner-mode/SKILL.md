---
name: qortal-registered-name-owner-mode
description: Use when a Qortal app must decide automatically whether the current visitor is the owner of the registered name it is served from, using the host-injected context globals and the account/name bridge actions, with a fail-closed decision and no in-app login.
---

# Qortal registered-name owner mode

- Platform: `qortal`
- Maturity: `verified-runtime`
- Last checked: `2026-09-16`
- Owner: shared capability library

## Use when

- A QDN app (usually a `WEBSITE`) needs an automatic owner/visitor decision with
  no in-app login, no owner picker and no hardcoded owner address or name.
- You are reading the host-injected render context (`_qdnName`, `_qdnService`,
  `_qdnContext`) and the injected bridge, and need the verified shape of both.
- You are deciding which host actions are safe to call before the user has
  approved anything.
- You need the verified behaviour of the host while it is **locked**, and the
  verified effect of an **account switch**, so your decision logic does not
  depend on a wrong assumption.

## Do not use when

- The platform is Qortium; the injected context and account APIs differ.
- You need the content publish/CRUD contract (separate skill) or the inline
  owner-editing UI contract (separate skill).
- You want a hardcoded allow-list of owner addresses. That is explicitly not
  this contract and does not survive a name transfer.

## Authoritative evidence

| Source | Revision | Paths / contract proved |
| --- | --- | --- |
| Qortal Web Builders (donor app, real host) | `agent/qwb/phase-4-runtime-fix` @ `741754becb79a131c699f2468fe096fdacd00c19` (accepted Phase 3 build `agent/qwb/phase-3` @ `911b44f3e57c39c46048c950274c89bdd04596f5`) | `src/qortal/bridge.ts` (`detectQortalRequest()`), `src/qortal/context.ts` (`decodeInjectedName()`), `src/qortal/identity.ts` (`determineOwner`, fail-closed outcomes), `src/owner/session.ts` (`assertOwner`, re-verify triggers); tests `tests/qortal-bridge-global.test.ts`, `tests/qortal-context.test.ts`. |
| Qortal Core 6.1.9 (node authority) | `qortal-6.1.9-108bf19`, mainnet, `127.0.0.1:24991` / `:24992`, sync 100% | injected `q-apps.js` shim in the real render frame; `/names/<name>` ownership record. |
| Qortal Hub 3.0.3 (host authority) | Linux/Electron build, 2026-09-16 | `GET_USER_ACCOUNT` / `GET_ACCOUNT_NAMES` permission behaviour, lock and log-out behaviour. |

Real-host runtime evidence (why maturity is `verified-runtime`), 2026-09-16,
target `WEBSITE / Q-Website / default`, expected owner
`QNwV9VV82UUZmMkDZZbEMAKPpCx7otnnsi`:

- **Genuine defect found and fixed on the real host.** The first staging publish
  reported `no-bridge` in the real render frame because (a) the injected
  `qortalRequest` is a **lexical** global — `typeof qortalRequest === 'function'`
  while `globalThis.qortalRequest === undefined` — and (b) `_qdnName` arrives
  **percent-encoded** (`Qortal%20Web%20Builders`). Fixed in `8fd110b` and
  re-validated live. Both facts are host bugs waiting to happen in any app.
- **Automatic recognition.** With the owner account signed in, the app rendered
  `OWNER MODE | Q-Website | WEBSITE · verified by name ownership` within one boot
  with no prompt and no in-app login; after an account switch away and back, a
  fresh boot re-derived the same decision automatically.
- **Non-owner.** A *signed-in but non-owning* account
  (`QRTUysZHKgxrdqsATotaffNVfFrD4KPE2Q`) produced **zero** owner DOM: no
  `data-qwb-owner` nodes, no controls, public content unchanged.
- **Inconclusive input is real.** For that non-owning account
  `GET_ACCOUNT_NAMES` returned an **error** rather than an empty list, so the app
  must treat a name-list failure as non-owner, not as "no names, therefore owner".
- **The host lock is not an account change.** While Hub displayed
  `Qortal Hub is locked`, `GET_USER_ACCOUNT` still resolved to the owner address,
  so owner mode legitimately still held. Do not assume a locked host invalidates
  the decision.
- **An account switch destroys the frame.** Logging out tore down the render
  iframe; the app cannot observe a mid-session account switch in Hub 3.0.3 and
  must therefore re-derive on every boot rather than trust any cached flag.

## Scope classification

- **Verified platform facts** (this revision only): the lexical-global injection,
  the percent-encoded `_qdnName`, the `GET_ACCOUNT_NAMES` error for a name-less
  account, the lock-versus-account distinction.
- **Reusable app-side contract:** derive, don't store; fail closed; re-verify per
  privileged action.
- **Dated revision pin:** revalidate against current Core/Hub before reuse.

## Reusable contract / procedure

**1. Resolve the bridge without assuming a global property.**

```js
const fn = typeof qortalRequest === 'function'
  ? qortalRequest                       // lexical global: do NOT use globalThis
  : (typeof globalThis.qortalRequest === 'function' ? globalThis.qortalRequest : null);
```

`globalThis.qortalRequest` is `undefined` in the real render frame even though the
bare identifier is callable, so a `globalThis`-only feature test reports
`no-bridge` on a real host and passes in local mocks. Test both.

**2. Decode the injected name.** `_qdnName` may be percent-encoded; run it through
`decodeURIComponent` (guarding against malformed input) before comparing.

**3. Decide.**

```text
status = ownerModeBlocked(context)? unavailable
account = GET_USER_ACCOUNT        -> failure => inconclusive
address = account.address         -> empty   => inconclusive
names   = GET_ACCOUNT_NAMES(address) -> failure => inconclusive
status  = names includes normalize(_qdnName) ? owner : visitor
```

Rules that matter:

- compare **case-folded, trimmed**, but never collapse internal whitespace;
- never use `names[0]` — the list is unordered and the owner legitimately owns
  more than one name;
- `inconclusive` is not `visitor`; it is still **not** owner for privileged
  actions;
- `unavailable` (no bridge / non-interactive context / empty publishing name) is
  definitive.

**4. Re-derive, never persist.** No `owner=true`, no `localStorage`, no session
storage. Re-derive at boot, before every privileged action, on visibility regain,
on an explicit user "re-check", and after a route change only while the previous
attempt was inconclusive.

**5. Gate privileged actions.** `assertOwner()` re-runs the decision and returns
true only for `status === 'owner'`. A control that was rendered while the account
owned the name must not act if the account changed.

**6. First interactive call prompts.** `GET_USER_ACCOUNT` / `GET_ACCOUNT_NAMES`
surface a host permission dialog the first time; a `PUBLISH_*` surfaces one every
time. Reads such as `GET_QDN_RESOURCE_STATUS` / `FETCH_QDN_RESOURCE` do not.

## Freshness and compatibility gate

- Pinned to Core `qortal-6.1.9-108bf19` and Qortal Hub 3.0.3.
- Invalidation triggers: a change to the injected globals or their encoding; a
  change to `GET_USER_ACCOUNT` / `GET_ACCOUNT_NAMES` response shape; Hub gaining
  real account switching without tearing down render frames.
- Smallest future compatibility check (bounded): load any deployed app in the real
  render frame and assert `typeof qortalRequest === 'function' &&
  globalThis.qortalRequest === undefined`, then read `_qdnName` and confirm whether
  it is percent-encoded.

## Validation

- Structural: `python3 tools/validate_skills.py` in this repository.
- Runtime (required for `verified-runtime`, executed 2026-09-16): owner boot,
  non-owner boot, owner-after-switch boot, all against a real node and real host,
  plus the negative evidence that a name-list failure yields no owner UI.
- Unit-level (donor): `tests/qortal-bridge-global.test.ts`,
  `tests/qortal-context.test.ts` cover the lexical-global probe and the
  percent-decoding.

## Known failure modes

- Testing only `globalThis.qortalRequest` -> app reports `no-bridge` on a real host
  while local mocks pass.
- Comparing the raw `_qdnName` without percent-decoding -> owner is never
  recognised for names containing spaces.
- Caching the owner decision in `localStorage` -> authority survives a reload and
  contradicts the "no persisted authority" rule.
- Treating a failed `GET_ACCOUNT_NAMES` as an empty name list, or as owner.
- Assuming a locked host means the account changed. In Hub 3.0.3 it does not.
- Assuming the app can observe an account switch. It cannot; the frame is
  destroyed.

## Non-goals

- Not a Qortium contract.
- Not the content publish/CRUD contract and not the owner-editing UI contract.
- Not an authorization server: the host remains the only signer.

## Harvest / maturity update

- Maturity `verified-runtime` on 2026-09-16 from the Qortal Web Builders Phase 4
  owner-runtime run. Report:
  `docs/qwb-qortal-web-builders/implementations/2026-09-16-qwb-phase-4-owner-runtime-validation.md`,
  evidence in
  `docs/qwb-qortal-web-builders/implementations/2026-09-16-qwb-phase-4-runtime-evidence/`
  (preserved Qortal platform source `projects/qortal-dev-workspace`; evidence on
  branch `origin/agent/qwb-qortal-web-builders/phase-4-checkpoint-docs-20260916`).
- Downgrade to `stale` if the injected globals, their encoding or the account
  actions change; the bounded check above re-promotes it.
