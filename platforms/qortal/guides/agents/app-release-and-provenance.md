# App Release and Provenance

## Purpose

Define the evidence and authorization required to move from
implementation-complete to a published Qortal application, and to keep the
published artifact traceable to its source.

Qortal has no QAVS or equivalent app-versioning standard (that marker belongs to
the Qortium workspace). Qortal app identity is the QDN resource address
`(service, name, identifier)`. **UNKNOWN/OWNER DECISION:** whether a project
wants additional in-app version metadata; record the choice in the project file.

## Use when

Use for release preparation, version synchronization, artifact creation,
publication, and deployment records.

## Do not use when

Do not use release work to bypass unresolved runtime/host/live validation.

## Prerequisites

- Implementation and required migrations complete.
- Required automated and live validation status known.
- Explicit owner authorization for any external write.
- The exact target QDN resource address.

## Required inputs

- Authoritative version source.
- Package/lock/UI version surfaces.
- Target `(service, name, identifier)`.
- Exact source commit and artifact contents.
- License and third-party notices, if required by the project.

## Workflow

### 1. Separate states

Record independently:

- implementation complete;
- automated validation complete;
- real-host validation complete;
- owner acceptance complete;
- artifact created;
- artifact published to QDN;
- published behavior verified.

A successful publish is not the same as verified published behavior.

### 2. Synchronize version authority

Identify one version authority and synchronize package, lockfile, visible UI,
release notes and artifact metadata. Validate that no stale alternative version
remains.

### 3. Build reproducibly

- clean install (`npm ci`);
- run the project's verify steps (for example typecheck, lint, tests);
- run the production build;
- produce the artifact from the built output in the form the host expects
  (a root-content bundle with `index.html` at the root for an `APP`/`WEBSITE`
  resource);
- exclude generated/test/cache/secrets;
- record checksum, source commit, build commands and expected version.

### 4. Record provenance before publishing

Declare: source repository, commit, build commands, artifact path/checksum,
version, and the intended `(service, name, identifier)`.

### 5. Publish only with authority

Publishing is an external write requiring explicit owner authorization. Record:

- who published and the publishing name;
- the exact `(service, name, identifier)`;
- the resulting status and metadata;
- the verification result.

Current Hub accepts `isMultiFileZip` (selecting `uploadType: 'zip'`) for both
single and multi-resource publication, so multi-file ZIP publishing from an app
is source-supported for the inspected revision. Host approval still applies and
the ZIP/root layout must be correct; source support is not proof of a successful
live publication. The host (Hub) publishing UI remains a valid workflow choice.

### 6. Verify the published resource

Confirm the resource exists, has the expected status, and serves the expected
content. Distinguish "published", "downloaded", "ready" (see
`ArbitraryResourceStatus`). A `READY`/available resource is not proof that a
newly submitted update is the served revision: confirm the served content
matches the intended update (for example version, content hash or exact
relevant payload), not merely that a resource exists at the expected address.

### 7. Distinguish candidate and stable

A published build MAY remain a candidate. Stable promotion requires a new,
synchronized build when version/metadata changes, plus re-verification. Stable
status MUST NOT be inferred from a successful upload.

## Mandatory rules

- Release work MUST NOT replace runtime validation.
- A reproducible artifact does not prove published behavior; published behavior
  does not prove stable readiness until required host checks pass.
- MUST NOT create a tag, release, artifact or QDN publication without requested
  scope and authorization.
- MUST NOT commit a release archive merely because it exists.
- Artifact provenance MUST identify source and version.
- Never claim a version was deployed when only a build was verified.

## Validation

- Clean install, full verify and production build.
- Version synchronization check.
- Artifact file list, root layout and checksum.
- Git diff/status and generated-file audit.
- Host rendering and live-resource verification before closure.

## Completion criteria

- Release state and version meaning are explicit.
- Artifact is reproducible and traceable.
- Publication happened only with authorization and is recorded.
- Required host/live checks pass before closure.

## Related files

- [`live-qdn-validation.md`](live-qdn-validation.md)
- [`git-generated-files-and-hygiene.md`](git-generated-files-and-hygiene.md)
- [`final-report-and-owner-handoff.md`](final-report-and-owner-handoff.md)
- [`../docs/architecture/qortal-dapp-development-standard.md`](../docs/architecture/qortal-dapp-development-standard.md)
