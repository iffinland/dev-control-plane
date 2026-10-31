---
name: qortal-legacy-dapp-audit-repair
description: Use when auditing or restoring an older Qortal Q-App / QDN website affected by platform evolution, outdated integrations, stale host contracts or accumulated technical debt - covers inventory, compatibility verification, defect reproduction, prioritized repair, regression testing and release readiness.
---

# Qortal legacy dApp audit and repair

- Platform: `qortal`
- Maturity: `candidate`
- Last checked: `2026-10-31`
- Owner: shared capability library

## Use when

- An existing Qortal `APP` or `WEBSITE` still runs but is suspected of being
  stale against current Core, Hub, GO or QDN behavior.
- An older dApp shows one or more legacy symptoms: blank app, wrong assets,
  missing data, duplicated or missing list rows, broken navigation/back,
  stale chunks, theme/frame defects, silent write failures, or data that no
  longer opens in another build.
- The owner wants a bounded audit, a prioritized repair plan, or a
  release-readiness decision rather than a rewrite.
- You need a repeatable evidence trail that separates confirmed platform drift
  from cosmetic debt and unverified third-party advice.

## Do not use when

- The platform is Qortium. Its Home/Core bridge, QDN and account contracts are
  separate; do not transfer this procedure on API-name similarity. Use the
  Qortium pack and its skills, then validate against current Qortium source and
  runtime.
- The task is a new build with no legacy behavior to preserve. Use
  [`functional-app-bootstrap`](../../shared/app-bootstrap/SKILL.md) instead.
- You need a single narrow capability already covered by a verified Qortal
  skill (for example QDN content CRUD); load that skill first and use this one
  only for the surrounding audit.
- The owner wants an unauthorized bulk rewrite, data migration, mainnet write,
  QDN publication, deployment or release.

## Authoritative evidence

Treat the following as **reference evidence, not platform authority**. Current
Qortal Core/Hub/GO source and observed runtime outrank all of it.

| Source | Revision | Paths / contract proved |
| --- | --- | --- |
| Third-party guide `QORTAL_Q_APP_MASTER_GUIDE_FOR_LLMS.md` | SHA-256 `9a787b5070571c53ec732c2f94b1116c2d6dd50e8c365ab01ad1287ce2482868`; claims pinned to Core 6.1.9 / Hub 3.0.3 / GO 3.0 as of 2026-10-29 | Host/bridge behavior, QDN search and publish semantics, layout, security and release checks. Not independently verified by this control plane. See the [source adoption analysis](../../../platforms/qortal/references/source-adoption-analysis.md). |
| Project prompt `PROMPT-night-1.md` | SHA-256 `2dd0a817612f1954358ca8628953b1929ae8d70ab50da0570dea2912f2f08d60` | Real overnight-maintenance practices and legacy-app failure classes from one Q-Shop+ project. Project-specific product guidance is **not** adopted. |
| Current Qortal Core / Hub / GO source and runtime | Resolve per task through [`ENVIRONMENT.md`](../../../ENVIRONMENT.md) | The only authority for implemented behavior at audit time. |
| Existing verified Qortal skills | Current library index | Where they conflict with the third-party guide, the verified skill plus its recorded runtime evidence wins until re-checked. |

The condensed, operational host checklist is
[`platforms/qortal/references/legacy-app-audit-checklist.md`](../../../platforms/qortal/references/legacy-app-audit-checklist.md).
It is a memory aid, not proof.

## Reusable contract / procedure

Run the phases in order. Do not start with a full rewrite, a dependency upgrade
or a data migration.

### 1. Establish the baseline and freeze the audit boundary

Record:

- exact application repository, branch, HEAD, dirty files and linked worktrees;
- current published app coordinates (`service`, registered name, identifier,
  latest signature) and the release zip/artifact actually served;
- current Core, Hub and GO versions, node/network, and whether the node is
  public;
- the data contract: services, identifier prefixes, JSON shapes, versions,
  encryption, tombstones and any `qapp-core` salt/app identity;
- the money surface: `SEND_COIN`, asset transfers, checkout, fees, order
  encryption and price conversion;
- authorized writes and forbidden actions; default to read-only audit.

Preserve owner changes. Never reset, clean, stash or relocate a dirty checkout
to make the audit easier.

### 2. Inventory before judging

Build a machine-readable inventory of:

- framework/build tooling, lockfile, Node/browser targets and release script;
- every `qortalRequest`/REST call, grouped by read vs write vs money;
- every QDN service/identifier family and its readers/writers;
- every host message, global, URL parameter and storage key;
- external URLs, CDNs, remote fonts/images and inline scripts;
- tests, lint/typecheck/build commands and any runtime harness;
- all user-visible flows and their loading/empty/error states.

Count first-load searches and body fetches. Record the biggest JS chunk and zip
size. The inventory is the evidence base; a defect without an inventory location
is not ready for repair.

### 3. Verify compatibility against current authority

For each boundary, compare the app against current source/runtime rather than
against memory or the guide:

- host detection and the injected `qortalRequest` contract;
- serving context, base path, `APP` vs `WEBSITE` routing and asset paths;
- theme, language, frame height and host message handling;
- search semantics (`mode`, `limit`, `prefix`, exact-name matching, paging);
- fetch/status behavior for data not yet on the node;
- identifier/service limits and data shape/versioning;
- publish, fee, unconfirmed-transaction and timeout behavior;
- encryption/private-service rules;
- navigation, deep links, back handling and share links;
- images/media/avatar loading and size caps;
- public-node refusals and graceful degradation;
- storage isolation and HTML sanitization;
- release packaging and served-build verification.

