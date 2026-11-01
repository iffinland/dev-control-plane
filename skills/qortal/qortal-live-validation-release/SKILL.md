---
name: qortal-live-validation-release
description: Use when a Qortal acceptance claim depends on live node/QDN state, real-host rendering, published-resource behavior, release provenance or versioned artifact verification.
---

# Qortal Live Validation and Release Provenance

- Platform: `qortal`
- Maturity: `verified-reference`
- Last checked: `2026-11-01`
- Owner: shared capability library

## Use when

Use when acceptance depends on QDN state, identity, discovery, persistence,
overwrite semantics, publication metadata, transactions, names, balances,
real-host rendering, release artifacts or published behavior.

## Do not use when

Do not use live validation to justify unrequested writes, publication,
deployment, moderation or issue closure. Read-only access never authorizes a
write. Do not apply this to Qortium.

## Authoritative evidence

- Qortal Core `ArbitraryResourceStatus.java`, QDN resource APIs and
  `Settings.java` for environment defaults.
- The actual host (Hub/gateway) revision and context.
- Migrated detail:
  [`live-qdn-validation.md`](../../../platforms/qortal/guides/agents/live-qdn-validation.md)
  and
  [`app-release-and-provenance.md`](../../../platforms/qortal/guides/agents/app-release-and-provenance.md).

## Reusable contract / procedure

1. **Record the environment.** Core revision and node endpoint/port, network
   (mainnet/testnet), host and context (`render`/`proxy`/`gateway`), account and
   name, app revision/artifact and `_qdnName`/`_qdnService`/`_qdnIdentifier`.
   A live result without provenance is not evidence. Core defaults (12391
   mainnet, 62391 testnet) are not universal constants.
2. **Report layers separately.** Static/automated, local runtime/browser,
   read-only node API, real-host rendering, exact published resource,
   adversarial review and owner acceptance. One layer never substitutes for
   another.
3. **Prefer read-only evidence.** Read-only investigation does not authorize
   publication, signing, moderation or transactions.
4. **Verify the exact resource.** For a publication claim confirm the requested
   `(service, name, identifier)` exists, has the expected status, decodes to the
   expected schema, has correct metadata and publisher name, and that the served
   content matches the intended update by revision/version/content hash/exact
   relevant payload. Submission, transaction confirmation, availability and
   intended-revision verification are distinct; `READY` alone only proves an
   existing resource is available.
5. **Separate release states.** Implementation complete, automated validation,
   real-host validation, owner acceptance, artifact built, artifact published
   and published behavior verified are independent records. A successful publish
   is not verified published behavior.
6. **Build reproducibly and record provenance.** Use a clean install, full
   verify, production build, root-layout artifact (for `APP`/`WEBSITE`), exclude
   generated/secrets, and record source commit, commands, checksum, version and
   intended address.
7. **Publish only with explicit authorization.** Record publisher name,
   address, status/metadata and verification. Do not create a tag, release,
   artifact, deployment or QDN publication without its own scope authorization.
8. **Be honest about gaps.** Name the missing layer and choose `PASS WITH OWNER
   VALIDATION REQUIRED`, `BLOCKED` or `NOT VERIFIED`; do not substitute mocks,
   source inspection or another context.

## Freshness and compatibility gate

Record the current Core/Hub revisions and the live environment before reuse.
Re-read the status enum and publication/verification APIs. If status semantics,
host rendering or publication behavior changed, update this skill and rerun the
relevant layer. Cached or historical evidence is not a current live check.

## Validation

- Reproducible environment/revision record.
- Exact-resource fetch and content/intended-revision comparison for publication.
- Each applicable layer pass/fail/unavailable, reported separately.
- Artifact file list, root layout, checksum and version synchronization.
- Host rendering with the real bridge/account where identity or writes matter.
- Missing layers named and controlling the final status.
- No secret, wallet data or private infrastructure detail in evidence.

## Known failure modes

- Inferring success from a publish response or a `READY` resource alone.
- Mixing dev-proxy, render and gateway evidence.
- Freezing one node port as a platform constant.
- Claiming "deployed" after only a build.
- Treating read-only access as write authorization.
- Hiding an unavailable live layer or labelling a mock as verified.

## Non-goals

Not a write authorization, deployment instruction, issue-closure authority or
Qortium validation contract. It does not replace owner product/runtime
acceptance.

## Harvest / maturity update

Created 2026-11-01 from the legacy Qortal live-validation and release-provenance
guides. Maturity is `verified-reference`; the recorded environment claims were
not re-executed in this migration. Promote after a current environment is
recorded and the exact-resource and host layers are re-proven.
