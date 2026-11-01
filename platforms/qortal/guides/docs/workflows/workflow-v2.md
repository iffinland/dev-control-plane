# Qortal Development Workflow v2

## Purpose

Define the canonical operating contract for AI-assisted Qortal development.
This document controls task shape, evidence, execution, validation, challenge,
completion and synchronization. Domain guides define how the contract applies
to architecture, QDN, bridge, runtime, release and maintenance work.

## Use when

Use for every substantial Qortal task after entering through
[`../../agents/00-SESSION-START.md`](../../agents/00-SESSION-START.md) and
classifying the request.

## Core contract

### 1. Compact prompt, referenced context

A task prompt supplies the task-specific delta, not a copy of the governance
repository. It SHOULD contain only:

- one objective and observable exit criterion;
- exact repository and matching project context;
- concrete scope and non-goals;
- task-specific invariants or unusual constraints;
- required evidence and owner-visible acceptance condition;
- explicit authority for commit, push, publish, deploy, release, live writes,
  issue mutation, or destructive action.

The prompt references shared standards, routed guides and project context.
Agents MUST read those sources rather than expecting generic rules to be
repeated in every prompt.

### 2. One objective at a time

One task/controller has one primary outcome and one exit criterion. Routine
implementation SHOULD normally map to one issue.

Multiple findings MAY share one controller only when they are tightly related,
share the same architecture or domain context, require the same acceptance
evidence, and must be regression-tested together. Unrelated architecture,
runtime, visual, dependency, release or cleanup outcomes remain separate tasks.
This prevents both unbounded "fix everything" prompts and wasteful
micro-prompting.

### 3. Evidence before implementation

Use this sequence:

```text
owner outcome or observed symptom
-> repository and working-tree baseline
-> current authoritative source and project context
-> real flow trace
-> first confirmed mismatch or approved design boundary
-> smallest coherent change
-> required validation layers
-> adversarial self-audit
-> remediation of confirmed in-scope BLOCKER/HIGH findings
-> truthful handoff
```

Do not code from a presumed root cause when source or runtime evidence can
distinguish competing explanations. Later stages that were not reached remain
`NOT VERIFIED`.

### 4. Evidence-based disagreement

Agents MUST NOT agree by default. When a requested method conflicts with current
source, measured runtime evidence, approved architecture, safety, data
integrity, or a materially better technical path, the agent MUST:

1. state the relevant verified evidence;
2. explain the consequence of the requested method;
3. recommend the better bounded alternative;
4. identify any genuine owner decision still required.

Disagreement does not authorize scope expansion, destructive action, or external
mutation. The owner retains product and authorization decisions.

### 5. Validation layers are not interchangeable

Plan and report each applicable layer separately:

1. static and automated checks;
2. local runtime or browser interaction;
3. read-only node API evidence;
4. the app rendered in a real Qortal host with the real bridge and account;
5. exact published QDN resource behavior (live network);
6. adversarial agent review;
7. owner product/runtime acceptance.

Typecheck, lint, unit tests, mocked or synthetic bridge tests, local Vite
preview, build success and agent self-report do not prove host or live QDN
compatibility.

### 6. Read-only live and host evidence is required when applicable

When acceptance depends on QDN state, metadata, identity, discovery,
persistence, overwrite semantics, publication metadata, transactions,
references, names, wallets or balances, the agent MUST use an available
read-only Qortal node endpoint and MUST record which node and environment was
used.

The endpoint is environment-specific. Core's defaults are port **12391**
(mainnet) and **62391** (testnet) (`Settings.java`), and a host may select or
override a node. Agents MUST determine the intended environment, verify actual
reachability, and record the node used. Do not freeze one port as a platform
constant.

Use a real host (Qortal Hub, hosted Hub, or a gateway node) when bridge
injection, selected account, approval, routing, display settings or
owner-visible behavior is material. Use the exact published QDN resource when
deployment behavior is claimed.

Verified tunnels may provide read-only node evidence under the universal
environment registry. Use the relevant available access path and record it.
A tunnel does not replace real-host/bridge validation or authorize SSH changes.

If required live evidence is unavailable, report the missing level and select
the truthful non-completion status. Do not silently downgrade to mocks or source
inspection.

Read-only investigation does not authorize publication, signing, moderation,
transactions, deployment or other live writes.

### 7. Local canonical authority and GitHub mirror

The current local working tree is authoritative for active editing. The
approved committed revision is the shared standard. GitHub mirrors the approved
revision. Do not treat a stale local copy as current when the remote has moved;
re-verify revisions before platform-dependent work.

## Task workflow

### Start

Establish the Git baseline, read the project context, classify the task, and
define scope, out-of-scope work, acceptance criteria, validation and stop
conditions.

### Investigate or design

Trace the real path from the observed symptom or requirement. Identify the first
confirmed mismatch or the approved design boundary. Distinguish verified fact,
inference, unknown and owner decision.

### Implement

Make the smallest coherent change that satisfies the objective. Do not expand
scope. Keep project-specific facts in the project, not in global guides.

### Validate

Run the applicable layers from §5, plus the project's declared commands. Record
what was run, the environment, and the outcome. Record what was not run.

### Handoff

Perform the adversarial self-audit, remediate confirmed in-scope BLOCKER/HIGH
findings, then produce the report per
[`report-storage-policy.md`](report-storage-policy.md) and state the exact
absolute report path.

## Stop conditions

Stop and report instead of guessing when:

- required live/host evidence is unavailable and the claim depends on it;
- a platform contract is unverified and the design depends on it;
- the change would exceed the authorized scope or require an external write;
- the same task has failed twice without a new, evidence-backed hypothesis;
- data integrity or authority semantics cannot be established safely.

## Compact controller shape

Use [`../../templates/TASK-CONTROLLER.md`](../../templates/TASK-CONTROLLER.md).
Include only the task-specific delta.

## Completion criteria

- One primary class and one objective are explicit.
- Required sources and guides were read; irrelevant guides were not.
- Baseline, evidence and validation are recorded.
- Unverified platform behavior is stated as unknown or blocking.
- The exit criterion is satisfied or the status honestly says otherwise.
- The self-audit was performed and in-scope BLOCKER/HIGH findings remediated.
- The report exists and its absolute path is disclosed.

## Related files

- [`../architecture/qortal-dapp-development-standard.md`](../architecture/qortal-dapp-development-standard.md)
- [`../governance/source-of-truth-and-lifecycle.md`](../governance/source-of-truth-and-lifecycle.md)
- [`deepseek-primary-work-model.md`](deepseek-primary-work-model.md)
- [`report-storage-policy.md`](report-storage-policy.md)
- [`../../agents/00-SESSION-START.md`](../../agents/00-SESSION-START.md)
