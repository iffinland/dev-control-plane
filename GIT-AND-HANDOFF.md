# Git and durable handoff

Each task names an application repository, a verified base SHA and a unique
`agent/<project>/<task>` branch. Keep owner dirty checkouts intact; use a separate
worktree under `/home/iffi/dev-workspace/projects` when isolation is needed. Never force
push, rewrite shared history, update parent gitlinks or bundle unrelated changes.

A task records exact commit/push permission for both the application branch and
handoff repository/branch. Designing this workflow does not grant blanket push
permission. Reuse already-given authorization; do not ask again. Without it,
prepare local artifacts and state `handoff_sync = pending_authorization`.
Main/default-branch merge/push, tags, releases, deployment, QDN writes, signing,
transactions and issue mutation require their own explicit scope authorization.

Durable exchange, once a GitHub remote and branch permissions are configured:
1. Store `tasks/<project>/<task>/TASK.md`, `STATUS.json`, and the concise
   `IMPLEMENTATION.md`/`AUDIT.md` handoff files in this orchestration repository
   on the task branch. Create only artifacts that actually exist; start from
   `templates/`. TASK/STATUS record the exact skills loaded and their freshness
   result. Detailed reports and evidence belong in the central
   `docs/<project>/<category>/` tree defined by
   [REPORT-STORAGE-POLICY.md](docs/REPORT-STORAGE-POLICY.md).
2. Push authorized application changes first; verify the remote branch SHA.
3. The current writer updates STATUS with that exact application SHA, evidence
   and next actor. Commit and push handoff artifacts; verify their remote SHA.
4. The receiving agent fetches and reads the exact handoff commit and exact
   application SHA. Verify task ID, expected prior revision/state and evidence
   before claiming work. A changed application SHA invalidates prior review.
5. The designated orchestration controller is the single handoff-state
   writer/coordinator. Where available, Codex Local / Work Local fulfills that
   role; DeepSeek submits implementation evidence and the controller records the
   transition. Do not concurrently update STATUS. A stale/conflicting update
   requires re-read and reconciliation, never force push. Resume idempotently
   from task ID + application SHA + state.
6. Before the terminal handoff, record capability harvest: exact skills created
   or updated, their maturity, or an explicit project-specific/no-harvest result.
   A skill update is orchestration knowledge, not authorization to change or
   publish the application.

States: `planned -> implementing -> review_pending -> owner_validation_pending
-> complete`. Review may return `changes_required -> implementing`. Any active
state may become `blocked`, with reason, missing evidence and resume condition.
`review_pending` means reviewable, not product-ready. `complete` requires all
TASK acceptance checks, required live/host evidence and owner acceptance.
If owner acceptance is not applicable (e.g. a documentation-only task), record
that reason in TASK. Do not use READY/COMPLETE to hide an unexecuted workflow.

GitHub stores evidence; it does not start agents. No background polling,
notification service, API agent runner or scheduled job is installed by phase 1.
Dispatch requires a separately verified local DeepSeek client and an authorized
run. If unavailable, record a blocker; do not silently substitute a costly model.

Detailed reports are stored centrally under `docs/<project>/<category>/` per
[REPORT-STORAGE-POLICY.md](docs/REPORT-STORAGE-POLICY.md). Handoff artifacts
contain a concise summary, exact source revision and a durable remote report link
when available. For local-only reports, publish an explicitly approved, sanitized
evidence snapshot in the handoff; record the canonical local report path and
SHA-256. A local path alone is not a GitHub-readable handoff.
Never include credentials, wallet data, secrets or private infrastructure details.

## Agent identity in reports and handoffs

Every report, handoff, status artifact and commit-message body MUST name the
agent that actually executed the work — the implementer or validator that
produced the evidence — using its registered role name (`ChatGPT`, `Codex
Local`, `DeepSeek`, or a future explicitly registered role).

- Identity is evidence, never a default. Never infer the author from a template
  placeholder, a role's nominal responsibilities, the agent a task controller is
  addressed to, the orchestrator that dispatched the work, the CLI/tool profile
  the work ran inside, or whoever committed the file.
- The orchestration role/profile is not the executor. Work performed through a
  Codex/`codex` CLI or Work Local profile is still authored by the model that
  actually did the work (for example `DeepSeek`). `Codex`/`Codex Local` must
  never be written as the executing agent merely because the task was
  dispatched, curated, reviewed or run through that orchestration role/profile.
- Every platform report is authored from
  [`templates/REPORT.md`](templates/REPORT.md), whose executing-agent field is
  filled with the executor's own registered role at authoring time.
- Orchestrator/dispatcher and executing agent are recorded separately. When
  Codex Local writes or curates an artifact on behalf of DeepSeek (or another
  implementer), the artifact states `executing agent = DeepSeek` and
  `report/handoff writer = Codex Local`. The executing agent is the author of the
  work; the writer is not.
- An executor that cannot be established is recorded as `unknown` with the
  reason and the missing evidence. It is never guessed to make the field look
  complete.
- A correction of a prior misattribution is itself recorded — date, corrected
  field, the prior value and the evidence that establishes the real executor — so
  downstream readers can detect stale copies carrying the wrong attribution.
- [`templates/REPORT.md`](templates/REPORT.md), [`templates/HANDOFF.md`](templates/HANDOFF.md),
  [`templates/TASK.md`](templates/TASK.md) and [`templates/STATUS.json`](templates/STATUS.json)
  carry explicit executing-agent fields for this purpose.

This rule is universal across platforms and agents. Platform report policies may
add their own disclosure requirements but MUST NOT replace the executed-agent
identity with an orchestration role.
