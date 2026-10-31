# Legacy Qortal dApp audit and repair checklist

Use with the
[legacy dApp audit and repair skill](../../../skills/qortal/legacy-dapp-audit-repair/SKILL.md)
and the [host compatibility notes](q-app-host-compatibility.md). Record evidence,
not impressions. An unchecked item is not a pass.

## Audit header

```text
Project / app name:
Repository / branch / HEAD:
Working tree state (dirty files, worktrees):
Published coordinates (service/name/identifier/signature):
Release artifact + SHA-256 actually served:
Core version / node / network / public-node state:
Hub version / GO version / device:
Executing agent / evidence date (UTC):
Authorized actions (read-only by default):
```

## 1. Baseline and scope

- [ ] Record the exact repository, branch, HEAD and dirty state.
- [ ] Record the published resource coordinates and latest signature.
- [ ] Identify the release artifact currently served; hash it.
- [ ] Resolve current Core/Hub/GO and node/network; record whether public.
- [ ] Read the app's own `AGENTS.md`/`CLAUDE.md`/README and constraints.
- [ ] List the data contract (services, prefixes, JSON versions, encryption,
      tombstones, `qapp-core` identity if any).
- [ ] List the money surface (payments, assets, checkout, orders, pricing).
- [ ] List forbidden actions and confirm no write/publish/payment is authorized.
- [ ] Preserve dirty owner work; use a separate worktree only if needed.

## 2. Inventory

- [ ] Framework, build tool, lockfile, Node/browser target, release script.
- [ ] Every bridge action and REST endpoint, grouped read/write/money.
- [ ] Every QDN service and identifier family, with readers and writers.
- [ ] Every injected global, URL parameter, host message and storage key.
- [ ] Every external URL, CDN, remote font/image and inline script.
- [ ] Every user flow and its loading/empty/error/not-signed-in/public-node state.
- [ ] Tests, lint/typecheck/build commands and runtime harness.
- [ ] First-load search count, body-fetch count, largest chunk and zip size.
- [ ] Documentation drift: README/version/changelog versus actual behavior.

## 3. Compatibility matrix

For each boundary record `compatible`, `needs-delta-audit`, `broken` or
`unknown`, with the source/runtime evidence. Do not mark `unknown` as pass.

| Boundary | Result | Evidence |
| --- | --- | --- |
| Host detection / outside-host fallback | | |
| Asset base / `APP` vs `WEBSITE` routing | | |
| Router basename / non-ASCII / `+` names | | |
| Theme boot + live `THEME_CHANGED` | | |
| Language / `LANGUAGE_CHANGED` | | |
| Frame height / mobile / keyboard | | |
| `NAVIGATE_TO_PATH` / Back / deep links | | |
| Search (`mode`, `limit`, `prefix`, exact match) | | |
| Encoding of names/identifiers/query values | | |
| Data-not-on-node / status / retry | | |
| Publish / fee / batching / timeout | | |
| Money / assets / order verification | | |
| Encryption / private services | | |
| Storage isolation / sanitization | | |
| Images / media / avatars / size caps | | |
| Public-node refusals / degradation | | |
| Release packaging / served-build match | | |
| Data compatibility old↔new | | |

## 4. Defect reproduction

For each defect record:

```text
ID:
Symptom:
Severity (data/money/security > core flow > compatibility > UX/perf):
Environment:
Minimal steps:
Expected:
Observed:
Evidence (request/response, console, screenshot, node read-back):
Confirmed cause layer (platform drift / app debt / product bug / environment):
Related inventory item:
```

- [ ] Reproduce before fixing.
- [ ] Separate platform drift from app debt.
- [ ] Confirm platform claims against current source/runtime.
- [ ] Check whether the defect affects data compatibility or money.
- [ ] Check whether a "fix" could auto-publish, overwrite or double-pay.

## 5. Prioritized repair queue

- [ ] Rank by data loss/money/security first, then core-flow breakage,
      compatibility, performance/UX/cosmetic.
- [ ] Record blast radius, reversibility and dependencies.
- [ ] Pin current money/data behavior with tests before changing it.
- [ ] Prefer the smallest coherent patch.
- [ ] Keep services, identifiers, JSON shapes, encryption and tombstones
      backward compatible; use additive fields/new prefixes.
- [ ] Keep writes explicit; never auto-repair data on read failure.
- [ ] One logical change per commit, with the reason for any money/data change.

## 6. Regression matrix

- [ ] Unit: payload builders, validators, identifier parsing, URL encoding,
      error normalization, first-load request counts.
- [ ] Integration: mocked decline, timeout, partial publish, public node,
      unavailable data, tombstone, malformed body.
- [ ] Real node (read-only): search, fetch, status, metadata, data fixtures.
- [ ] Hub Dev Mode: Server and/or Zip; reload at the documented root.
- [ ] GO when applicable: keyboard, landscape, Android Back, public node.
- [ ] Layout sizes: 360×740, 390×844, 844×390, ~700, 1280+.
- [ ] Themes: light/dark, contrast, user content readability.
- [ ] Identity: sign-in, decline, timeout, account switch, no name, many names.
- [ ] Routing: deep link, reload, host Back, in-app Back then Android Back,
      copy-link round trip.
- [ ] Writes: fee shown, decline quiet, timeout verified, batching, optimistic
      item merged from search.
- [ ] Money: validation, decline, timeout lookup, no double charge.
- [ ] Update recovery: open tab across a republish.
- [ ] Data compatibility: old app reads new data and new app reads old data.
- [ ] Performance: re-count first-load searches/fetches, largest chunk, zip.

## 7. Release readiness

- [ ] Build the exact release artifact; record SHA-256.
- [ ] Zip has `index.html` at the root; no `node_modules`, maps, `.gz`/`.br`.
- [ ] No absolute `/assets/`, CDN or remote-font references in the build.
- [ ] Published metadata `files` list matches the local release file list.
- [ ] Resource status is `READY`; served bundle hash matches the artifact.
- [ ] Version, changelog and About/version display agree.
- [ ] Rollback artifact retained.
- [ ] Owner-only acceptance steps listed.
- [ ] Separate authorization obtained for any publish/deploy/transaction.
- [ ] Report saved in the canonical project/category tree with exact app SHA.

## 8. Handoff fields

```text
Result: compatible / needs-delta-audit / stale
Fixes completed (with commit SHAs):
Fixes deferred and why:
Unverified claims still open:
Owner acceptance required:
External writes performed (should normally be none):
Report path + SHA-256:
Skill harvest result:
```
