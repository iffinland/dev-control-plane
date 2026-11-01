---
name: qortal-runtime-diagnostics
description: Use when a Qortal Q-App is slow, stuck, loading incorrectly or behaving differently across dev-proxy, real-host and published-QDN environments, and the cause must be measured before changing behavior.
---

# Qortal Runtime Diagnostics and Performance

- Platform: `qortal`
- Maturity: `verified-reference`
- Last checked: `2026-11-01`
- Owner: shared capability library

## Use when

Use for startup problems, slow or blocking operations, incorrect loading or
empty states, media/memory pressure, perceived slowness, stale responses or
performance work in a Qortal Q-App.

## Do not use when

Do not use performance work to change authority, schema, publication behavior or
product scope. Do not optimize from a presumed cause or apply this to Qortium.

## Authoritative evidence

- The app's exact revision and runtime context.
- Qortal Core status/source and the actual host revision.
- Migrated detail:
  [`runtime-diagnostics-and-performance.md`](../../../platforms/qortal/guides/agents/runtime-diagnostics-and-performance.md).

## Reusable contract / procedure

1. **Locate the exact runtime.** Record host (desktop/web/mobile Hub, hosted Hub,
   gateway), context (`render`/`proxy`/`gateway`), node endpoint/port, app
   `_qdn*` values and the account/name. A proxy-only issue may not reproduce in
   production and vice versa (different CSP, empty identity variables, no POST
   forwarding).
2. **Map milestones.** Measure app shell/first paint, identity, primary listing,
   per-card metadata/status, media, engagement and steady state. Identify the
   first slow or wrong milestone.
3. **Count requests, not just time.** Per-card status/search/engagement queries
   are the primary QDN performance defect. Compare with the discovery/scaling
   guidance and measure a full page render.
4. **Instrument safely.** Use app diagnostics or browser devtools; never log
   credentials, keys, signatures or private content. Cancel or generation-tag
   stale responses so they cannot overwrite newer state.
5. **Audit loading correctness.** Distinguish not-started, loading, ready,
   empty-but-valid, partial, transiently unavailable, permanently missing,
   malformed and error. A loading or failed state must not render as valid empty.
6. **Use current statuses.** QDN readiness can include `PUBLISHED`,
   `NOT_PUBLISHED`, `DOWNLOADING`, `DOWNLOADED`, `BUILDING`, `READY`,
   `MISSING_DATA`, `BUILD_FAILED`, `UNSUPPORTED` and `BLOCKED`. Treat
   `MISSING_DATA`/`BUILD_FAILED` as retryable-later unless proven otherwise and
   bound any build trigger.
7. **Measure before and after.** Use the same environment and record the
   comparison. If the environment changed, say so and do not compare across it.
8. **Evaluate patterns, not invented budgets.** Route-level splitting, lazy
   media, shell-first rendering, batched/paginated discovery, indexes, explicit
   caches, background refresh with staleness, skeletons and cold/warm visits.
   Collect a baseline from current apps before proposing a budget.

## Freshness and compatibility gate

Record the current Core/Hub/framework revision and the exact runtime context.
Re-read the status enum and any queue/cache behavior you rely on. If the host,
CSP, dev proxy or `qapp-core` changed, re-measure. A prior measurement is
historical evidence, not a current baseline.

## Validation

- Reproduction with the recorded environment.
- Before/after measurements under the same environment.
- Request-count comparison for a full page render.
- Cold-visit versus warm-visit comparison.
- Failure-path rendering: unavailable, malformed, missing, partial and error.
- Stale-response race test.
- No secret or private content in diagnostics.

## Known failure modes

- Changing behavior without a measured root cause.
- Conflating dev-proxy, render and gateway evidence.
- Reporting time without request counts.
- Rendering loading/error as valid empty.
- Letting a late response overwrite newer state.
- Unbounded status polling or build triggers.
- Inventing performance budgets instead of measuring current apps.

## Non-goals

Not a discovery redesign, authority fix, release gate or Qortium contract. It
does not authorize publication, deployment or production writes.

## Harvest / maturity update

Created 2026-11-01 from the legacy Qortal runtime-diagnostics guide. Maturity is
`verified-reference`; no fresh live measurement matrix was run in this
migration. Promote after recording current-app baselines and before/after
measurements in a real host.
