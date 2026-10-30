---
name: qortal-private-chat-contact-form
description: Implement or review a Qortal Q-App Contact form that resolves a current registered-name owner and sends one direct private-chat message through the current host bridge.
---

# Qortal private-chat Contact form

- Platform: `qortal`
- Maturity: `verified-runtime`
- Last checked: `2026-09-15`
- Owner: shared capability library

## Use when

- A Qortal Q-App needs a simple direct private-chat Contact flow to the current owner of its registered publishing name.
- A Q-App needs truthful submission/ambiguity UX around `SEND_CHAT_MESSAGE` without inventing a delivery receipt.

## Do not use when

- The requirement is Q-Mail, public/group chat, attachments, durable inbox storage, or an arbitrary address picker.
- The target is Qortium or any non-Qortal bridge.

## Authoritative evidence

| Source | Revision | Paths / contract proved |
| --- | --- | --- |
| Qortal Core | `108bf191` | `src/main/resources/q-apps/q-apps.js`, `Q-Apps.md`, `blockchain.json`, CHAT transaction/API code: host routing, 60 s timeout, read-back, non-confirmability, retention and data limit. |
| Qortal Hub | `12a573b2` | `src/qortal/get.ts` (`sendChatMessage` / `signChatFunc`): approval, public-key resolution, encryption, signing and relay. |
| qapp-core | `0f9d6ac` | `src/types/qortalRequests/interfaces.ts`: bridge request vocabulary. |
| Shadow Archives Contact | owner validation, 2026-09-15 | Real-host owner PASS: current-name recipient, approved send, owner-side arrival once, no duplicate, clean reload. |

The source/read-only evidence is in the Shadow Archives 2026-09-14 Contact reports under
`projects/qortal-dev-workspace/docs/shadow-archives-webportal/`; verify the preserved Qortal
evidence branch before citing. The owner result is recorded in its 2026-09-15 phase-closure
checkpoint. It is evidence for this Qortal contract, not a reusable UI.

## Reusable contract / procedure

1. Resolve the app's injected publishing name and look up its **current** registered-name owner immediately before send. Do not hardcode an address; fail closed if the owner cannot be resolved or cannot receive encrypted chat.
2. Send the bridge envelope exactly as `{ action: 'SEND_CHAT_MESSAGE', destinationAddress, message }`. The payload fields supplied by the app are `destinationAddress` and bare text `message`; do not provide a public key, subject, `groupId`, message id, or encryption flag.
3. Treat send as host-mediated. Current Core routes it to the UI handler and the Hub resolves the recipient public key, encrypts a direct message, requests approval when needed, signs, and relays. Relevant preconditions include an unlocked capable host, approval (unless previously granted), recipient on-chain public key, Hub's current minimum balance gate, and node pending-chat limits.
4. Read the response as submission data, currently including `signature` and sender `creatorAddress`. `creatorAddress`, not `sender`, identifies the sender. A signature/submission is not delivery or read proof: `ChatTransaction.isConfirmable()` is false and CHAT never block-confirms.
5. If a node-local read-back is useful, call `SEARCH_CHAT_MESSAGES` with exactly two valid `involving` addresses. It returns an array from the node's validated-chat store; absence or presence is node-local and not owner-read proof.
6. Enforce the current encrypted cap: `ChatTransaction.MAX_DATA_SIZE = 4000` bytes. The current secretbox envelope budget is 3984 bytes after its 16-byte authenticator. Keep a conservative product body limit and validate before requesting approval.
7. Model outcomes truthfully: acknowledged submission/read-back present = sent; acknowledged submission/read-back absent = submitted but unconfirmed; 60 s timeout = ambiguous; declined approval = rejected; pre-sign/host/node failures = failed. Preserve drafts except after the accepted product's explicitly acknowledged-submission policy.
8. A send is non-idempotent. Disable repeat submission while in flight, never automatically retry an ambiguous result, and make any user-initiated retry visibly warn about duplicate risk.
9. Explain limited retention without overpromising: Core `108bf191` chain config currently sets normal CHAT expiry to approximately 24 hours. Reticulum DM's approximately one-month store is separate Hub transport and is unavailable through the verified Q-App bridge. Do not silently fall back to Q-Mail, public/group chat, or QDN; a durable-contact Q-Mail recommendation may be UI copy only.

## Freshness and compatibility gate

Before reuse, record current revisions and inspect the delta for:

1. Core `q-apps.js` action handling/default routing and `SEND_CHAT_MESSAGE` timeout; `Q-Apps.md`; `blockchain.json`; Chat transaction, chat repository, and `/chat/messages` API behavior.
2. Hub `sendChatMessage` / `signChatFunc`, permission UI, recipient public-key lookup, encryption, and response marshaling.
3. qapp-core request interfaces and any target host/extension implementation.
4. Any change to current name-ownership lookup, recipient encryption preconditions, 4000-byte limit, transaction expiry config, response `creatorAddress`/signature fields, or exactly-two-address search validation.

Run a bounded source delta check plus read-only node probe. Mark `needs-delta-audit` on any relevant change, and do not carry forward the approximately 24-hour value without checking the active chain config. A target host send still needs target-owner runtime validation.

## Validation

- Unit-test request shape, recipient re-resolution, byte-budget rejection, result classification, draft preservation, and in-flight duplicate guard.
- Build/type/lint/format and verify chat transport remains constrained to the intended lazy/feature boundary where that is an app requirement.
- Read-only: confirm target Core revision, current registered-name owner/public key, and `SEARCH_CHAT_MESSAGES` rejects fewer than two/invald addresses and returns an array for two valid addresses.
- Real host: verify approval, one send, owner-side arrival exactly once, truthful result wording, and clean reload. Do not use a repeated send to resolve ambiguity.

## Known failure modes

- A 60 s bridge timeout may happen after approval/relay: classify as ambiguous, preserve the draft, and never auto-retry.
- A returned signature does not prove delivery; CHAT cannot enter a block.
- Read-back can lag or be pruned/node-local; do not call it recipient receipt.
- The recipient may lack an on-chain public key, the account may fail balance/pending-chat preconditions, or a non-host/gateway context may lack the required bridge.
- `recentChatMessagesMaxAge` is a pending-message rate-limit window, not normal private-chat retention.

## Non-goals

- Q-Mail implementation or interoperability.
- Public/group chat, attachments, delivery/read receipts, durable message storage, automatic retries, or Qortium support.
- Shadow Archives naming, branding, page layout, or hardcoded recipient identity.

## Harvest / maturity update

This is `verified-runtime` because Core/Hub/qapp-core source, read-only node checks, automated feature checks, and owner real-host delivery evidence all exist at the dated revisions above. Downgrade to `stale` when any freshness trigger changes the contract or a target real-host validation contradicts it. Upgrade or renew only with current source delta evidence and a real-host send/arrival/no-duplicate observation; never use unit tests or a signature alone as delivery proof.
