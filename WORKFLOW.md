# Shared workflow

## 1. Define the outcome

ChatGPT converts the owner request into one owner-visible outcome with:

- measurable exit criterion;
- in-scope and non-goals;
- important invariants;
- required acceptance surfaces;
- explicit external-write authorization.

ChatGPT must actively challenge inferior or unsupported approaches and propose a
better bounded alternative. Agreement with the owner's first idea is not a
workflow goal.

## 2. Reuse before research

Before platform investigation:

1. search `skills/` for relevant capabilities;
2. record each selected skill's platform, maturity and last verification;
3. run its bounded freshness/compatibility gate against current authoritative
   source/runtime;
4. search current proven donor apps for the complete integration boundary;
5. investigate only the missing or changed delta.

A stale/absent skill triggers investigation; it does not justify guessing from
memory. A current verified skill should normally eliminate a full repeat audit.

## 3. Establish exact baseline

The designated orchestration controller records repository, branch, HEAD, full
dirty state, reference revisions, linked worktrees, environment IDs and
permissions. Where available, Codex Local / Work Local performs this controller
role; the controller surface never establishes executing-agent identity.
Preserve owner changes. Use an isolated worktree when necessary rather than
cleaning the owner checkout.

The controller gives the primary implementation agent the compact task
controller plus exact canonical context/skill paths. Do not paste the whole
knowledge base into every prompt.

## 4. Implement one coherent outcome

Current default primary implementer: DeepSeek.

The implementer:

1. follows the real production flow;
2. identifies the first confirmed mismatch or approved design boundary;
3. reuses current skills/reference implementations where compatible;
4. makes the smallest robust coherent change;
5. runs project-defined checks;
6. executes every accessible required real-runtime validation layer;
7. performs adversarial self-audit and remediates confirmed in-scope
   BLOCKER/HIGH findings.

Do not silently expand into unrelated refactors or platform modifications.

### Validation cadence: bounded fix vs checkpoint

Match validation effort to the change.

A bounded fix:

1. inspects the defect;
2. makes the smallest coherent patch;
3. runs only the focused regression tests and directly related checks;
4. runs `git diff --check`;
5. stops.

Do not follow every bounded fix with the entire test suite, the full build, a
complete runtime validation, another QDN publication, or another project-wide
audit. Those belong to an explicit checkpoint or final release gate, where the
accumulated change is validated once.

Keep targeted implementation validation and final release validation separate.
Do not repeat an already proven runtime matrix unless the changed code can
materially affect the behavior that matrix proves. A non-blocking observation
found during a bounded fix is recorded as a follow-up for later classification,
not converted into another implementation cycle.

At a final release gate, prove which bytes are actually served by comparing the
served bundle hash with the locally built release artifact, and record the exact
release artifact.

## 5. Review and escalation

The designated controller checks the handoff against the exact application
revision. Routine work gets a bounded handoff review. Independent review is
required for high-risk authority/data-integrity work, repeated failures and
release-critical changes. If the controller implemented the change, its own
review is not independent.

Escalate after two failed implementation attempts or one failed correction of an
owner runtime failure. Expensive/high-reasoning agents should be used where risk
or difficulty justifies them, not for routine repository reading/build loops.

## 6. Owner/runtime acceptance

Execute all accessible required acceptance steps. An owner-only action remains
explicitly pending. Unit, mock, lint, typecheck, build and local preview never
prove embedded Hub/Home or deployed QDN behavior.

For “all”, “everywhere” or “app-wide”, enumerate every relevant surface in the
controller and validate each.

## 7. Capability harvest

Before final handoff run
[`skills/shared/capability-harvest/SKILL.md`](skills/shared/capability-harvest/SKILL.md).

If the task discovered or corrected a reusable capability:

```text
project finding
-> identify reusable boundary
-> source/runtime evidence
-> create/update canonical skill
-> set maturity
-> define invalidation/freshness test
-> record skill path in handoff
```

This closes the compounding loop: each solved project should make later projects
cheaper when the solved knowledge is actually reusable.

## 8. Handoff and completion

Return a truthful handoff with exact application SHA, evidence by validation
layer, missing evidence, owner acceptance, external-write state and skill
harvest result. The handoff must name the agent that actually executed the work;
identity is never inferred from a template, an orchestration role or the CLI/tool
profile the work ran inside (see [GIT-AND-HANDOFF.md](GIT-AND-HANDOFF.md)). Author
every platform report from [templates/REPORT.md](templates/REPORT.md) and store
it at its canonical project/category path. Only
verified acceptance permits completion. Publishing/merging/releasing is a
separate authorized step.

Use [GIT-AND-HANDOFF.md](GIT-AND-HANDOFF.md) for machine-readable state. Store
substantial reports in the central project/category tree defined by
[REPORT-STORAGE-POLICY.md](docs/REPORT-STORAGE-POLICY.md); cross-project and
control-plane material belongs under `workspace/`. Compact task artifacts remain
under `tasks/`.

### Executable completion contract

For every **new** Workflow v3 job, the completion contract is mandatory and
machine-checked, not prompt advice. Both `dev start` and Telegram Dev Monitor
starts resolve the same project-scoped delivery policy from
[PROJECT-REGISTRY.md](PROJECT-REGISTRY.md) and receive the same default contract;
there is no start surface that can omit it or supply a global remote fallback.
The job must record in its evidence files:

