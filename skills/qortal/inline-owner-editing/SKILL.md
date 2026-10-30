---
name: qortal-inline-owner-editing
description: Use when a published QDN page gives its owner edit-in-place controls - the owner bar, per-entity controls, form drafts that survive rejected or ambiguous host writes, a truthful submitted/verified/rejected/ambiguous vocabulary, and no automatic retry.
---

# Qortal inline owner editing on a published page

- Platform: `qortal`
- Maturity: `verified-runtime`
- Last checked: `2026-09-16`
- Owner: shared capability library

## Use when

- A `WEBSITE` (or `APP`) that is already published should let its owner edit the
  page **in place**, with the edit controls injected into the rendered page for
  the owner only.
- You need the verified UX and state vocabulary for host-gated writes: what to
  show before approval, what may be claimed after, and what must never be claimed.
- You need the verified **draft-survival** and **no-retry** rules that a rejected
  or ambiguous host write must obey.
- You need the verified owner-bar surface contract (status line, last write,
  unsaved drafts, manual re-check).

## Do not use when

- The platform is Qortium.
- You need the owner/visitor decision itself (separate
  `registered-name-owner-mode` skill) or the publish/verify/tombstone mechanics
  (separate `qdn-content-crud` skill).
- The page is not QDN-hosted, or you intend to add a backend/CMS. This contract
  is deliberately host-signed and backend-free.

## Authoritative evidence

| Source | Revision | Paths / contract proved |
| --- | --- | --- |
| Qortal Web Builders (donor app, real host) | `agent/qwb/phase-4-runtime-fix` @ `741754becb79a131c699f2468fe096fdacd00c19` (accepted Phase 3 build `agent/qwb/phase-3` @ `911b44f3e57c39c46048c950274c89bdd04596f5`) | `src/owner/bar.ts`, `src/owner/flows.ts`, `src/owner/session.ts`, `src/owner/drafts.ts`, `src/owner/writes.ts`, `src/owner/forms.ts`. |
| Qortal Hub 3.0.3 (host authority) | Linux/Electron build, 2026-09-16 | approval dialog wording/layout, decline semantics, approval countdown. |
| Qortal Core 6.1.9 | `qortal-6.1.9-108bf19`, mainnet | served read-back used to confirm revisions. |

Real-host runtime evidence (why maturity is `verified-runtime`), 2026-09-16,
staging `WEBSITE / Q-Website / default`, owner
`QNwV9VV82UUZmMkDZZbEMAKPpCx7otnnsi`; all content synthetic:

- **Owner bar.** One boot produced `OWNER MODE | Q-Website | WEBSITE · verified by
  name ownership`, with 17 per-entity controls, 5 add controls, publishing status,
  reload content, check last write and `Re-check owner mode`; genuinely
  reload-surviving (in-page marker gone, `frameNavigated` observed).
- **Visitor/non-owner.** An independent browser with no account, and separately a
  signed-in non-owning account, showed **no** bar and **no** inline controls, with
  identical public content.
- **Write vocabulary.** Success appeared as
  `Submitted to the host (availability: verified)` in the bar and
  `"<title>" was published and verified as revision 7` as a toast; the session
  status list showed
  `Submitted to the host (availability: verified): Published and verified (signature 3D6TqkhSPrgQ…): the node serves revision 7.`
  with `Pending writes: 0.`
- **Declined write (the load-bearing negative).** Declining the host approval on
  an edit produced `Rejected by the host — nothing was published — The request was
  declined, or the host refused it before signing. No change was published.
  Nothing was retried automatically. (User declined request)`, the owner bar
  switched to `last write: Rejected by the host — nothing was published
  (availability: unverified)` plus `1 unsaved draft — not published`, the form
  stayed open with its draft, a `Check status` action appeared, and **exactly one**
  approval dialog was observed with no re-request during 30 s of quiet
  observation. The node revision was unchanged.
- **Host dialog shape.** `Q-APP REQUEST | Do you give this application permission
  to publish to QDN? | service: JSON | identifier: … | name: Q-Website | 60 | … |
  Fee | 0.01000000 QORT | Decline | Accept`. The two controls are plain `div`s
  (`div.MuiBox-root`), not `<button>`; `Decline` sits on the left, `Accept` on the
  right. A countdown (`60`) is shown. Driving them needs a real pointer event -
  JS `.click()` on the app side cannot reach them, and `Input.dispatchMouseEvent`
  does.

## Scope classification

- **Verified app-side contract:** the state vocabulary, draft survival, the
  single-pending-write rule and the manual-recheck rule.
