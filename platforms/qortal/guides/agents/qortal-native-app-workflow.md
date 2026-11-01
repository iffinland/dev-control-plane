# Qortal-Native Application Workflow

## Purpose

Define how to take a Qortal application from product intent to a verified,
scalable, Qortal-native implementation without importing assumptions from
legacy Qortal, Qortium, or generic web projects.

## Use when

Use when creating a new Qortal Q-App/webportal or when redesigning an existing
app's foundation.

## Do not use when

Do not use this to change an already-approved architecture without an explicit
owner decision, and do not use it to implement unrelated product features.

## Prerequisites

- Owner product intent.
- Target platform confirmed (Qortal QDN Q-App/webportal).
- The matching project context file (create it from
  [`../templates/PROJECT-CONTEXT.md`](../templates/PROJECT-CONTEXT.md)).

## Required inputs

### Product definition

- Purpose, audience, language.
- Primary flows and the owner-visible success criterion.
- Non-goals for the current phase.
- Responsive/target-device requirements.

### Application identity

- Repository and local path.
- Planned stack.
- Publishing name (the registered Qortal name that owns the app).
- Service (`APP` or `WEBSITE`) and identifier.
- Owner-detection requirement.
- Non-goals for the current phase.

## Workflow

### 1. Extract requirements, not legacy runtime

Separate product requirements from whatever runtime a donor implementation used.
Do not assume a donor app's router, state model, identity handling or publishing
patterns are current or optimal.

### 2. Define success before architecture

State the observable outcome and the validation layers that will prove it. A
feature is not done when it builds; it is done when the required host/live
evidence exists.

### 3. Choose the current stack, verified

**VERIFIED** current baseline (2026-09-11): `qapp-core` + the
`qapp-templates/react-default-template` starter (`react-default-template`) via
`create-qortal-app`, with React 19, TypeScript, Vite, `react-router-dom` 7, and
`@mui/material` 7 in the current template. Current apps (Q-Tube, Subwire,
Quitter) follow this shape.

Rules:

- Scaffold with the current starter, then verify the generated files instead of
  assuming the template is current.
- `create-qortal-app` has not been updated since 2025-05-12; verify it still
  resolves the current template and prefer `qapp-core`+template directly if it
  does not.
- Do not start from `Qortal/qortal-ui` or `Qortal/Q-Apps-Utils`; both predate the
  current model (Q-Apps-Utils last pushed 2024-07-17; `qortal-ui` archived).
- Configure the router with `window._qdnBase` as `basename` and Vite `base: ''`.
- Wrap the app in `GlobalProvider` (qapp-core) with the correct `publicSalt` and
  app metadata.

### 4. Design authoritative entities

For each entity, define the resource address `(name, service, identifier)`,
ownership, immutable fields, owner-edit fields, and tombstone behavior. See
[`qortal-architecture-and-data-integrity.md`](qortal-architecture-and-data-integrity.md).

### 5. Design independent operations

Separate likes, comments, tips, shares, moderation and edits into independent
operations with their own actors and identifiers.

### 6. Design discovery and scale from the start

Define how lists, pagination, catalogs/indexes, batching and caches work before
implementing screens. Reject N+1 designs. See
[`qdn-publication-discovery-and-scaling.md`](qdn-publication-discovery-and-scaling.md).

### 7. Design identity and authority truthfully

- Detect the app publisher from `_qdnName`.
- Determine "owner" by current name ownership, resolved fresh.
- Never hardcode the owner name or address.
- State honestly what moderation can and cannot do on an immutable network.
- Plan for owner-side moderation presentation without pretending data was
  deleted.

### 8. Verify host integration

Confirm the exact `qortalRequest` actions, response shapes, approval boundaries,
routing and CSP constraints against current source before implementing. See
[`qortal-qdn-and-bridge.md`](qortal-qdn-and-bridge.md).

### 9. Design the UI shell and performance

- Define the loaded shell, skeletons and progressive content.
- Plan route-level code splitting.
- Plan media lazy loading and avoid unnecessary download.
- Plan repeat-visit caching.
- Define empty/error/retry states.
- Respect `prefers-reduced-motion` for any animation.

### 10. Plan release and provenance

Define the version source, build command, artifact, and the publishing name /
service / identifier that will receive it, plus the provenance record. See
[`app-release-and-provenance.md`](app-release-and-provenance.md).

### 11. Bootstrap and implement

Scaffold, then implement in bounded issues with one objective each.

### 12. Validate

- automated checks;
- dev-proxy runtime (plumbing only);
- real-host rendering with a real account (identity/writes);
- exact published resource (deployment).

### 13. Hand off

Self-audit, remediate, report with the canonical path.

## Mandatory rules

- QDN, identity and authority semantics MUST be verified, not assumed.
- No N+1 discovery in a new design.
- No hardcoded owner identity.
- No claim that data was deleted.
- No unrequested external writes.
- Project-specific values stay in the project file, not in global guides.

## Validation

- Product success criterion mapped to a validation layer.
- Identity/authority negative tests.
- Request-count budget for a page render.
- Host rendering and live-resource verification before completion.

## Completion criteria

- Requirements, identity, entity model and discovery strategy are documented.
- The current stack and router pattern are used and verified.
- Required validation layers are planned and, when reached, recorded.

## Related files

- [`01-TASK-CLASSIFICATION.md`](01-TASK-CLASSIFICATION.md)
- [`qortal-architecture-and-data-integrity.md`](qortal-architecture-and-data-integrity.md)
- [`qortal-qdn-and-bridge.md`](qortal-qdn-and-bridge.md)
- [`qdn-publication-discovery-and-scaling.md`](qdn-publication-discovery-and-scaling.md)
- [`../templates/PROJECT-CONTEXT.md`](../templates/PROJECT-CONTEXT.md)