1. task-start skill discovery and the freshness/compatibility result;
2. the control-plane, platform-pack and project documentation actually read;
3. the capability-harvest result;
4. the documentation updates, or an explicit statement that none were needed;
5. the scoped commit(s) after the recorded base SHA;
6. the authorized development-branch push and the verified remote SHA.

The policy must name an existing Git remote whose URL normalises to the
configured GitHub repository, a development pattern inside `agent/*`, and an
explicit automatic-push flag. A missing, ambiguous or mismatched remote refuses
the start before a job exists; it never guesses, reuses another project's remote
or downgrades the mandatory push check. Automatic push is limited to matching
non-protected `agent/*` branches; `main`/`master`/`trunk`, merges, tags,
releases, deployment, QDN writes, wallet transactions and server changes remain
separately unauthorized.

The harness also rejects a protected branch without explicit authorization, a
merge commit without merge authorization, changed paths outside the declared
scope, uncommitted changes outside declared owner paths, and secret-bearing
paths or diff patterns. A failed contract makes the job `FAILED`; a pending
authorization (for example an unauthorized required push) makes it `BLOCKED`.
Genuine acceptance or validation failures take precedence over pending
authorization and always remain `FAILED`. Contract checks never grant
authority: push, protected-branch, merge, deploy, QDN, wallet and destructive
actions each remain separately authorized.

`dev start --contract-file ...` may customize evidence files, allowed paths or
add explicit authorization, but it can never disable a mandatory check or
replace the validated project remote. Pre-existing owner changes are recorded as
allowed dirty paths and forbidden commit paths; they are preserved, never
staged, rewritten or required to be cleaned. Jobs created before this rule keep
their recorded contract state, and resuming such a legacy job does not
retroactively add or weaken one. See the
[Workflow v3 contract](docs/operations/DEV-WORKFLOW-V3.md#executable-completion-contract).

## Authorized unattended/overnight sessions

This is a delta to sections 1-8, not a second workflow and not a background
service. It applies only when the owner explicitly authorizes an unattended or
overnight session and names the repository, outcome, allowed external actions
and forbidden actions.

Terminal persistence mechanics (tmux naming, working directories, detach,
reattach, listing and safe cleanup) are documented in the
[OpenCode tmux session runbook](docs/operations/OPENCODE-TMUX-SESSIONS.md).
Persistence does not authorize autonomous execution or background scheduling;
this section still governs authorization, scope, validation and stop conditions.

Bounded unattended execution mechanics are documented in the
[unattended OpenCode runbook](docs/operations/UNATTENDED-OPENCODE.md). The run
uses a separate restricted agent profile, a short-lived execution guard with an
eight-hour maximum and one-execution lock, resource preflight at phase
boundaries, and safe process-group cancellation. The owner starts the task; no
scheduler, daemon, timer or polling agent is installed.

For multi-step or multi-hour development work, use the
[Workflow v3 development CLI](docs/operations/DEV-WORKFLOW-V3.md). It records
durable jobs with explicit acceptance criteria, runs them detached (no tmux),
detects blocked/failed outcomes, supports safe resume and sends optional
Telegram notifications. Its development profile allows normal Git/build/SSH,
registered workspace paths, Workflow/tooling state, Qortal/QDN work and
read-only VPS/Qortium diagnostics, with documented hard boundaries and
command-pattern limits
([permission semantics](docs/operations/OPENCODE-PERMISSIONS.md)). Recovered
intermediate permission or same-operation command failures do not block
completed work; unresolved denials and failed required acceptance criteria still
do. It is still owner-started and does not add a scheduler or background polling
service.

Before starting, record:

- the measurable outcome and phase exit criteria;
- exact repositories, branches, worktrees and authorized write actions;
- forbidden actions (for example mainnet payments, QDN publication,
  deployment, merge to `main`, server changes);
- a budget or stop condition and the one controller allowed to update shared
  handoff state.

During the session:

- do not stop for routine implementation decisions; make the smallest
  reversible choice and record unresolved owner decisions as numbered
  follow-ups in the handoff;
- keep money code, the data contract and the compatibility baseline serial
  before fanning out;
- parallelize only disjoint files and isolated worktrees; integrate one change
  at a time with its focused build/lint/tests; allow only one agent to drive a
  shared host, node or runtime;
- when the budget or stop condition is reached, stop starting new work and
  finish validation and handoff;
- keep the PR or handoff summary current, with a short morning summary at the
  top, evidence per phase and explicit owner-only or unverified items.

Sections 4-8 still govern validation cadence, review, acceptance, capability
harvest and durable handoff. Authorization for an overnight session does not
authorize publication, deployment, signing, transactions or merging.

## New application default

Use the functional bootstrap skill unless the product requires another proven
architecture:

```text
neutral functional shell
-> platform/QDN/auth/routing/data flows
-> tests + real host/runtime smoke
-> project-specific visual identity and polish
```

Do not impose one visual identity across owner apps. The reusable shell should be
replaceable at the presentation layer.

## Starting/resuming shorthand

Starting or resuming needs only: project ID + one outcome + this contract path.
For an unregistered project, discover the actual Qortal/Qortium repository and
platform context, add a registry row, then create only the thin routing/context
needed. Do not move or reinitialize an existing project to fit a preferred tree.