- **Verified host behaviour (dated):** dialog wording, the 60-unit countdown and
  the div-based controls in Hub 3.0.3.
- **Not a Qortium contract.**

## Reusable contract / procedure

**1. Render owner controls only from a derived decision.** Inject them as DOM
nodes (never markup built from content), tag every node (`data-*-owner="controls"
| "add"`), and keep a single bar element with a stable id. Hidden means removed,
not merely invisible.

**2. Gate every write on a fresh re-check.** Before opening a write flow and again
immediately before submitting, re-derive owner mode; refuse with an explicit
reason if it no longer holds, and keep the draft.

**3. One pending write per entity.** Refuse a second write for the same entity
while one is in flight; there is no compare-and-swap on the node, so two publishes
for one entity would race.

**4. Truthful vocabulary.** Keep four distinct states and never collapse them:

| Situation | Wording |
| --- | --- |
| request sent, no result yet | `Submitted to the host` |
| read-back matched | `Published and verified (signature <sig>): the node serves revision <n>` |
| host declined/refused | `Rejected by the host — nothing was published` |
| no confirmation obtainable | ambiguous - availability `unverified` |

Availability is a **separate axis** from outcome: a submitted-but-unconfirmed
write is `unverified`, never `verified`. A submission is not a result.

**5. Drafts survive rejection.** A rejected, failed or ambiguous write keeps the
form open with the user's input intact and explains why. Offer an explicit
`Check status` for a submitted-but-unconfirmed write.

**6. Never retry automatically.** A rejected or ambiguous write is only repeated
by an explicit user action. Show `Pending writes: <n>` so an unresolved write is
visible rather than silently re-sent.

**7. Show unsaved work.** Track drafts and surface `N unsaved draft(s) — not
published` in the bar so a closed/abandoned form is never lost silently.

**8. Manual re-check.** Provide a `Re-check owner mode` action; when the decision
no longer holds it removes the bar **and** the inline controls and explains that
nothing was published. Do not keep a stale bar because the host sends no
account-changed event.

**9. Reload content** re-reads the published state from the node and reports
`Content reloaded from this node.` on success; keep a distinct named diagnostic
for a partial reload.

## Freshness and compatibility gate

- Pinned to Qortal Hub 3.0.3 and Core `qortal-6.1.9-108bf19`.
- Invalidation triggers: a Hub change to the approval dialog wording/countdown or
  to how app requests are surfaced; a Core change to bridge actions; a Hub that
  permits real account switching without destroying render frames (which would
  make trigger 8 reachable mid-session instead of only at boot).
- Smallest future compatibility check (bounded, owner needed): with a form open,
  decline one approval and assert that the app reports a rejection, claims
  nothing, keeps the draft, and issues **exactly one** approval dialog.

## Validation

- Structural: `python3 tools/validate_skills.py` in this repository.
- Runtime (required for `verified-runtime`, executed 2026-09-16): real host, real
  node, synthetic content; owner boot, visitor boot, signed-in non-owner boot, add,
  edit, hard-reload persistence, media replacement, reorder, tombstone, session
  status, content reload and a declined write.
- The declined write must be validated by observation, not by unit test: assert
  one dialog, no retry, unchanged node revision, draft still present.

## Known failure modes

- Claiming `verified` straight after approval, without a read-back match.
- Closing the form on rejection and losing the draft.
- Retrying a rejected/ambiguous write automatically, producing duplicate signed
  transactions.
- Letting two writes for one entity run concurrently on a node with no
  compare-and-swap.
- Leaving a stale owner bar after the owner decision changed.
- Expecting JS `.click()` to drive the host approval dialog; on Hub 3.0.3 only a
  real pointer event works.

## Non-goals

- Not a CMS, backend, database or external service.
- Not the owner/visitor decision and not the QDN write mechanics.
- Not a Qortium contract.

## Harvest / maturity update

- Maturity `verified-runtime` on 2026-09-16 from the Qortal Web Builders Phase 4
  owner-runtime run. Report:
  `docs/qwb-qortal-web-builders/implementations/2026-09-16-qwb-phase-4-owner-runtime-validation.md`,
  evidence in
  `docs/qwb-qortal-web-builders/implementations/2026-09-16-qwb-phase-4-runtime-evidence/`
  (preserved Qortal platform source `projects/qortal-dev-workspace`; evidence on
  branch `origin/agent/qwb-qortal-web-builders/phase-4-checkpoint-docs-20260916`).
- Downgrade to `stale` if the host approval surface or the account-change
  behaviour changes; the bounded decline check above re-promotes it.
