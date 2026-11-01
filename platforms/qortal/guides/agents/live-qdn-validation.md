# Live QDN and Host Validation

## Purpose

Define how to obtain honest, reproducible live evidence for QDN state, identity,
publication, discovery and host rendering.

## Use when

Use when acceptance depends on QDN state, metadata, identity, discovery,
persistence, overwrite semantics, publication metadata, transactions, names,
wallets or balances, or on real-host rendering.

## Do not use when

Do not use live validation to justify unrequested writes, publication,
moderation or deployment.

## Prerequisites

- Implementation complete for the claim under test.
- The exact revision/artifact under test.
- Access to the intended node and host.

## Required inputs

- The claim to be validated.
- The exact resource(s): `(service, name, identifier)`.
- The node/endpoint and environment.
- The host context expected (`render`, `proxy`, `gateway`).
- The account/name to use.

## Validation levels

Report each separately:

1. static and automated checks;
2. local runtime/browser;
3. read-only node API evidence;
4. real-host rendering with the real bridge and account;
5. exact published QDN resource behavior;
6. adversarial review;
7. owner acceptance.

## Workflow

### 1. Record the environment

- Qortal Core revision and node URL/port;
- host and host version/context;
- network (mainnet/testnet) — **VERIFIED** default ports 12391/62391;
- account address and name used;
- app revision/artifact and its `_qdnName`, `_qdnService`, `_qdnIdentifier`.

A live result without provenance is not evidence.

### 2. Prefer read-only evidence first

Use the node API read paths and `qortalRequest` reads. Read-only investigation
does not authorize publication, signing, moderation, transactions or deployment.

### 3. Verify exact resources

For a publication claim, fetch the exact resource and confirm:

- the requested `(service, name, identifier)` exists;
- status is the expected value;
- content decodes and matches the expected schema;
- the served content matches the intended update using an appropriate
  revision/version/content-hash/exact-relevant-payload check, not merely a
  prior version that shares the same address;
- metadata (title/description/category/tags) is correct;
- the publisher name is the expected name.

Never infer success from a publish response alone. Submission, transaction
confirmation (where applicable), resource availability/status and
intended-revision verification are separate; a `READY` resource does not prove
that a newly submitted update is the version currently served.

### 4. Verify across contexts

- `render` — the published app in a real host;
- `proxy` — local dev; proves plumbing, not production behavior;
- `gateway` — URL shapes and auth-bypass behavior differ.

State which context each claim came from.

### 5. Be honest about gaps

If a required live layer is unavailable:

- report the missing layer by name;
- choose the truthful status (`PASS WITH OWNER VALIDATION REQUIRED`, `BLOCKED`,
  or `NOT VERIFIED`);
- do not substitute mocks, source inspection or a different context for the
  missing layer.

### 6. Bounded write tests

When a live write is explicitly authorized, prefer one controlled test with
recorded identifiers and results over repeated speculative attempts. Do not leave
orphan resources. Treat ambiguous writes as recoverable, not safely repeatable.

## Mandatory rules

- Use verified node access, including an available configured tunnel when
  relevant; tunnel health does not replace real-host evidence.
- No fixed endpoint claim without recording the environment; ports are
  configurable.
- No unproven live claim, and no "verified" label for a mock or local-only run.
- Read-only access MUST NOT be used as authorization for writes.
- Live writes MUST be explicitly authorized and bounded.

## Validation

- The claim is reproducible from the recorded environment and revision.
- Exact resource verification is included for publication claims.
- Missing layers are named.
- No secret appears in the report.

## Completion criteria

- Environment and revision are recorded.
- Each applicable layer is pass/fail/unavailable, explicitly.
- Remaining owner/host validation is named and controls the status.

## Related files

- [`qortal-qdn-and-bridge.md`](qortal-qdn-and-bridge.md)
- [`runtime-diagnostics-and-performance.md`](runtime-diagnostics-and-performance.md)
- [`final-report-and-owner-handoff.md`](final-report-and-owner-handoff.md)
- [`../docs/architecture/qortal-dapp-development-standard.md`](../docs/architecture/qortal-dapp-development-standard.md)
