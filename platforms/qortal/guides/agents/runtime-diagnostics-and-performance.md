# Runtime Diagnostics and Performance

## Purpose

Diagnose Qortal Q-App runtime problems and improve performance from measured
evidence rather than guesses, without confusing environments.

## Use when

Use for startup problems, slow or blocking operations, incorrect loading
states, memory/media pressure, perceived slowness, or performance work.

## Do not use when

Do not use performance work to change authority, schema or publication behavior.

## Prerequisites

- Exact repository and revision.
- The node, host and context used (`render`, `proxy`, `gateway`).
- The account/name used, if identity is involved.

## Required inputs

- Observed symptom and reproduction.
- Expected behavior.
- Baseline measurement.
- Any request/network evidence available.

## Core rule

State the measured root cause before changing behavior. Do not optimize from a
presumed cause.

## Workflow

### 1. Locate the exact runtime

Record:

- which host renders the app (Hub desktop/web/mobile, hosted Hub, gateway);
- whether it is `render` or `proxy` context;
- the node endpoint and port actually used;
- the app's `_qdnName`/`_qdnService`/`_qdnIdentifier` when relevant;
- the account/name used.

An issue that reproduces only under the dev proxy may not exist in production,
and vice versa (different CSP, no identity vars, no POST forwarding).

### 2. Map the milestones

Measure, in order:

1. app shell / first paint;
2. identity resolution;
3. primary listing (catalog or first search page);
4. per-card metadata/status;
5. media load;
6. engagement data;
7. steady state.

Identify the first milestone that is slow or wrong.

### 3. Count requests, not just time

Record the number and shape of node requests, especially per card. A page that
issues one status/search/engagement query per card is the primary QDN
performance defect. See
[`qdn-publication-discovery-and-scaling.md`](qdn-publication-discovery-and-scaling.md).

### 4. Instrument safely

- Use the app's own diagnostics or the browser devtools.
- Never log credentials, private keys, signatures, or private content.
- Provide a way to inspect state without a console when needed.
- Ignore late/stale responses with cancellation or generation tokens; a stale
  response MUST NOT overwrite newer state.

### 5. Audit duplication and stale work

Look for duplicate fetches, refetches on every render, uncached repeat
navigation, competing caches, and work started for routes that are not visible.
`qapp-core`'s request queues, caches and abort support are the current reference.

### 6. Audit loading-state correctness

Distinguish: not yet started, loading, ready, empty-but-valid, partial,
unavailable/transient, permanently missing, malformed, and error. A loading or
failed state MUST NOT render as a valid empty result.

Resource readiness uses the verified statuses: `PUBLISHED` (not yet downloaded),
`NOT_PUBLISHED`, `DOWNLOADING`, `DOWNLOADED`, `BUILDING`, `READY`,
`MISSING_DATA`, `BUILD_FAILED`, `UNSUPPORTED`, `BLOCKED`
(`ArbitraryResourceStatus.java`). Treat `MISSING_DATA`/`BUILD_FAILED` as
retryable-later, not permanently invalid, unless proven otherwise. Build triggers
(`GET_QDN_RESOURCE_STATUS` with `build: true`) MUST be bounded.

### 7. Measure environments separately

Report dev-proxy, real-host and live-QDN measurements separately. Do not mix
them. **VERIFIED.** The dev proxy's CSP and context differ from production's.

### 8. Verify before and after

Record the same measurements before and after the change, under the same
environment. If the environment changed, say so.

## Performance patterns to evaluate (not assumed budgets)

- route-level code splitting and dynamic imports;
- lazy media loading and avoiding unnecessary video download;
- application shell first, then progressive content;
- batched, paginated discovery;
- catalog/index to avoid repeated scans;
- IndexedDB/local caching with explicit TTLs;
- background refresh with visible staleness;
- route/content prefetching only where it does not waste bandwidth;
- skeletons and partial rendering;
- repeat-visit performance.

Collect a Qortal-relevant baseline from current apps before proposing a budget.

## Mandatory rules

- No behavior change without a stated verified cause.
- No unmeasured performance claims.
- Loading, empty, partial and error states MUST be distinguishable.
- Diagnostics MUST NOT leak secrets.
- Do not conflate environments.

## Validation

- Reproduction with the recorded environment.
- Before/after measurements.
- Request-count comparison for a full page render.
- Cold-visit versus warm-visit comparison.
- Failure-path rendering (unavailable, malformed, missing).

## Completion criteria

- Root cause is stated and evidenced.
- Before/after measurement is recorded per environment.
- Loading-state correctness is verified.
- No secret is exposed.

## Related files

- [`qdn-publication-discovery-and-scaling.md`](qdn-publication-discovery-and-scaling.md)
- [`qortal-qdn-and-bridge.md`](qortal-qdn-and-bridge.md)
- [`live-qdn-validation.md`](live-qdn-validation.md)
- [`../docs/architecture/qortal-dapp-development-standard.md`](../docs/architecture/qortal-dapp-development-standard.md)
