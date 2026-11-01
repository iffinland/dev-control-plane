# Implementation — <one main problem>

Use with the control-plane [WORKFLOW.md](../WORKFLOW.md) and the matching
platform pack. One issue has one primary objective and one observable exit
criterion.

## Prerequisites

## Scope

## Out of scope

## Acceptance criteria

## Implementation constraints

Preserve owner changes. Use the smallest coherent change. Do not mix unrelated
refactors, platform changes or release actions into the implementation.

## Required validation layers

List each applicable layer separately: static/automated, local runtime,
read-only node API, real host, exact published resource, adversarial review and
owner acceptance. For any feature that renders untrusted or stored content,
include malicious HTML/URL fixtures, including post-sanitization transformations.

## External-action authorization

State exactly which external actions are authorized (commit, development-branch
push, PR, deploy, QDN write, wallet transaction, protected branch, merge,
destructive operation). Absent authorization, stop before the write.

## Evidence and completion contract

- Skills discovered and freshness result:
- Documentation read:
- Capability harvest result:
- Documentation updates:
- Commit scope:
- Push remote and verified remote SHA:

## Owner/live validation requirement

## Completion and closure rule

Completion evidence must be reported. Issue closure, merge and release require
their own explicit owner authorization.
