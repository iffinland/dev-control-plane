# Task Classification

## Purpose

Classify a request by the question it must answer so architecture, runtime, UI
and release evidence are not confused.

## Use when

Use when a request spans multiple concerns, an issue title is ambiguous, or the
agent must decide which guide and validation level apply.

## Do not use when

Do not use classification to expand scope. A secondary track is loaded only
when technically necessary for the requested outcome.

## Prerequisites

- Owner request or issue.
- Current repository baseline.
- Product/project file when available.

## Required inputs

- User-visible outcome.
- Data, authority or identity affected.
- Runtime host and QDN services affected.
- External writes or release actions requested.
- Acceptance criteria and required live checks.

## Classification questions

### Product or feature work

> What should the application do?

Identify users, minimum flows, owner-visible success criteria, non-goals, and
compatibility requirements. Route new product work to
[`qortal-native-app-workflow.md`](qortal-native-app-workflow.md).

### Architecture, identity and data-integrity work

> Who is authoritative?
> Who may publish or mutate each entity?
> How is authority proven (name ownership, not payload claims)?
> Can unrelated publishers replace state?
> How are operations ordered deterministically?
> How does the design scale?

Route to [`qortal-architecture-and-data-integrity.md`](qortal-architecture-and-data-integrity.md)
and, where relevant,
[`qdn-publication-discovery-and-scaling.md`](qdn-publication-discovery-and-scaling.md).

### Platform integration work

> Which `qortalRequest` action or node endpoint is involved?
> What does the current source actually accept and return?
> Does the host need to approve or sign it?
> Does the CSP or render context constrain it?

Route to [`qortal-qdn-and-bridge.md`](qortal-qdn-and-bridge.md).

### Runtime and performance work

> What does the user experience?
> Which operation blocks progress?
> What are the measured timings and request counts?
> Which state transition is incorrect?

Route to [`runtime-diagnostics-and-performance.md`](runtime-diagnostics-and-performance.md).

### UI and visual work

> What should the user see?
> Does the control work?
> Does the visual result match the intended design?

Use the project UI conventions and select live-validation levels appropriate to
the interaction. A visual task does not automatically authorize architecture,
data, bridge or publication changes.

### Release work

> Is the implementation already validated?
> Is the version correct?
> Is the artifact reproducible and traceable to source?
> Is the published resource the one that was built?

Route to [`app-release-and-provenance.md`](app-release-and-provenance.md).

## Workflow

1. State the primary task class.
2. List secondary classes only when required.
3. Map each acceptance criterion to one class.
4. Identify evidence each class needs.
5. Split technically independent outcomes into separate issues.
6. Choose guides and validation levels from the routing table.

## Mandatory rules

> Passing architecture tests does not prove acceptable runtime UX.

> A visual improvement does not prove data integrity.

> A reproducible artifact does not prove the published app works.

- MUST NOT report one track's evidence as proof of another.
- SHOULD create separate issues for independent architecture, runtime, visual,
  dependency, and release changes.
- A critical owner-reported runtime blocker MUST be tracked explicitly even
  when broader architecture work is underway.

## Validation

Confirm every acceptance criterion has an evidence source: static, automated,
local runtime, node API, real host, or exact published resource.

## Completion criteria

- One primary class is named.
- Secondary and out-of-scope tracks are explicit.
- The selected guides and validation levels match the task.

## Related files

- [`00-SESSION-START.md`](00-SESSION-START.md)
- [`issue-driven-audit-and-refactor.md`](issue-driven-audit-and-refactor.md)
- [`live-qdn-validation.md`](live-qdn-validation.md)