Produce a compatibility matrix with one of `compatible`, `needs-delta-audit`,
`broken` or `unknown`, plus the exact source/runtime evidence. `unknown` is a
valid and required result when evidence is missing.

### 4. Reproduce defects deterministically

For each confirmed mismatch, record:

- environment (Core/Hub/GO version, node/network, viewport, theme, language,
  account/name state, cache state);
- minimal reproduction steps;
- expected vs observed behavior;
- evidence (request/response, console error, screenshot, node read-back);
- severity and whether the defect can lose data, move money, expose data or
  merely degrade presentation.

Separate platform drift from app debt, product bugs and environment problems.
Do not attribute a defect to the platform until current source/runtime confirms
the contract.

### 5. Prioritize and repair in bounded slices

Rank by: data loss / money / security, then a broken core flow, then platform
incompatibility, then performance/UX/cosmetic. Consider blast radius,
reversibility and the owner's priority.

For each repair:

1. pin current behavior with a test before changing money code or the data
   contract;
2. make the smallest coherent change that preserves the existing service,
   identifier, JSON, encryption and tombstone contracts;
3. prefer additive data changes and new prefixes over destructive rewrites;
4. keep writes explicit and user-triggered; never publish or pay to "repair" a
   read failure automatically;
5. feature-detect uncommon host actions and degrade truthfully when absent;
6. keep each logical change separate and record why any money/data change was
   necessary.

### 6. Regression-test at the required layers

Use the smallest layer that can falsify the change, then run the release matrix
once at the checkpoint:

- unit/integration tests for pure builders, validators, URL/encoding, error
  normalization and first-load request counts;
- mocked host bridge tests for decline, timeout, partial publish, public node
  and unavailable data;
- read-only real-node checks for search/fetch/status and data compatibility;
- Hub Dev Mode and, when applicable, GO testing;
- release matrix: boot, routing/deep link/back, identity, reads, writes, money,
  layout sizes, themes, public node, performance and update recovery;
- data compatibility in both directions: old app reads new data and new app
  reads old data, including tombstones and unknown fields.

### 7. Decide release readiness

Only after the prior phases:

- build the exact release artifact and record its hash;
- verify zip layout (`index.html` at the root), no source maps/precompressed
  files, no CDN references and no absolute `/assets/` paths;
- compare the published metadata file list with the local release file list;
- confirm resource status `READY` and, where possible, that the served bundle
  hash matches the locally built artifact;
- confirm version, changelog, rollback archive and owner-visible release notes;
- record owner-only acceptance and any unexecuted layer;
- obtain separate authorization for publication, deployment or any on-chain
  write. Release readiness is not publication authorization.

### 8. Harvest and hand off

Record exact app SHA, per-layer evidence, missing evidence, owner acceptance,
external-write state and harvested skill changes. If the audit found a reusable
contract not already covered, update this library through
[`capability-harvest`](../../shared/capability-harvest/SKILL.md).

## Freshness and compatibility gate

Before reusing this skill:

1. resolve current Core/Hub/GO source and a node/runtime through the
   [`ENVIRONMENT.md`](../../../ENVIRONMENT.md) freshness gate;
2. compare the app's pinned versions and the guide's version table with what is
   actually running;
3. inspect `q-apps.js` and the Hub action catalogue for changed actions,
   encoding, timeouts, dialog behavior or routing;
4. run the smallest read-only smoke that can falsify the relevant boundary;
5. mark the task `compatible`, `needs-delta-audit` or `stale`.

This skill remains `candidate` until a real legacy Qortal dApp is audited end
to end and its before/after evidence is recorded.

## Validation

- Static: validators, lint, typecheck, build, `git diff --check`.
- Unit/integration: pinned money payloads, data contracts, search URL encoding,
  error normalization, first-load request counts.
- Host: Hub Dev Mode Server/Zip/Directory, plus GO for phone/public-node
  behavior when the app supports it.
- Node: read-only search/fetch/status, resource metadata, served build and
  data-compatibility fixtures.
- Owner: the specific flows and devices only the owner can confirm.

A green build, a mocked test or a local preview never proves embedded host or
published QDN behavior.

## Known failure modes

- Starting with a rewrite or dependency upgrade before the baseline and data
  contract are known.
- Trusting the third-party guide's version-sensitive claims without current
  source/runtime confirmation.
- Treating `unknown` as compatible to make the matrix look complete.
- Auditing only the UI while ignoring QDN data compatibility, money code and
  release artifacts.
- "Fixing" stale data by auto-publishing an empty or default document after a
  failed read.
- Reading `mode=LATEST`, omitting `limit`, or trusting contains-matching as an
  exact lookup.
- Changing a service, identifier prefix, JSON shape or encryption format without
  a dual-read compatibility test.
- Treating a timeout as failure and retrying a payment or publish.
- Assuming a Qortal rule applies to Qortium, or the reverse.
- Reporting release readiness from a build that was never compared with the
  served bytes.

## Non-goals

- A rewrite framework, a mandatory stack, or one universal Qortal app shell.
- Product-specific branding, pricing, catalogue or checkout logic.
- A Qortium audit procedure.
- Authorization to publish, deploy, merge, sign or transact.
- A replacement for current platform source/runtime authority.

## Harvest / maturity update

- Upgrade to `verified-reference` when this procedure has been applied to one
  or more current legacy apps with a complete inventory/compatibility matrix
  and the platform claims were checked against source or runtime.
- Upgrade to `verified-runtime` only after a real audit plus regression and
  release-readiness validation on a legacy app, with evidence stored in the
  canonical report tree.
- Downgrade to `stale` when Core/Hub/GO serving, bridge, search or release
  behavior changes materially.
- Keep project-specific findings in that project's report; do not promote them
  into this skill.
