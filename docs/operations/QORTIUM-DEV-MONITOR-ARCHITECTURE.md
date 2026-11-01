# Qortium Dev Monitor — Telegram remote control architecture

Status: **P1 read-only observer, P2 authorized control, P3 cancellation plus
queued owner messaging and P4 hardening implemented with an optional systemd
user unit; P5 remains proposed.** Activation remains manual; see
[QORTIUM-DEV-MONITOR.md](QORTIUM-DEV-MONITOR.md) and the
[P4 owner acceptance checklist](QORTIUM-DEV-MONITOR-P4-ACCEPTANCE.md).

| Field | Value |
| --- | --- |
| Executing agent | `DeepSeek` |
| Report/handoff writer | `DeepSeek` (same agent) |
| Executing-agent evidence | Work performed in this session by the `deepseek/deepseek-flash` model through the owner-authorized Workflow v3 job. No second agent produced the audit or design. |
| Artifact type | Control-plane operations / architecture report |
| Project scope | Cross-project Workflow v3 control plane (`workspace` material) |
| Canonical path | `docs/operations/QORTIUM-DEV-MONITOR-ARCHITECTURE.md` |
| Base repository / branch / HEAD | `/home/iffi/dev-workspace/control-plane`, `agent/control-plane/workflow-v3-20261031`, `be5fde3` |
| Reference contract | [AGENTS.md](../../AGENTS.md), [WORKFLOW.md](../../WORKFLOW.md), [GIT-AND-HANDOFF.md](../../GIT-AND-HANDOFF.md) |
| Report policy note | The owner explicitly requested this path. This is an operations/architecture document, not a substitute for later implementation evidence. Later implementation and validation evidence must still be stored under `/home/iffi/dev-workspace/docs/workspace/implementation/` and `/validation/` per [REPORT-STORAGE-POLICY.md](../REPORT-STORAGE-POLICY.md). |
| Implementation state | P1 read-only observer, P2 authorized control, P3 additive cancellation plus queued owner messaging and P4 hardening are implemented in `tools/dev_monitor.py`, `tools/devmonitor/` and additive Workflow v3 changes. P3 adds the `CANCELLED` state, verified `dev cancel`, optional `dev resume --prompt-file -`, durable queued owner instructions with explicit delivery state, safe resume composition and explicit new-session confirmation. P4 adds detector-classification regression fixes, lifecycle-notification redaction, per-user/per-chat rate limits, an hourly start cap, atomic one-time confirmation claims, job-directory symlink resistance, isolated fault-injection tests and the real-runtime owner acceptance checklist. `read_only` remains the default; control mode is explicit owner configuration and remains restricted to the numeric private-chat allowlist. The optional systemd user unit under `deploy/systemd/user/` was not installed, enabled, restarted or started by the repository, and owner-local `telegram.json` was not modified. No Qortium service, listener, node or VPS setting was changed. The owner must activate the bot manually; see [QORTIUM-DEV-MONITOR.md](QORTIUM-DEV-MONITOR.md). |

## 1. Executive summary

Qortium Dev Monitor (QDM) is a proposed owner-only Telegram control surface for the
existing Workflow v3 development-job system. It is not a new job engine and it is
not Qortium node software. It reads the existing job store, drives the existing
`dev` CLI, observes OpenCode session lifecycle evidence, and adds an interactive
owner interface.

The design is deliberately layered:

```text
Telegram Bot API (long polling, outbound only)
        |
        v
QDM authorization, routing, rendering, redaction, rate limiting
        |
        +--> Workflow v3 CLI (start/resume/report/accept; cancel in a later phase)
        +--> Read-only job store (job.json, events.jsonl, logs, reports)
        +--> Read-only project registry (PROJECT-REGISTRY.md)
        +--> Read-only central docs tree (safe resolver)
        +--> QDM private state (offset, cursors, wizard state, audit)
```

The most important design decisions are:

1. **No public inbound port.** The monitor uses Telegram long polling with an
   outbound HTTPS client. It never calls `setWebhook`, starts a web server, opens
   a listener, or exposes an API.
2. **No direct job mutation.** The monitor invokes the existing `dev` CLI as a
   subprocess with argument arrays and `shell=False`. It does not import the job
   runner to create jobs in-process, and it never writes `job.json`.
3. **Read-only by default.** Phase 1 ships in `read_only` mode. Starting,
   resuming, cancelling and accepting require a separate `control` mode,
   explicit confirmation and (recommended) a local unlock passphrase.
4. **Authorization is by numeric Telegram user ID and private chat ID**, not by
   username, display name, group membership or callback content.
5. **The monitor does not make Workflow v3 more powerful.** It exposes only
   allowlisted v3 operations. Cancel is deferred to a later additive `dev cancel`
   command with its own tests because the current CLI has no safe cancel surface.
6. **True mid-run agent injection is not supported.** Owner messages are queued
   and delivered at the next `dev resume` boundary. The monitor never writes
   OpenCode's SQLite store, never starts `opencode serve/web/acp`, and never uses
   `--auto`.
7. **Document access is an allowlisted, descriptor-based read-only capability.**
   Paths are resolved from trusted roots with `O_NOFOLLOW` per component, regular
   files only, size caps, sensitive-name denial, and redaction for text previews
   and text downloads.
8. **Qortium and the VPS remain untouched.** The monitor never runs `sudo`,
   service managers, package managers, network configuration, mount commands, or
   Qortium control commands. It does not signal processes by name.

## 2. Goals, non-goals and invariants

### 2.1 Goals

- Provide interactive Telegram menus for jobs, projects and documents.
- Show live job status, including total and per-attempt elapsed time, state,
  pending acceptance criteria, blocker, detected issues and worker liveness.
- Allow owner selection of a registered project for job start and document
  browsing.
- Show job logs and reports, with bounded output and safe pagination.
- Send STARTED and RESUMED notifications in addition to the existing final-state
  notifications.
- Allow owner-authorized start, resume and cancel flows.
- Provide safe two-way owner/agent communication: owner instructions are queued
  and delivered on resume; agent questions and blockers are surfaced to the
  owner.
- Serialize job admission per project without changing the existing global
  one-execution guard.
- Provide read-only document browsing and download from the central docs tree.
- Keep all credentials, tokens and sensitive output out of Git, logs, reports,
  audit records and Telegram messages.
- Preserve all unrelated uncommitted work in the repository.

### 2.2 Non-goals

- No webhook, HTTP server, public port, reverse proxy or inbound API.
- No Qortium node control, restart, configuration, database, wallet, JAR or log
  mutation.
- No VPS system administration, service installation, firewall, mount, kernel,
  network or package changes.
- No generic shell console or arbitrary command execution from Telegram.
- No arbitrary filesystem browser. Only configured document roots are visible.
- No live prompt injection into a running `opencode run` session.
- No direct reads or writes of OpenCode's SQLite session database.
- No automatic scheduler, timer, dispatcher or self-starting job queue.
- No change to existing Workflow v3 job semantics in this task.
- No implementation of the bot in this task.

### 2.3 Invariants

- The existing execution guard remains the authority for one heavyweight OpenCode
  execution, resource preflight, the eight-hour per-attempt maximum and
  process-group cancellation.
- The existing job store remains the durable source of truth for job state.
- OpenCode exit code `0` is never acceptance. Acceptance criteria remain
  authoritative.
- `SUCCESS` is computed from evidence, not process exit alone.
- A timed-out or cancelled job preserves the working tree and session history so
  `dev resume` can continue.
- The monitor never expands the authorization scope of a job.
- Unrelated uncommitted changes are never staged, reset, cleaned, stashed or
  committed by this work.

## 3. Read-only audit of the current system

This section records what was inspected and the constraints the design must
respect. It is an audit of source and documentation at the base revision, not a
runtime test of a new bot.

### 3.1 Workflow v3 CLI

Inspected: [tools/dev.py](../../tools/dev.py),
[DEV-WORKFLOW-V3.md](DEV-WORKFLOW-V3.md).

Observed commands:

| Command | Behaviour relevant to the monitor |
| --- | --- |
| `dev start` | Requires a prompt and at least one acceptance criterion. Resolves the repository, takes a Git snapshot, runs guard preflight, creates a durable job, optionally starts detached, and prints the job. Supports `--dry-run` and `--json`. |
| `dev status` | Supports one job, latest job or `--all`, plus `--json`. Reconciles stale `RUNNING` jobs whose worker disappeared. |
| `dev report` | Renders and writes `report.md`, then prints it. `--json` returns job status and report path. |
| `dev logs` | Reads `run.log` or `worker.log`; supports line count and follow mode. |
| `dev resume` | Reuses the same job directory, repository/worktree and OpenCode session. Refuses a live `RUNNING` job. Requires a known session ID unless `--new-session` is explicitly used. |
| `dev accept` | Records manual acceptance for manual criteria only; command criteria must still pass. |
| `dev _worker` | Internal detached worker entry point. The monitor never calls it. |

Important audit findings:

- There is **no `dev cancel` command**. The guard handles `SIGINT`/`SIGTERM` for
  the process group it owns, but there is no owner-facing, verified cancel
  surface. A remote cancel must therefore be phased behind an additive,
  tested v3 command.
- `--prompt-file -` exists for `dev start`, which allows the monitor to pass a
  prompt on standard input instead of the process argument list. `dev resume`
  only accepts `--prompt`, so a later additive `--prompt-file -` is recommended
  for long or sensitive resume instructions.
- `--json` is available on the read paths and is the preferred monitor boundary.
- `dev status --all --json` is the stable list view; `dev status <id> --json`
  exposes total elapsed, attempt elapsed, attempt number, PIDs, worker liveness,
  pending criteria, issues, blocker, session ID and notification records.

### 3.2 Job storage

Inspected: [tools/devjob/store.py](../../tools/devjob/store.py),
[DEV-WORKFLOW-V3.md](DEV-WORKFLOW-V3.md).

Observed storage contract:

- State root precedence: explicit `--state-dir`, then
  `DEV_CONTROL_PLANE_STATE`, then `$XDG_STATE_HOME/dev-control-plane`, then
  `~/.local/state/dev-control-plane`.
- Jobs live under `<state-root>/jobs/<job-id>/`.
- `job.json` is written atomically with a temporary file, `fsync`, mode `0600`
  and `os.replace`.
- Runtime directories are created with mode `0700`; lock, log and report files
  are chmodded `0600`.
- `events.jsonl` is append-only and stores lifecycle events. `job.json` keeps the
  most recent 200 events; the JSONL file is the durable event stream.
- A per-job `.worker.lock` uses `fcntl.flock(..., LOCK_EX | LOCK_NB)` to prevent
  two workers from driving one job.
- `worker_is_alive()` checks the PID and verifies that `_worker` and the job ID
  appear in the process command line.
- `job_dir()` rejects empty IDs, `/`, `.` and `..`. Job IDs are generated from a
  timestamp, a slug and a UUID fragment.
- `safe_text()` redacts obvious `token`/`secret`/`password`/`api_key`
  assignments and truncates.
- Job states are `RUNNING`, `SUCCESS`, `FAILED`, `BLOCKED` and `TIMEOUT`. There is
  no `CANCELLED` state.

Important audit findings:

- There is **no per-project or per-repository lock** in the store. Only the
  global guard lock and the per-job lock exist.
- Several job fields are stored unredacted, including `prompt`, `resume_prompt`,
  acceptance output and a `guard_command` event that contains the full quoted
  command, including the prompt. The monitor must redact before display; a later
  v3 hardening task should reduce or redact prompt persistence.
- The job record contains absolute log/report paths. The monitor must derive
  allowed paths from the validated job directory and known filenames rather than
  trusting arbitrary path fields.

### 3.3 Worker, guard and OpenCode lifecycle

Inspected: [tools/devjob/runner.py](../../tools/devjob/runner.py),
[tools/opencode_guard.py](../../tools/opencode_guard.py),
[tools/session_state.py](../../tools/session_state.py),
[UNATTENDED-OPENCODE.md](UNATTENDED-OPENCODE.md).

Observed lifecycle:

- `create_job()` runs guard preflight. A refusal creates a `BLOCKED` job instead
  of starting a doomed process.
- `spawn_worker()` starts `dev.py _worker` with `start_new_session=True`,
  redirected streams and `DEV_CONTROL_PLANE_STATE` preserved. Closing SSH does
  not stop the job.
- The worker acquires the per-job lock, appends an attempt, invokes the guard and
  then runs acceptance criteria.
- The guard enforces one heavyweight OpenCode execution at a time through a
  global `guard.lock`, an eight-hour maximum per attempt, resource thresholds and
  safe process-group termination.
- The guard only terminates the process group it created. It refuses to signal
  PID/PGID `<= 1`, the guard's own process group, or a detected Qortium process
  group. It reads Qortium only for PID/RSS reporting.
- Session completion uses `opencode export`/`session list` through an anonymous
  temporary file. Completion means the agent turn ended with no active tool
  call; it is explicitly not acceptance.
- A resumed job starts a new attempt in the same job directory and the same
  OpenCode session when the session ID is known.

Important audit findings:

- **Live two-way messaging is not supported by the current execution model.** A
  running `opencode run` is a single non-interactive turn. There is no supported
  API for injecting a new user message into that turn without starting a server,
  writing the session database or otherwise bypassing the guard.
- The monitor's safe alternative is a queued instruction delivered by
  `dev resume` after the current attempt ends.
- The global guard serializes all projects, not just one project. Per-project
  serialization is therefore an additional admission rule, not a replacement for
  the guard.
- The guard's PID evidence (`guard_pid`, `child_pid`, `child_pgid`) is sufficient
  for a later verified `dev cancel`, but a cancellation command must revalidate
  the process identity to avoid PID-reuse mistakes.

### 3.4 Detection and reports

Inspected: [tools/devjob/detect.py](../../tools/devjob/detect.py),
[tools/devjob/runner.py](../../tools/devjob/runner.py).

Observed:

- Detection prefers structured `opencode export` events and falls back to a
  context-aware console-log parser.
- It scans tool state and assistant text, not arbitrary user prompts, successful
  tool output, source files or diffs.
- It emits bounded, sanitized issue excerpts and a maximum of 50 issues.
- Reports include acceptance criteria, verification, detected issues, Git
  snapshot, notifications, session-completion evidence and the acceptance rule.
- Acceptance command output is stored in `acceptance-ACx.log`; the tail is also
  stored in `verification` inside `job.json`.

Monitor implications:

- Detected issues are useful for owner alerts, but their excerpts still pass
  through the monitor redactor before display.
- Report and acceptance log content can contain secrets from the build or test
  environment. Redaction is mandatory.

### 3.5 Notification module

Inspected: [tools/devjob/notify.py](../../tools/devjob/notify.py),
[DEV-WORKFLOW-V3.md](DEV-WORKFLOW-V3.md).

Observed:

- Notifications are optional and final-state only:
  `SUCCESS`, `FAILED`, `BLOCKED`, `TIMEOUT`.
- Credentials are loaded from `~/.config/dev-control-plane/telegram.json` or
  `DEV_TELEGRAM_CONFIG`, with environment overrides.
- The loader warns when the config is group/world accessible.
- Delivery uses an outbound HTTPS `sendMessage` call through `urllib`.
- Failures never change the job result; reasons are sanitized.
- The token is removed from error text and from `TelegramSettings.__repr__`.
- Notification records are appended to the job but capped at 20.

Important audit findings:

- The existing module is **one-way and final-only**. It has no `getUpdates`,
  callback handling, interactive menus, STARTED/RESUMED events or document
  delivery.
- There is no need to fork or replace it. The monitor should reuse the same
  credential file and final-state format where practical, while owning all
  interactive and lifecycle messaging.
- To avoid duplicate final messages, jobs started by the monitor should use
  `--no-notify`; the monitor then sends the final message. Jobs started directly
  through the CLI keep the existing final notification, and the monitor can
  deduplicate by reading `job["notifications"]`.

### 3.6 Project discovery

Inspected: [PROJECT-REGISTRY.md](../../PROJECT-REGISTRY.md),
[ENVIRONMENT.md](../../ENVIRONMENT.md).

Observed:

- Registered projects are recorded in a Markdown table with project ID, platform,
  verified local path, project-level `AGENTS.md`, canonical context status and
  central report root.
- Platform source references are a separate section and are not projects.
- Deferred registry entries are explicitly not routable until verified.
- The central docs root is `/home/iffi/dev-workspace/docs`; each registered
  project has its own root.
- No machine-readable registry exists.

Monitor implications:

- The monitor needs a small, read-only registry parser. It must not invent a
  project from a similarly named directory.
- Job start must accept only registered, job-eligible projects whose repository
  path exists and is under configured repository roots.
- Source references and deferred entries must not be startable.
- A registry parse failure must fail closed for start/resume; document browsing
  can still use configured document roots.

### 3.7 Central documentation structure

Inspected: `/home/iffi/dev-workspace/docs`, especially `workspace/`,
registered project roots, `references/`, and [REPORT-STORAGE-POLICY.md](../REPORT-STORAGE-POLICY.md).

Observed:

- The central root is grouped by project, then by category: `audit/`,
  `reports/`, `research/`, `implementation/`, `validation/`, `handoffs/`.
- Category directories are created only when an artifact exists.
- `workspace/` holds cross-project and control-plane material.
- `references/` holds preserved source documents with provenance; it is not
  current platform authority.
- The docs directory is its own Git repository with `.git`, `.githooks` and a
  security exception file.
- Unregistered directories can exist in the tree and must not automatically
  become visible in the monitor.

Monitor implications:

- Document roots must be explicitly allowlisted, normally derived from registered
  central roots plus `workspace/` and optionally `references/`.
- The docs Git metadata, hooks, hidden files and unregistered directories must not
  be browsable by default.
- Access must be read-only. The monitor must never create, edit or delete files
  under the docs tree.

### 3.8 Baseline validation and preservation

At audit time, before any edit:

```text
branch: agent/control-plane/workflow-v3-20261031
HEAD:   be5fde3
control-plane validator: passed
skills validator:        passed
security validator:      passed
```

Pre-existing unrelated changes were present and were left untouched:

```text
 M skills/README.md
 M skills/qortium/home2-qdn-publishing/SKILL.md
 M skills/qortium/qdn-resource-discovery/SKILL.md
?? skills/shared/browser-thumbnail-generation/
```

No reset, clean, stash, checkout, relocation or deletion was performed. The
architecture document is the only file this task commits.

## 4. Architecture overview

### 4.1 Design principles

1. **Reuse the durable engine.** Workflow v3 remains the only job engine.
2. **Separate observation from mutation.** Read paths are read-only; mutations go
   through explicit, allowlisted CLI calls.
3. **Fail closed.** Missing config, invalid authorization, malformed registry,
   unsafe path or ambiguous process identity results in refusal, not a guess.
4. **Server-side state.** Telegram callback data is a short reference to
   server-side state, never a path, prompt, command or authorization claim.
5. **Least exposed surface.** No generic shell, no arbitrary file path, no
   arbitrary model/agent, no arbitrary repository.
6. **Defense in depth.** Authorization is followed by input validation, path
   checks, redaction, confirmation, rate limits and idempotency.
7. **Polling, not listening.** The only network client is outbound HTTPS to the
   Telegram Bot API.

### 4.2 Component diagram

```text
+-----------------------------+
| Telegram Bot API            |
| getUpdates / sendMessage    |
| editMessageText / sendDoc   |
+--------------+--------------+
               ^ outbound HTTPS long poll
               |
+--------------+----------------------------------------------+
| Qortium Dev Monitor                                         |
|                                                             |
|  api.py          transport, retries, 429/409 handling        |
|  auth.py         user/chat authorization, unlock, nonces     |
|  router.py       update dispatch, deduplication, rate limit  |
|  render.py       menus, status, logs, reports, chunking      |
|  jobs.py         CLI facade, job reads, event watcher        |
|  projects.py     registry parser and validation              |
|  documents.py    descriptor-based safe docs resolver         |
|  redact.py       credential and path redaction               |
|  state.py        SQLite monitor state and audit              |
|  service.py      single-instance loop, locks, stop flag      |
+----+------------------+------------------+-------------------+
     |                  |                  |
     | subprocess       | read-only        | read-only
     v                  v                  v
+---------+      +-----------+      +-------------------+
| dev CLI |      | job store |      | central docs tree |
| existing|      | job.json  |      | allowlisted roots |
| v3 only |      | events    |      | read-only         |
+---------+      | logs      |      +-------------------+
                 | reports   |
                 +-----------+
```

### 4.3 Proposed package layout

This layout is proposed, not implemented:

```text
tools/dev_monitor.py                 entry point: run / check / status / stop
tools/devmonitor/
  __init__.py
  config.py                          config loading and validation
  auth.py                            user/chat allowlist, unlock, nonces
  api.py                             Telegram Bot API client and long polling
  router.py                          update dispatch and idempotency
  menus.py                           inline keyboard definitions
  render.py                          message formatting and chunking
  redact.py                          credential redaction
  jobs.py                            CLI facade, status, logs, reports, events
  projects.py                        PROJECT-REGISTRY.md parser
  documents.py                       safe docs listing and descriptor reads
  state.py                           SQLite state, cursors, wizard state
  service.py                         main loop, lock, stop flag, signals
tools/test_dev_monitor_auth.py
tools/test_dev_monitor_documents.py
tools/test_dev_monitor_jobs.py
tools/test_dev_monitor_redact.py
tools/test_dev_monitor_integration.py
```

No existing `dev.py`, `devjob/*`, guard or session-state file is modified by
Phases 0-2. Phase 3's additive cancel command is a separate authorized change.

### 4.4 Runtime topology and long polling

- One owner-started process, either in a foreground terminal or through the
  optional systemd user unit stored in `deploy/systemd/user/`. It is not a
  repository-installed system service, scheduler or daemon; installing the user
  unit is an explicit owner action.
- The process acquires a single-instance lock under the monitor state directory.
  If the lock is held, it refuses to start rather than creating a second poller.
- It calls `getUpdates` with a long-poll timeout (default 20-30 seconds). It does
  not call `setWebhook`.
- It processes updates sequentially, persists the next offset only after the
  update is handled or dead-lettered, and uses numeric update IDs for
  deduplication.
- If a webhook is already configured, the monitor fails closed and reports the
  conflict. A small owner-run `delete-webhook` helper may clear it later; the
  monitor never silently changes Telegram bot configuration.
- Outbound-only operation means no new listening socket on the VPS. A useful
  verification is that the monitor process has no LISTEN socket in `ss -ltnp`.
- Jobs are detached from the monitor. Stopping or restarting the monitor does not
  stop running jobs.

### 4.5 Primary flows

Start:

```text
owner selects project -> wizard (title, prompt, criteria, timeout)
-> confirmation summary -> admission lock for project
-> existing `dev start --json --no-notify`
-> RUNNING: send STARTED, register status message
-> BLOCKED/refusal: show sanitized reason, no STARTED
```

Observe:

```text
poll loop -> read telegram updates
-> read `dev status --all --json` (cache a few seconds)
-> render list/status/report/log views
-> edit existing status message where possible
-> refresh only active jobs and only while the owner requested it
```

Notify:

```text
event watcher reads events.jsonl per job with persisted inode/offset/hash
-> STARTED on first worker/attempt start
-> RESUMED on resume_requested or a resumed attempt
-> terminal state from job status
-> deduplicate against job["notifications"] for CLI-started jobs
```

Resume:

```text
owner opens terminal job -> optional queued owner messages
-> confirmation -> `dev resume --json`
-> new attempt in the same job directory and session
-> RESUMED notification and same status message
```

Cancel (Phase 3 only):

```text
owner confirms -> additive `dev cancel --json`
-> v3 verifies job, worker and guard identity
-> SIGTERM to the exact guard PID, never by name
-> guard stops only its child process group
-> state CANCELLED, worktree and session preserved
-> owner may resume later
```

## 5. Functional design

### 5.1 Telegram menus and commands

The primary interface is inline keyboards. Text commands are a small convenience
surface and are never a substitute for authorization.

| Surface | Entry | Contents |
| --- | --- | --- |
| Main menu | `/start`, `/menu` | Jobs, Projects, Documents, Status, Help |
| Jobs | `/jobs` | Active jobs first, then recent terminal jobs; project filter; pagination |
| Job | job button | State, timing, attempt, PIDs, session, pending criteria, blocker, issues, queued messages; actions |
| Projects | `/projects` | Registered projects with platform, repository status and docs link |
| Documents | `/docs` | Allowlisted document roots, then directories and files |
| Status | `/status [job]` | Compact status text; same renderer as the job view |
| Help | `/help` | Commands, modes, safety notes and the exact active mode |

Suggested job actions:

- Refresh
- Auto-refresh on/off
- Logs (run / worker)
- Report
- Resume
- Cancel (only when the cancel command exists and control mode is enabled)
- Accept manual criteria (optional; explicit confirmation)
- Queue owner instruction
- Download report

All callbacks are short and opaque. Suggested grammar, all under 64 bytes:

```text
m                          main menu
j:<job-index>              job view
j:<job-index>:r            refresh
j:<job-index>:l:<kind>     logs
j:<job-index>:p            report
j:<job-index>:s            resume wizard
j:<job-index>:c            cancel confirmation
j:<job-index>:q            queue instruction
w:<wizard-id>:<action>     wizard step
b:<browse-id>:<action>:<n> document browser
x:<nonce>:y|n              confirmation
```

`job-index`, `wizard-id` and `browse-id` are server-side identifiers. The monitor
maps them to the real job ID or document path after re-authorizing the caller.
Paths, prompts, commands and user IDs are never placed in callback data.

### 5.2 Authorization and modes

Two modes:

- `read_only` (default): list jobs, inspect status, read logs and reports, browse
  documents. No start, resume, cancel, accept or owner-message delivery.
- `control`: read-only plus start, resume, and (when available) cancel/accept.
  Control mode requires explicit confirmation for each mutating action.

Authorization rules:

1. Only `update.message` and `update.callback_query` are accepted. Channel posts,
   inline queries and other update classes are ignored.
2. `from.id` must be an integer in `authorized_user_ids`.
3. The chat must be a private chat and `chat.id` must be in `allowed_chat_ids`.
4. The user ID and chat ID are rechecked for every callback, not just the first
   message.
5. Usernames, display names, forwarded headers, group membership and
   `callback_data` claims are never authorizing.
6. An optional local unlock passphrase protects control actions even if the
   Telegram account is compromised. The passphrase is stored only as a salted
   scrypt/PBKDF2 hash in owner-local config. Unlock is time-bounded per
   user/chat.
7. Unknown users receive a generic denial. The monitor may log their numeric ID
   and update ID for owner diagnosis, but never their message content.

### 5.3 Live job status

The status view is built from `dev status <job-id> --json`. It displays:

- state and state age;
- total job elapsed and current/last attempt elapsed;
- attempt number, start/end time and per-attempt timeout;
- worker/guard/child liveness and PIDs (with an explanation that PIDs are
  evidence, not control handles);
- OpenCode session ID (truncated for display);
- pending acceptance criterion IDs;
- detected issue count and sanitized issue summaries;
- blocker text;
- queued owner-message count;
- resume count;
- last notification result, sanitized;
- buttons for logs, report, resume, cancel and refresh.

Refresh behaviour:

- One status message per job per chat is kept in `message_refs` and edited in
  place.
- Auto-refresh is opt-in. While enabled, active jobs refresh on a bounded cadence
  (default 30 seconds) for a bounded duration (for example 30 minutes), then
  switch off with a notice.
- Telegram rate limits and `retry_after` are respected. A "Message is not
  modified" response is not silently ignored: Refresh reports that the job
  status is unchanged since the last refresh, so the button always has visible
  feedback.
- If the status message was deleted, the monitor recreates it and updates its
  reference.

### 5.4 Project selection

The monitor parses the registered-projects table in
[PROJECT-REGISTRY.md](../../PROJECT-REGISTRY.md). For each row it extracts:

- project ID;
- platform;
- repository path;
- project-level `AGENTS.md` presence;
- central report root;
- Git remote name, GitHub repository, `agent/*` branch pattern and explicit
  automatic-push authorization.

Validation:

- The repository path and central docs root must exist and must resolve under
  configured workspace roots.
- The project must not be a platform source reference or a deferred entry.
- A project with a missing or invalid repository is shown as unavailable and
  cannot be started.
- A project with a missing, ambiguous, non-GitHub or URL-mismatched delivery
  policy is shown as unavailable and cannot be started.
- A project with a missing docs root can still be started if its repository and
  delivery policy are valid, but its documents link is disabled.

Project selection is used in two places:

1. Start/resume admission: only registered, job-eligible projects can be chosen.
2. Document browsing: registered central roots plus `workspace/` and optional
   `references/` are visible.

The monitor caches the parsed registry for a short interval and re-reads it after
a file change. A parse failure fails closed for job mutation.

### 5.5 Starting a job

The wizard collects:

1. project (button selection only);
2. title;
3. prompt (text; bounded length);
4. at least one command acceptance criterion or one manual criterion;
5. timeout (bounded to the existing eight-hour maximum);
6. optional branch label;
7. confirmation.

The confirmation summary shows the exact repository, title, redacted prompt
preview, exact acceptance commands, timeout, agent and model. The owner must press
Confirm. The monitor then:

- acquires the per-project admission lock;
- checks for an active job in the same project;
- invokes:

```text
python3 tools/dev.py start \
  --project <registry-project-id> \
  --registry <PROJECT-REGISTRY.md> \
  --repo <registry-repository> \
  --title <title> \
  --prompt-file - \
  --criterion <label::command> ... \
  --manual-criterion <text> ... \
  --timeout <duration> \
  --agent <allowlisted-agent> \
  --model <allowlisted-model> \
  --no-notify \
  --json
```

- writes the prompt to standard input and closes it;
- uses `shell=False` and an argument array;
- records the returned job ID in monitor state;
- sends `STARTED` only if the returned state is `RUNNING`;
- shows the sanitized `BLOCKED` refusal if preflight refused.

The monitor never accepts a free-form repository path, arbitrary agent profile,
arbitrary model, arbitrary timeout above eight hours, or a job with no acceptance
criteria. Acceptance commands are intentionally executed by Workflow v3 with
`bash`; the monitor displays them exactly and requires explicit confirmation.

### 5.6 Resuming a job

Resume is available for terminal or reconciled jobs. The monitor:

- refuses if Workflow v3 reports the job `RUNNING` with a live worker;
- refuses if a different job in the same project is active;
- shows the job ID, title, attempt number, session ID, current blocker and any
  queued owner messages;
- collects an optional resume instruction;
- composes the prompt from the base resume instruction plus queued owner messages;
- invokes `dev resume <job-id> --json` with optional `--timeout` and `--prompt`;
- never uses `--new-session` unless the owner explicitly confirms that session
  continuity is being abandoned;
- never uses `--force` unless the owner explicitly confirms a successful job
  should run again;
- sends `RESUMED` after the CLI returns a new attempt.

If the session ID is unknown, v3 already refuses to attach to a random session.
The monitor surfaces that refusal and offers `--new-session` as an explicit,
separately confirmed option.

### 5.7 Cancelling a job

The current system has no cancel command. The proposed safe design is an additive
`dev cancel <job-id> --json` in Workflow v3, implemented and tested in a separate
authorized task:

1. Load the job and refuse unless it is `RUNNING` with a live worker.
2. Read the recorded `guard_pid`, `worker_pid` and, when present, attempt
   metadata.
3. Verify `/proc/<guard_pid>/cmdline` identifies the Workflow v3 guard and the
   job-specific log path or session title. Record a distinct `cancel_requested`
   event before signalling.
4. Refuse if the PID is PID 1, the caller's own process group, a detected
   Qortium process, or an identity that does not match the job.
5. Send `SIGTERM` to the exact guard PID only. The guard then stops the child
   process group it created, using its existing safe process-group logic.
6. Wait for the worker to finalize. If the guard does not exit within a bounded
   grace period, report "cancel requested; guard still alive" and do not escalate
   to a name-based kill.
7. Mark the attempt and job `CANCELLED` (a new additive terminal state), skip
   command criteria, preserve the working tree and session, write the report and
   notify if configured.

Until that command exists and passes its tests, the monitor must not expose a
cancel button in production. A monitor-side direct signal is explicitly rejected:
it would duplicate dangerous process logic outside the tested guard boundary.

Cancellation is not "delete the job". A cancelled job remains resumable with
`dev resume`, exactly like a timeout or a failed attempt.

### 5.8 Acceptance

`dev accept` is an existing, owner-only operation for manual criteria. The
monitor may expose it as an optional control action:

- show the exact manual criteria and current verification;
- require explicit confirmation;
- invoke `dev accept <job-id> --all-manual --note <sanitized note> --json`;
- re-render the job state and report.

Command criteria cannot be accepted manually. The monitor must never imply that
manual acceptance proves a command criterion.

### 5.9 STARTED and RESUMED notifications

The existing notification module only sends final states. The monitor adds
lifecycle notifications by reading `events.jsonl` without modifying v3:

| Event | Notification |
| --- | --- |
| `worker_started` or first `attempt_started` with `resume=False` | `STARTED` |
| `resume_requested` or `attempt_started` with `resume=True` | `RESUMED` (attempt number, resume count) |
| `blocked_preflight` or terminal `BLOCKED` | `BLOCKED` with sanitized reason |
| `reconciled_stale` | `WORKER LOST` alert |
| `worker_lock_conflict`, `worker_error` | sanitized error alert |
| `finished` | terminal state; send only if not already handled |

Implementation details:

- Read the file with `os.stat` for inode and size, persist `(inode, offset,
  last_event_hash)` per job, and read from the last offset on each poll.
- If the inode changes or the file shrinks, reset to offset 0 and deduplicate by a
  hash of the event JSON. This handles monitor restarts and file replacement.
- Send each lifecycle notification at most once per `(job, event, timestamp,
  detail)` key.
- Monitor-started jobs use `--no-notify`, so the monitor is the sole sender.
- For CLI-started jobs, the existing final notification remains authoritative. The
  monitor inspects `job["notifications"]`; if a terminal record was already sent,
  it does not duplicate it. If delivery previously failed, the monitor may offer a
  manual resend, but it does not silently spam retries.
- Lifecycle messages include project, job short ID, title, attempt number,
  elapsed, timeout and buttons. They never include the prompt or raw log lines.

### 5.10 Logs and reports

Logs:

- Read only known files derived from the validated job directory: `run.log` and
  `worker.log`. Do not trust arbitrary paths from `job.json`.
- Enforce a maximum byte window (default 64 KiB) and a maximum line count
  (default 100). Show the newest lines first or last consistently.
- Redact before display. Never send ANSI escapes or control characters raw.
- Paginate rather than sending an unbounded log.
- Provide a manual Refresh; do not stream-follow in Telegram.
- Optionally send the selected log as a redacted text document, capped at 2 MiB.

Reports:

- Prefer the durable `report.md` in the job directory.
- For a fresh report, invoke `dev report <job-id>` and capture its text; this is an
  existing v3 write and is allowed because it is the documented report surface.
- Render a bounded summary in chat and offer the full report as a redacted text
  document.
- Never expose absolute state paths in a way that invites manual shell access;
  display the job short ID and relative artifact name.

### 5.11 Safe two-way agent messaging

The honest boundary: Workflow v3 runs a single non-interactive OpenCode turn.
There is no safe live input channel. The monitor therefore implements messaging as
a durable queue with resume-boundary delivery.

Owner to agent:

- "Queue instruction" is available while a job is running or terminal.
- Each message is stored in monitor state with ID, author user ID, chat ID, job
  ID, creation time, body, delivery marker and delivered attempt.
- Messages are length-limited, rate-limited, redacted for display and never
  interpreted as shell.
- While a job is `RUNNING`, the monitor clearly says the message will be delivered
  on the next resume, not injected live.
- On resume, queued messages are composed into the resume prompt with an explicit
  owner-follow-up header. The prompt says: continue the authorized task, preserve
  the working tree, do not expand scope, and finish with verifiable evidence.
- Delivery is exactly once per message per resume attempt; delivered messages are
  marked and shown as history. Failed resume attempts do not lose the queue.
- Phase 3 adds `dev resume --prompt-file -`, so composed owner instructions are
  passed over standard input rather than the process argument list.

Agent to owner:

- Lifecycle events, detected issues, `BLOCKED:` markers and report sections are
  surfaced as notifications.
- A blocked or permission-rejected job shows a "Needs owner input" card with
  buttons to view the report, queue an instruction, resume or cancel.
- An optional Phase 4 read-only "latest agent message" view may use
  `session_state.load_export` through the existing read-only helper. It must be
  bounded, redacted, feature-flagged and never used to write the session.

Explicitly rejected approaches:

- writing OpenCode's SQLite database directly;
- starting `opencode serve`, `opencode web` or `opencode acp`;
- using `--auto` to force autonomy;
- injecting text into a running process's standard input;
- executing owner message text as a shell command.

### 5.12 Per-project job serialization

Two different serialization layers must not be confused:

1. **Global guard lock (existing):** at most one heavyweight OpenCode execution
   at a time across all projects.
2. **Per-project admission (new monitor rule):** at most one active monitor-managed
   job per registered project.

The per-project rule exists to protect the project working tree and session from
races between two nearly simultaneous owner actions, even though the global guard
would eventually serialize them.

Project key resolution:

```text
repo_real = realpath(job.repo)
if repo_real exactly matches a registered project's repository realpath:
    key = that project ID
else:
    key = "repo:" + sha256(repo_real)
```

Admission algorithm:

```text
with flock(monitor/locks/project-<sha256(key)>.lock, timeout=5s):
    active = jobs where state == RUNNING and worker_is_alive(job)
             and project_key(job) == key
    if active:
        reject with "project busy" and offer the active job
        optionally save one queued request (manual confirmation only)
    else:
        invoke dev start or dev resume
```

The lock is held only for the check-and-invoke critical section, not for the whole
job. The durable source of truth is the job store scan; the lock prevents two
Telegram handlers from racing. The global guard remains authoritative.

Queue semantics:

- At most one saved start request per project.
- The queue does not auto-start. When the active job ends, the monitor notifies the
  owner that the project is free and asks for confirmation. This preserves the
  control-plane rule that the owner starts work; the monitor is not a scheduler.
- A queued request expires after a configurable interval and is shown with its
  expiry.

Hard guarantee boundary:

- This design serializes monitor-initiated jobs. A job started directly from the
  CLI at the same moment is still protected by the global guard, but not by the
  monitor's project lock.
- A later additive v3 per-repository lock in the worker (state-root lock keyed by
  canonical repository path) is recommended for a hard cross-client guarantee. It
  must be a separate, tested change and must not alter existing job semantics.

### 5.13 Read-only document browsing and download

Visible roots are explicit and normally derived from the registry:

- each registered project's central report root, for example
  `/home/iffi/dev-workspace/docs/Blogs`;
- `/home/iffi/dev-workspace/docs/workspace`;
- optionally `/home/iffi/dev-workspace/docs/references`;
- optionally `/home/iffi/dev-workspace/control-plane/docs` for operations
  runbooks.

The monitor does not expose `/home/iffi/dev-workspace/docs` as a generic root by
default, because it contains unregistered directories and Git metadata.

Browsing:

- Project roots are shown as top-level buttons.
- Directories are listed with directories first, then files; pagination defaults
  to 8-10 entries per page.
- Hidden components and `.git`/`.githooks` are excluded.
- Symlinks are excluded from listings and refused on open.
- A file preview shows a redacted text head, size, relative path and available
  actions.
- Inline preview is text only. Binary files are download-only and disabled by
  default.

Safe resolver requirements:

1. Resolve the configured root once at startup and open it with
   `O_RDONLY | O_DIRECTORY | O_NOFOLLOW`. Refuse if the root is a symlink or not a
   directory.
2. Accept only relative paths. Reject absolute paths, NUL, backslash, empty
   components, `.`, `..`, percent-encoded traversal and too many components.
3. Walk each component with `os.open(component, O_RDONLY | O_DIRECTORY |
   O_NOFOLLOW | O_CLOEXEC, dir_fd=fd)`. This rejects symlinked directories at
   every level.
4. Open the final component with `O_RDONLY | O_NOFOLLOW | O_CLOEXEC` and
   `fstat`. Require `S_ISREG`; reject directories, sockets, FIFOs, devices and
   symlinks.
5. Enforce a maximum size before reading. Read through the descriptor; do not
   re-open by path after validation.
6. For listings, use the validated directory descriptor and exclude entries whose
   `is_symlink()` is true.
7. Never construct a new path from the raw user string after validation.

Denied names and types by default:

- `.git`, `.githooks`, all dotfiles and dot-directories;
- `.env`, `.env.*`, `*.pem`, `*.key`, `*.p12`, `*.pfx`, `*.jks`, `*.kdbx`,
  `id_rsa*`, `id_ed25519*`;
- directories or files named `secrets` or `credentials`;
- executables, shared libraries, archives, sockets, FIFOs and device nodes;
- SVG and HTML downloads (script-bearing formats);
- files above the configured caps.

Download policy:

- Text-like files (`.md`, `.txt`, `.json`, `.jsonl`, `.log`, `.csv`, `.yaml`,
  `.yml`) are offered as a redacted text copy with a `.redacted` marker in the
  caption. The source file is never modified.
- Raster images and PDFs are download-only, disabled by default. If the owner
  enables binary downloads, require a per-file confirmation, an extension
  allowlist and the size cap.
- File names are sanitized for display and `sendDocument`; no control characters,
  path separators or misleading extensions.
- The monitor never writes into the docs tree. Redacted text copies are built in
  memory or in the private monitor state directory and deleted after send.

Residual risks:

- A malicious hardlink inside an owner-controlled docs root can point to data
  outside the root; descriptor validation cannot distinguish it by path. The docs
  root is owner-controlled and not writable by untrusted users. For stronger
  isolation, the owner may later mount or bind the docs tree read-only; that is a
  VPS/owner action, not a bot action.
- Redaction is pattern-based. It catches common credential shapes, not arbitrary
  secrets. The docs policy and owner-only chat remain authoritative.

## 6. API boundaries

### 6.1 Boundary table

| Boundary | Direction | Allowed operations | Notes |
| --- | --- | --- | --- |
| Telegram Bot API | outbound | `getMe`, `getUpdates`, `sendMessage`, `editMessageText`, `answerCallbackQuery`, `sendDocument`, `deleteMessage`, `setMyCommands`, optional `deleteWebhook` | HTTPS only; no webhook; no inbound listener |
| Workflow v3 CLI | subprocess | `dev start`, `dev status`, `dev report`, `dev logs`, `dev resume`, `dev accept`, later `dev cancel` | `shell=False`, fixed argv shape, `--json` preferred |
| Job store | read-only | `job.json`, `events.jsonl`, `run.log`, `worker.log`, `report.md`, `acceptance-*.log` | Validate job ID; derive paths; redact output |
| Project registry | read-only | parse registered table and central roots | Never write; fail closed on start/resume |
| Central docs | read-only | list, preview, download | Descriptor-based resolver; no writes |
| Monitor state | read/write | offsets, cursors, wizard state, nonces, audit, queues | Private `0700`/`0600`; SQLite |
| Process control | constrained | later `dev cancel` only | No generic `kill`; no name-based signalling |
| OpenCode session | read-only optional | `opencode export` via `session_state` | No SQLite access; no serve/web/acp |
| OS `/proc` | read-only | PID/cmdline/liveness checks | Never signal by name; never touch Qortium |

### 6.2 Workflow v3 CLI contract used by the monitor

Rules:

- Invoke with `sys.executable` and the absolute `tools/dev.py` path.
- Pass `--state-dir` only when the monitor uses a non-default state root; keep the
  monitor and CLI roots identical.
- Use `--json` on every call that supports it.
- Set `DEV_CONTROL_PLANE_STATE` explicitly in the child environment when needed.
- Disable existing final notifications for monitor-started jobs with
  `--no-notify`.
- Never invoke `_worker`.
- Never concatenate user text into a shell string.
- Parse stdout as JSON; treat non-JSON output as an error and show a sanitized
  diagnostic.
- Apply a bounded subprocess timeout and capture output with size caps.

Monitor facade, proposed:

```text
list_jobs() -> list[JobStatus]
job_status(job_id) -> JobStatus
job_report(job_id) -> ReportText
job_log(job_id, kind, max_bytes) -> str
start_job(StartRequest) -> JobResult
resume_job(job_id, prompt, timeout_seconds) -> JobResult
accept_manual(job_id, criterion_ids, note) -> JobResult
cancel_job(job_id) -> JobResult        # Phase 3 only
```

### 6.3 Job store read contract

- Validate the job ID against `list_jobs()` or the monitor index; never pass a raw
  Telegram string to a path.
- Use the job directory returned by the store contract. For known artifacts,
  derive `run.log`, `worker.log`, `report.md` and `events.jsonl` from that
  directory rather than trusting absolute paths in `job.json`.
- Treat `job.json` as eventually consistent: the worker writes it atomically, but
  a read can land between attempts. Prefer `dev status --json` for authoritative
  reconciliation and use `job.json` only for fields not exposed by status.
- Read `events.jsonl` with a cursor and a bounded read. Do not load an unbounded
  file into memory.
- If the job directory disappears, drop the index entry and tell the owner,
  rather than recreating it.

### 6.4 Telegram Bot API contract

- Base URL is HTTPS. A configurable base is allowed only for tests on loopback;
  production validation rejects non-HTTPS.
- `getUpdates` uses an offset, a timeout of 20-30 seconds and an explicit allowed
  update list (messages and callback queries).
- Callback queries in a fetched batch are acknowledged before any handler runs,
  with a short acknowledgement timeout. A stale, rejected, timed-out or
  network-failed acknowledgement is best-effort: it is audited and the
  associated action still executes. One slow acknowledgement must not block the
  rest of the batch.
- The token is part of the request URL. It must never appear in logs, exceptions,
  audit records or chat messages.
- Handle:
  - `409 Conflict`: another poller or webhook is active; fail closed.
  - `401 Unauthorized`: token invalid; stop and instruct the owner to fix config.
  - `429 Too Many Requests`: honor `retry_after`, back off, do not drop updates.
  - `5xx`, timeouts and connection errors: exponential backoff with jitter.
- `sendDocument` uses multipart upload from a validated descriptor or in-memory
  redacted bytes; it never opens an arbitrary path.
- `setMyCommands` is optional and idempotent. The monitor does not change bot
  privacy settings silently.
- No `getFile` download of remote Telegram files is needed for the initial
  design.

### 6.5 Document resolver contract

```text
list_documents(root_id, relative_dir, page) -> DocumentListing
preview_document(root_id, relative_file, max_bytes) -> TextPreview
open_download(root_id, relative_file, max_bytes) -> DownloadHandle
```

`DownloadHandle` exposes a validated descriptor, sanitized name, detected text or
binary kind, size and a redaction path for text. The caller cannot request an
arbitrary filesystem path.

### 6.6 Monitor state schema

SQLite is used with the standard library. Suggested tables:

```text
meta(key, value)
seen_updates(update_id PRIMARY KEY, received_at)
jobs(job_id PRIMARY KEY, short_id, project_id, chat_id, status_message_id,
     last_state, updated_at)
message_refs(job_id, chat_id, kind, message_id, updated_at,
             PRIMARY KEY(job_id, chat_id, kind))
event_cursors(job_id PRIMARY KEY, inode, offset, last_event_hash)
wizards(wizard_id PRIMARY KEY, user_id, chat_id, state_json, created_at, expires_at)
browses(browse_id PRIMARY KEY, user_id, chat_id, root_id, rel_dir, page, created_at)
confirmations(nonce PRIMARY KEY, user_id, chat_id, action, payload_json,
              created_at, expires_at, used_at)
owner_messages(message_id PRIMARY KEY, job_id, user_id, chat_id, body,
               created_at, delivery_state, delivered_at, delivered_attempt,
               last_error_redacted)
project_queue(queue_id PRIMARY KEY, project_id, payload_json, created_at,
              expires_at, state)
audit(id PRIMARY KEY, ts, user_id, chat_id, update_id, action, job_id,
      result, detail_redacted)
rate_limits(bucket PRIMARY KEY, window_start, count)
```

Properties:

- Database and directory are `0600`/`0700`.
- Writes use short transactions and `WAL` only if needed; single-writer loop.
- Store no full message bodies except explicitly queued owner instructions.
- Audit records contain identifiers, action, result and a short redacted detail,
  never raw prompts, logs or tokens.
- Wizard, browse and confirmation entries expire and are garbage-collected.

## 7. Security design

### 7.1 Threat model

| Threat | Example | Primary controls |
| --- | --- | --- |
| Unauthorized Telegram user | Stranger messages the bot | Numeric user/chat allowlist; private chat only; generic denial; optional unlock |
| Stolen Telegram session | Account compromise | Allowlist, optional local passphrase, short unlock window, confirmations, audit |
| Callback tampering | Forged callback data | Server-side opaque IDs; re-authorize every callback; nonce bound to user/chat/action; expiry; one-time use |
| Replay | Re-sent update ID | Update deduplication; offset persisted after handling; idempotent handlers; one-time nonces |
| Command injection | Prompt or title treated as shell | `shell=False`; argv arrays; prompt over stdin; fixed command shapes; no shell surface |
| Path traversal | `../../etc/passwd` | Reject absolute/`.`/`..`/encoded traversal; descriptor walk |
| Symlink escape | Symlink inside docs root to outside | `O_NOFOLLOW` on every component; regular files only; listings exclude symlinks |
| Secret leakage | Token in log, error or report | Redaction at render boundary; sanitized exceptions; no raw message logging; token never printed |
| Prompt/command logging | v3 stores prompt and guard command | Display redaction; later v3 hardening to reduce persistence |
| Arbitrary repository | Start a job in `/etc` | Registered project only; repository root allowlist; realpath check |
| PID reuse / wrong signal | Cancel signals wrong process | Additive `dev cancel` revalidates cmdline/job identity; never signal by name |
| Concurrent same-project jobs | Two starts race | Per-project admission lock plus durable active-job scan; global guard |
| Resource abuse | Spam starts or huge files | Rate limits, max starts/hour, size caps, pagination, one global execution |
| Telegram/API outage | 429 or timeout | Backoff, retry_after, durable offset, no lost updates |
| Docs overexposure | Unregistered/private directory | Explicit root allowlist; no generic docs root listing |
| Local multi-user exposure | Another local user reads state | `0700` directories, `0600` files; OS account remains the real boundary |
| Qortium/VPS mutation | Bot becomes a control plane for the host | No host commands; no service/system access; only constrained v3 CLI |

### 7.2 Authorization details

- `authorized_user_ids` and `allowed_chat_ids` are mandatory, non-empty integer
  lists. The monitor refuses to start if either is missing.
- `chat.type == "private"` is mandatory. Groups and channels are rejected even if
  an allowlisted user posts there.
- The monitor does not trust `message.from.is_bot`, forwarded metadata, contact
  cards or usernames.
- Every callback rechecks both IDs. Callback data is never an authorization token.
- Confirmation nonces include the action, a hash of the payload, user ID, chat ID
  and expiry. They are single-use and invalidated on any state change.
- Optional unlock uses a salted password hash configured outside Git. Unlock
  state is per user/chat and expires (for example 15 minutes). Re-lock on
  `/lock`, mode change or process restart.
- Denied actions produce a generic message and a sanitized audit entry. They do
  not reveal job names, paths, project IDs or configuration.

### 7.3 Input validation and no-shell rule

- Every mutating action has a fixed command shape. Only a small set of typed
  values can vary: title, prompt, criteria, timeout, branch label, project ID,
  job ID and resume text.
- Project ID must match a parsed registry entry. Job ID must match the monitor
  index. Timeout is parsed as an integer and capped at eight hours.
- Agent and model are selected from config allowlists, not free text.
- Prompt text is written to `dev start` through `--prompt-file -`, not an
  argument.
- Resume text is passed over stdin with `dev resume --prompt-file -` to avoid
  long-argument exposure. The P2 one-argv-element form remains supported.
- The monitor never calls `bash -c`, `sh -c`, `eval`, `exec` or a shell wrapper for
  its own operations.
- Acceptance commands are the one intentional shell surface, because Workflow v3
  executes them with `bash`. The monitor displays them verbatim before
  confirmation and warns that they run in the selected repository.
- File names, titles and note text are stripped of control characters before
  rendering.

### 7.4 Path traversal and symlink escape design

The resolver is the only path authority. It never trusts a Telegram string or a
job-record path. The algorithm is:

```text
root_fd = open(configured_root, O_RDONLY|O_DIRECTORY|O_NOFOLLOW)
for component in validated_relative_components:
    next_fd = open(component, O_RDONLY|O_DIRECTORY|O_NOFOLLOW|O_CLOEXEC,
                   dir_fd=current_fd)
file_fd = open(final_component, O_RDONLY|O_NOFOLLOW|O_CLOEXEC,
               dir_fd=parent_fd)
st = fstat(file_fd)
require S_ISREG(st.st_mode)
require st.st_size <= configured_cap
read from file_fd only
```

Validation rejects:

- empty paths and paths with NUL;
- absolute paths and drive-like prefixes;
- backslashes;
- `.` and `..` components at any depth;
- percent-encoded traversal patterns;
- too many components or too much depth;
- hidden components;
- denied names and extensions;
- symlinks at any component;
- non-regular final files.

The monitor additionally checks that the resolved root itself is a real directory
and is under an allowed workspace root. It never follows a root symlink. It
rechecks the root at startup and refuses if the configured root disappears or is
replaced by a non-directory.

### 7.5 Credential redaction

Redaction is applied at every outbound render boundary:

- Telegram messages;
- edited status messages;
- log and report previews;
- text attachments;
- audit detail;
- exception text;
- doctor/check output.

Baseline patterns:

- the configured bot token, replaced exactly;
- Telegram bot-token shapes;
- `Authorization: Bearer ...` values;
- assignments for token, secret, password, passphrase, API key, access token,
  auth token and client secret;
- environment-style `NAME=value` lines for sensitive names;
- GitHub, AWS, Slack and OpenAI-style token shapes;
- PEM private-key blocks;
- URLs containing user information;
- long random-looking values adjacent to a sensitive key.

Additional rules:

- Redact before truncation, then cap, so a token cannot be cut into a
  non-matching fragment.
- Never log the raw update object or message body. Log update ID, user ID, chat
  ID, action, job ID and result only.
- Wrap HTTP errors and sanitize the URL because the token is in the request path.
- Store the token only in the owner-local config or environment. Never write it to
  monitor state, job state, reports, audit or Git.
- Provide a test fixture for every pattern and for the leak paths: API error,
  job log, report, acceptance output, audit entry and document preview.
- Redaction is best-effort. The owner must not send secrets in prompts or docs,
  and the docs root must follow the central report policy.

### 7.6 Qortium and VPS boundaries

The monitor process must never:

- run `sudo`, `su`, service managers with mutating verbs, `systemd-run`,
  `crontab`, `at` or a global package manager;
- start, stop, restart, reconfigure, signal or delete the Qortium node, its
  service, JAR, data directory, database, configuration or logs;
- change VPS networking, firewall, mounts, kernel modules, system packages or
  system services;
- create an inbound listener or webhook;
- write to `/home/iffi/qortium-preview/**` or `/home/iffi/qortium-data/**`;
- use SSH to bypass these limits on a remote host.

Allowed read-only diagnostics, if ever needed by a separate owner action, remain
the same as the control-plane contract: `systemctl status`, `journalctl` reads,
`ps` for a specific PID, and file reads. The monitor itself does not need any of
them; it does not inspect the node.

The only process signal the monitor may request is through the later `dev cancel`
command, which is part of the tested guard boundary and targets the exact guard
it owns for that job. Name-based `kill`, `pkill`, `killall` and
`tmux kill-server` are never used.

### 7.7 Replay, idempotency and rate limits

- `seen_updates(update_id)` is checked and inserted before side effects. A
  duplicate update is acknowledged without re-running the action.
- Offset is advanced after successful handling, a bounded dead-letter, or an
  outbound Telegram failure that happened while attempting the action. The
  update stays durably claimed in the last case, so a reconnect or restart
  acknowledges the redelivery without replaying a partially committed action.
  This is at-most-once action semantics, not exactly-once message delivery.
- A poll-level `getUpdates` failure does not claim any update; the offset stays
  unmoved and the loop backs off, so those updates are fetched again. An
  in-handler transport failure triggers the same backoff after the action is
  marked handled.
- Batch callback acknowledgement is best-effort UI work, not action processing.
  A failed acknowledgement neither releases an update nor aborts the actions of
  the remaining authorized callbacks.
- Distinct update IDs are distinct deliveries even when the owner sent the same
  `/start` or `/menu` command twice; that is a duplicate command, not duplicate
  processing. Only a repeated update ID is suppressed by `seen_updates`.
- Start/resume uses a confirmation nonce and a project admission lock. A replayed
  confirm cannot create a second job.
- Queued owner messages are delivered with a `delivered_attempt` marker; a retry
  of the same resume does not duplicate them.
- Per-user rate limit (for example 30 actions per minute), per-chat message rate,
  maximum starts per hour (for example 6) and maximum queued starts (one per
  project).
- Telegram 429 responses are respected globally and per chat.

### 7.8 Data protection

- Monitor state directory `~/.local/state/dev-control-plane/monitor/` mode `0700`.
- SQLite database, lock, log and audit files mode `0600`.
- Config file `~/.config/dev-control-plane/telegram.json` mode `0600`; the monitor
  refuses unsafe permissions rather than only warning.
- No prompt bodies in audit. Queued owner instructions are stored because they
  must survive restart; they are still private state and are deleted after a
  configurable retention period.
- Log rotation is owner-configured; the monitor writes bounded records and never
  grows an unbounded debug log.
- The monitor state can be deleted to reset UI state without affecting jobs.
- The monitor does not back up or copy job credentials or docs content.

### 7.9 Residual risks

- The monitor runs as the owner's OS user. It has the same filesystem authority as
  that user; the constrained API is a policy boundary, not an OS sandbox.
- Pattern-based redaction cannot catch every possible secret.
- A compromised Telegram account with an unlocked control session can perform
  authorized actions. Telegram 2FA and the optional local passphrase are the
  mitigations.
- True live agent conversation is unavailable until OpenCode provides a supported
  control channel. The design intentionally does not invent one.
- Hardlink escapes from the docs root are a residual risk as described above.
- The monitor's per-project lock does not cover a simultaneous CLI-started job; the
  global guard still serializes execution, and a future v3 per-repository lock is
  the hard fix.
- Telegram retains messages on its servers. The owner should treat the chat as a
  sensitive but external surface.

## 8. Implementation phases and dependencies

### 8.1 Phase table

| Phase | Scope | Mutates jobs | Changes v3 | Exit criteria |
| --- | --- | --- | --- | --- |
| P0 | Audit and architecture (this document) | No | No | Document reviewed; no code changes; validators pass |
| P1 | Read-only observer: config, auth, long polling, state, redaction, menus, job list/status/logs/report, project list, doc browser | No | No | Unauthorized users denied; read-only flows pass; no listener; no secrets |
| P2 (implemented) | Control: start wizard, resume, per-project admission, STARTED/RESUMED, final relay, confirmations, optional unlock | Yes, through existing CLI | No | Start/resume acceptance passes; concurrency tests pass; no duplicate notifications |
| P3 (implemented) | Cancel and owner messaging: additive `dev cancel`, optional `dev resume --prompt-file -`, queued instructions | Yes | Additive only | Separate authorization; v3 regression tests; cancel safety tests; queue exactly-once |
| P4 (implemented) | Hardening and operations: docs download policy, rate limits, incident runbook, real-runtime acceptance | No new semantics | No | Security acceptance matrix passes; owner accepts real bot flow |
| P5 (optional) | Advanced: latest assistant message view, richer queues, multi-chat, search | Maybe | Additive | Separate owner decision and scope |

### 8.2 Phase details

P1 — read-only observer:

- `config.py`: read the existing Telegram config, validate mode and authorization.
- `api.py`: implement outbound long polling, error handling and no webhook.
- `state.py`: SQLite offsets, message refs, audit.
- `auth.py`: numeric allowlist; deny groups and unknown users.
- `projects.py`: registry parser and root validation.
- `documents.py`: safe resolver and listing.
- `render.py` and `menus.py`: main menu, jobs, projects, documents.
- No `dev start`, `dev resume`, `dev cancel`, `dev accept` or owner-message
  delivery in this phase.
- Tests: auth, traversal, symlink, redaction, update deduplication, API fault
  handling.

P2 — control:

- Start wizard with confirmation and exact summary.
- Resume flow with queue preview and explicit `--new-session`/`--force`
  confirmation.
- Per-project admission lock and durable active-job scan.
- Event watcher for STARTED/RESUMED and terminal dedupe.
- Optional local unlock.
- `dev start --no-notify` for monitor-started jobs.
- Tests: start via fake CLI, resume, concurrency, duplicate confirms, notification
  dedupe, real-runtime owner acceptance.

#### P2 implementation notes (2026-10-31)

The implemented P2 surface is deliberately smaller than a general job console:

- `mode: "control"` is required; `read_only` remains the default and exposes no
  start or resume action.
- Control mode must also configure non-empty `agent_allowlist` and
  `model_allowlist`. The wizard uses only those values.
- The start wizard selects a registered, job-eligible project by server-side
  index, then collects title, prompt, at least one command or manual criterion,
  timeout and optional branch label before a one-time confirmation nonce.
- `dev start` is invoked with `--no-notify --json`, the exact fixed argument
  shape from section 5.5, and the prompt over stdin. `dev resume` uses
  `--prompt` as one argv element in P2; P3 uses the additive
  `--prompt-file -` form.
- Per-project admission uses `monitor/locks/project-<sha256>.lock` held only for
  the check-and-invoke section. A running job in another project is reported as
  global-guard busy rather than creating a doomed attempt.
- STARTED/RESUMED and terminal notifications are claimed in durable
  `notification_log` rows before sending. Existing Workflow v3 terminal
  notifications remain authoritative for CLI-started jobs; monitor-started jobs
  (`--no-notify`) get exactly one terminal relay.
- The optional local passphrase uses a salted scrypt hash in owner-local config,
  an in-process unlock window and `/unlock`/`/lock`. Passphrases are never stored
  in monitor state or audit rows. Restarting the monitor re-locks control.
- The P3 cancel and owner-to-agent queued messaging extensions are described
  below. In P2-only deployments, `/cancel` cancelled only an active wizard.

P3 — cancel and messaging (implemented 2026-11-01):

- Separate owner authorization to modify Workflow v3 was granted by the P3 task.
- `CANCELLED` is an additive terminal state in `store`, `notify`, `status`,
  report rendering and tests.
- `dev cancel` verifies the recorded guard against `/proc/<pid>/cmdline`, writes
  a durable attempt-scoped cancel marker and sends `SIGTERM` to that exact PID.
  It never signals by name and never escalates during the bounded grace period.
- `dev resume --prompt-file -` passes long owner instructions over stdin.
- Queued owner messages are stored in monitor SQLite with explicit
  `queued`/`delivered` state and `delivered_attempt`; they are composed into the
  resume prompt and marked delivered only after Workflow v3 accepts the resume.
  A failed resume leaves the queue intact.
- A job with no known OpenCode session still requires the explicit New session
  toggle before resume.
- Regression tests cover existing start/status/report/logs/resume/accept
  behaviour, cancel safety, queue exactly-once delivery and notification dedupe.
- The monitor exposes cancel only in control mode and only for a RUNNING job with
  a live worker.

P4 — hardening and operations (implemented 2026-11-01; owner acceptance pending):

- Detector regression: a Python/Node `FileNotFoundError` or a bare
  `No such file or directory` for an ordinary data file is classified as a
  failed command, not `missing_dependency`. Shell-style exec failures,
  `command not found`, missing modules and `missing dependency` text remain
  blocking. The P3 job
  `20261101T061959Z-qortium-dev-monitor-p3-961a2a11` had been falsely blocked by
  a cancel-test traceback naming a missing fixture `job.json`; the underlying
  test failure was real and was fixed, but its classification was wrong.
- Lifecycle STARTED/RESUMED/terminal and alert notifications now pass through
  the same credential redaction boundary as interactive messages.
- Per-user and per-chat action budgets plus an hourly start cap are enforced in
  durable monitor state. Confirmation nonces are claimed atomically, and a job
  artifact path is rejected if the job directory is a symlink or resolves
  outside the job store.
- `tools/test_dev_monitor_p4.py` adds isolated authorization, replay,
  rate-limit, document fuzzing, symlink-swap, redaction, restart-persistence,
  polling fault-injection, atomic-claim and fake-CLI start/queue/cancel/resume
  integration tests. The detector regression is covered in `test_detect.py`.
- The English runbook includes incident response, token rotation and the
  [real-runtime owner acceptance checklist](QORTIUM-DEV-MONITOR-P4-ACCEPTANCE.md).
- P4 adds no new job semantics, no listener, no Qortium/VPS change and no
  automatic scheduler. Real-runtime R-01 through R-16 remain owner-executed.

P5 — optional advanced:

- Read-only latest assistant message via `session_state.load_export`.
- Project queues with explicit owner confirmation (still no scheduler).
- Search within allowlisted docs.
- Multi-chat or multi-owner support only with an explicit authorization model.

### 8.3 Dependencies

| Dependency | Needed by | Notes |
| --- | --- | --- |
| Python 3.11+ standard library | all phases | Verified environment is Python 3.13; no new pip packages |
| Existing `tools/dev.py` and `tools/devjob/*` | P1-P2 | No modification in P1-P2 |
| Existing execution guard | P1-P2 | Remains the only execution authority |
| Existing final notification config | P1-P2 | Reuse token/chat; add a nested monitor config object |
| Registered project repository paths | P2 | From `PROJECT-REGISTRY.md`; must exist |
| Central docs roots | P1 | Explicit allowlist; read-only |
| Telegram bot token and owner IDs | P1 | Owner-local config, mode `0600` |
| Owner acceptance | P2-P4 | Real bot, real job, no committed credentials |
| Separate authorization for v3 changes | P3 | Required before adding `dev cancel` or `--prompt-file` for resume |

### 8.4 Rollout and feature flags

- Start with `mode: read_only`.
- Enable control mode for one owner/chat only.
- Enable start before resume; enable resume before cancel.
- Keep `allow_binary_downloads: false` until the owner explicitly needs it.
- Keep `auto_start_queued: false`; there is no scheduler.
- If anything fails, switch back to read-only without stopping jobs.

## 9. Acceptance tests

### 9.1 Automated test matrix

The monitor must be tested without contacting production Telegram and without
starting a real model session. Use a fake Telegram transport or a loopback-only
fake API, a disposable state directory, a fake `dev` CLI, and a temporary docs
tree.

| ID | Area | Test | Expected result |
| --- | --- | --- | --- |
| T-AUTH-01 | Authorization | Authorized user in an allowed private chat sends `/start` | Main menu returned |
| T-AUTH-02 | Authorization | Unknown numeric user ID sends any command | Generic denial; no job, path or config details |
| T-AUTH-03 | Authorization | Allowed user posts in a group/channel | Rejected; no action |
| T-AUTH-04 | Authorization | Callback from unauthorized user or wrong chat | Rejected before state lookup |
| T-AUTH-05 | Authorization | Expired, reused or tampered confirmation nonce | Rejected; no side effect |
| T-AUTH-06 | Authorization | Callback data changed to another job index | Only the caller's authorized state is resolved; mismatch rejected |
| T-REPLAY-01 | Idempotency | Same update ID delivered twice | Action runs once; duplicate acknowledged |
| T-REPLAY-02 | Idempotency | Confirm start twice with the same nonce | Exactly one job created |
| T-REPLAY-03 | Idempotency | Redelivery after an in-handler Telegram timeout or restart | No second action; the claimed update is only acknowledged |
| T-CALLBACK-01 | Callback acknowledgement | First acknowledgement in a batch times out | Remaining acknowledgements and every callback action still run once |
| T-JOB-16 | Refresh | Job status text and markup are unchanged | Telegram "message is not modified" becomes explicit "No changes" feedback |
| T-RATE-01 | Abuse | Exceed per-user action rate | Rate-limit response; no state change |
| T-RATE-02 | Abuse | Telegram returns 429 with `retry_after` | Waits, retries, does not drop the update |
| T-JOB-01 | Start | Wizard without acceptance criteria | Refused before CLI invocation |
| T-JOB-02 | Start | Wizard with a repository outside the registry | Refused; no CLI call |
| T-JOB-03 | Start | Valid project, prompt, criteria, confirm | `dev start` invoked with fixed argv; STARTED only for `RUNNING` |
| T-JOB-04 | Start | Guard preflight returns REFUSE | BLOCKED shown; no STARTED |
| T-JOB-05 | Status | Running job with pending criteria and issues | Status shows state, timing, attempt, PIDs, criteria, sanitized issues |
| T-JOB-06 | Status | Worker disappears | `dev status` reconciliation is surfaced; WORKER LOST alert |
| T-JOB-07 | Logs | Read run/worker logs | Bounded, redacted, paginated output; no absolute-path traversal |
| T-JOB-08 | Report | Render/report and download | Bounded summary; redacted text attachment; source unchanged |
| T-JOB-09 | Resume | Terminal job with known session | RESUMED sent; same job ID and session used |
| T-JOB-10 | Resume | RUNNING live job | Refused; no duplicate attempt |
| T-JOB-11 | Resume | Unknown session without confirmation | Refused; `--new-session` offered only as explicit opt-in |
| T-JOB-12 | Admission | Two simultaneous starts for one project | Exactly one starts; the other is rejected or queued |
| T-JOB-13 | Admission | Start for project B while project A runs | Blocked by the global guard or reported as busy; no bypass |
| T-JOB-14 | Final dedupe | CLI-started job already has a sent final notification | Monitor does not duplicate it |
| T-JOB-15 | Final dedupe | Monitor-started job (`--no-notify`) reaches terminal state | Monitor sends exactly one final message |
| T-CANCEL-01 | Cancel (P3) | Cancel a RUNNING job with a verified guard | Guard receives SIGTERM; child group stops; state CANCELLED |
| T-CANCEL-02 | Cancel (P3) | Guard PID does not match the job | Refused; no signal |
| T-CANCEL-03 | Cancel (P3) | Cancel when worker is already gone | No signal; reconcile and explain |
| T-MSG-01 | Messaging | Queue while RUNNING, then resume | Message appears in resume prompt; delivered once; marked delivered |
| T-MSG-02 | Messaging | Attempt live injection | UI states "next resume"; no OpenCode DB/server write |
| T-MSG-03 | Messaging | Oversized or abusive message | Truncated or rejected; rate limit applies |
| T-DOC-01 | Docs | List allowlisted roots | Registered roots, workspace and references only |
| T-DOC-02 | Docs | `../`, absolute, backslash and encoded traversal | Rejected before filesystem access |
| T-DOC-03 | Docs | Symlink file and symlink directory to outside root | Rejected; no read |
| T-DOC-04 | Docs | Hidden, `.git`, `.env`, key and credential names | Not listed; open refused |
| T-DOC-05 | Docs | FIFO, device, socket, executable | Rejected as non-regular/disallowed |
| T-DOC-06 | Docs | Oversized file | Rejected with a size message; no unbounded read |
| T-DOC-07 | Docs | Text preview/download | Redacted copy; source file unchanged |
| T-DOC-08 | Docs | Binary download disabled | Not offered; no Telegram upload |
| T-DOC-09 | Docs | No writes | Directory and file metadata remain unchanged after browsing |
| T-RED-01 | Redaction | Bot token, bearer, env secret, key marker, common token shapes | All redacted in messages, logs, audit, reports and errors |
| T-RED-02 | Redaction | Telegram API error contains the request URL | URL/token redacted; only sanitized reason shown |
| T-RED-03 | Redaction | Prompt/report/log fixtures contain secrets | No secret reaches outbound text or persisted audit |
| T-OPS-01 | Network | Start monitor and inspect sockets | No LISTEN socket; long polling only |
| T-OPS-02 | Network | Webhook already configured | Monitor fails closed with a sanitized conflict message |
| T-OPS-03 | Restart | Restart monitor after STARTED | Offset and event cursor restored; no duplicate STARTED |
| T-OPS-04 | Config | Config file mode is group/world readable | Refuses to start (or refuses control mode) with clear guidance |
| T-OPS-05 | Config | Missing token or empty user allowlist | Refuses to start; no polling |
| T-OPS-06 | Safety | Static scan of monitor source | No `sudo`, service mutation, name-based kill, shell wrapper or Qortium path writes |
| T-OPS-07 | Safety | Monitor attempts no Qortium API or file write | No node access in tests or traces |
| T-OPS-08 | Resilience | Telegram 5xx/timeout during poll or handler | Backoff; process stays alive; polled updates are retried and in-handler updates are not replayed |
| T-OPS-09 | Resilience | Corrupt job file or deleted job dir | Sanitized error; monitor continues serving other jobs |
| T-OPS-10 | Shutdown | Stop flag written | Monitor exits gracefully; running jobs continue |

### 9.2 Real-runtime owner acceptance

These require the owner's real bot, real Telegram account and the VPS. They are
not committed credentials and are not part of CI. The maintained P4 checklist
with preflight, evidence capture and sign-off is
[QORTIUM-DEV-MONITOR-P4-ACCEPTANCE.md](QORTIUM-DEV-MONITOR-P4-ACCEPTANCE.md).

| ID | Scenario | Expected evidence |
| --- | --- | --- |
| R-01 | Authorized owner opens `/start` | Menu works; mode is visible; no secret in messages |
| R-02 | Unauthorized second account messages the bot | Generic denial; owner gets no job data |
| R-03 | Start a small authorized job through the bot | STARTED arrives; status shows attempt #1; logs and report open |
| R-04 | Let the job reach a terminal state | Final message is sent exactly once; existing CLI notification is not duplicated |
| R-05 | Resume the job with a queued instruction | RESUMED arrives; attempt #2; queued text is present in the report/prompt evidence |
| R-06 | Cancel a running job (after Phase 3) | Only that guard's child group stops; worktree preserved; CANCELLED shown; resume still works |
| R-07 | Browse and download a report | Only allowlisted docs are visible; text preview is redacted; file is readable |
| R-08 | Attempt traversal and symlink paths | Both refused; audit records the refusal without content |
| R-09 | Restart the monitor during a running job | Job continues; monitor recovers; no duplicate lifecycle messages |
| R-10 | Inspect VPS and Qortium before/after | No new listener; no service change; Qortium PID/RSS unchanged |
| R-11 | Rotate the bot token | Old token fails; new config works after restart; no token in logs |
| R-12 | Verify shutdown | Monitor stops gracefully; running jobs are unaffected |

### 9.3 Definition of done for the monitor implementation

- All automated tests pass.
- Real-runtime acceptance R-01 through R-12 has owner evidence, except items
  explicitly deferred to Phase 3.
- No new listening socket exists.
- No Qortium or VPS setting changed.
- No credential appears in any committed file, message, log, report or audit.
- Workflow v3 regression tests pass unchanged for P1-P2.
- Phase 3 v3 changes have their own exact diff, tests and authorization.
- The implementation report is stored under the central docs workspace tree with
  the exact application revision and evidence.

### 9.4 Acceptance criteria for this architecture document

| ID | Criterion | Evidence |
| --- | --- | --- |
| D-01 | File exists at `docs/operations/QORTIUM-DEV-MONITOR-ARCHITECTURE.md` | `ls` / Git |
| D-02 | English and contains audit, design, phases, dependencies, API boundaries, security, tests and setup | Content review |
| D-03 | No bot code and no Workflow v3 functionality changed | `git status`, exact diff |
| D-04 | Unrelated uncommitted changes preserved | Baseline and final `git status` |
| D-05 | Control-plane validator passes | Command output |
| D-06 | Skills validator passes | Command output |
| D-07 | Security validator passes | Command output |
| D-08 | Commit contains only the architecture document | `git show --stat` |

## 10. Operational setup

### 10.1 Prerequisites

- Python 3.11+ on the VPS; the verified environment uses Python 3.13.
- Existing Workflow v3 checkout at `/home/iffi/dev-workspace/control-plane`.
- An owner-created Telegram bot and its token, stored outside Git.
- The owner's numeric Telegram user ID and private chat ID.
- Existing job state under the default or configured Workflow v3 state root.
- Read access to the central docs tree.
- No `sudo`, system service, public port, firewall change, package install or
  Qortium change is required.

### 10.2 Create the bot (owner action)

1. Create a bot with Telegram BotFather and record the token only in the owner's
   local configuration.
2. Keep the bot in private chat use. Do not add it to groups for control.
3. Send the bot a first message from the owner account. Use a local setup/check
   mode to read the numeric user and chat IDs; do not trust the username.
4. Confirm no webhook is configured before polling. If one exists, clear it with
   an explicit owner-run helper and verify again.

### 10.3 Configuration

Reuse the existing `~/.config/dev-control-plane/telegram.json` so the token and
chat are not duplicated. The existing notification loader ignores the nested
`monitor` object. The monitor reads and validates it; it never rewrites it.

Example shape (all values are placeholders; never commit real credentials):

```json
{
  "enabled": true,
  "bot_token": "<configured outside Git>",
  "chat_id": "<configured outside Git>",
  "events": ["SUCCESS", "FAILED", "BLOCKED", "TIMEOUT"],
  "timeout_seconds": 10,
  "monitor": {
    "mode": "read_only",
    "authorized_user_ids": [123456789],
    "allowed_chat_ids": [123456789],
    "require_private_chat": true,
    "control_passphrase_hash": "<configured outside Git>",
    "poll_timeout_seconds": 25,
    "status_refresh_seconds": 30,
    "max_inline_chars": 16000,
    "max_actions_per_minute": 30,
    "max_actions_per_chat_per_minute": 60,
    "max_starts_per_hour": 6,
    "max_text_download_bytes": 2097152,
    "max_binary_download_bytes": 10485760,
    "allow_binary_downloads": false,
    "relay_external_final": true,
    "queue_owner_messages": true,
    "auto_start_queued": false,
    "unlock_ttl_seconds": 900,
    "admission_lock_timeout_seconds": 5,
    "lifecycle_poll_seconds": 30,
    "terminal_grace_seconds": 20,
    "allowed_repo_roots": [
      "/home/iffi/dev-workspace/projects",
      "/home/iffi/dev-workspace/control-plane"
    ],
    "docs_roots": [
      "/home/iffi/dev-workspace/docs/workspace",
      "/home/iffi/dev-workspace/docs/references",
      "/home/iffi/dev-workspace/control-plane/docs"
    ],
    "agent_allowlist": ["opencode-development"],
    "model_allowlist": ["deepseek/deepseek-flash"]
  }
}
```

Permissions:

```bash
install -d -m 0700 ~/.config/dev-control-plane
install -d -m 0700 ~/.local/state/dev-control-plane/monitor
chmod 600 ~/.config/dev-control-plane/telegram.json
```

The monitor must refuse to start if the config is group/world readable. The
existing notification module only warns; the monitor is stricter because it
handles inbound interactive control.

`read_only` is the safe default. To enable P2 control, the owner must explicitly
set `mode: "control"`, keep the numeric private-chat allowlist, configure at
least one agent and model in the allowlists, and preferably add a passphrase
hash. Generate the hash locally without echo and place only the printed hash in
the `0600` config:

```bash
python3 /home/iffi/dev-workspace/control-plane/tools/dev_monitor.py hash-passphrase
```

The passphrase itself never belongs in Git, monitor state, audit rows or chat.
Restarting the monitor clears any unlocked control session.

Registry-derived project roots are added automatically at runtime. The explicit
`docs_roots` list above covers cross-project material and runbooks; it does not
grant access to unregistered top-level directories.

### 10.4 First run and verification

```bash
python3 /home/iffi/dev-workspace/control-plane/tools/dev_monitor.py check
```

`check` should validate, without starting the poll loop:

- config presence and mode `0600`;
- numeric allowlists and private-chat requirement;
- `getMe` success (token sanitized);
- no active webhook;
- registry parse and repository/doc root existence;
- docs resolver self-test on the configured roots;
- monitor state directory permissions;
- no existing single-instance lock.

Then start the monitor:

```bash
python3 /home/iffi/dev-workspace/control-plane/tools/dev_monitor.py run
```

For an owner-managed terminal session:

```bash
tmux new-session -s dev-monitor \
  "python3 /home/iffi/dev-workspace/control-plane/tools/dev_monitor.py run"
tmux attach-session -t dev-monitor
```

The monitor is not a repository-installed service. Do not create a system service
or a public listener as part of this phase. If the owner later chooses user-level
supervision, that is an explicit owner decision outside this document.

### 10.5 Running, stopping and upgrading

- The monitor writes a PID/lock record in its private state directory and refuses
  a second instance.
- Preferred stop: `dev-monitor stop`, which writes a stop flag that the loop
  checks; no signal by name is used. Jobs are detached and continue.
- In an interactive terminal, `Ctrl-C` is a normal graceful interrupt.
- If the process is wedged, the owner may terminate that exact monitor process
  from the terminal. Never use `pkill`, `killall` or a name-based kill.
- Upgrade: stop the monitor, update the repository, run `check`, then start again.
  Jobs are unaffected. Monitor state is backward-compatible within a release; if
  not, delete the monitor database (it contains UI state, not job state).
- Never stop or restart Qortium as part of a monitor upgrade.

### 10.6 Logs and monitoring

- Monitor log: private state directory, mode `0600`.
- Audit log: JSONL with timestamp, user ID, chat ID, update ID, action, job ID,
  result and a short redacted detail.
- Do not log message bodies, prompts, tokens, environment variables or full
  filesystem paths from user input.
- A health view should show: last successful poll, last Telegram error, current
  mode, authorized user count, active job count, pending wizard count and
  database status.
- Optional heartbeat: send a low-frequency owner message only if the owner opts
  in. The heartbeat is not a scheduler and must not start jobs.
- Rotate logs with an owner-managed mechanism outside the docs tree.

### 10.7 Revocation and incident response

Token or account compromise:

1. Remove the affected numeric user ID or chat ID from config.
2. Rotate the bot token with BotFather and update the config mode `0600`.
3. Restart the monitor and run `check` to confirm the new identity.
4. Review the sanitized audit log for actions and job IDs.
5. Inspect affected jobs with `dev status`; cancel only through the approved
   Phase 3 cancel flow.
6. Do not modify Qortium or VPS settings during incident response.

Suspected secret exposure:

1. Rotate the exposed credential at its source.
2. Search job logs, reports and monitor audit for the redacted marker and the
   original value; do not paste the value into a report.
3. Fix the source, add a redaction fixture, and re-run the security tests.
4. Notify the owner; store only a sanitized incident report.

Lost or stolen device:

1. Revoke the Telegram session externally.
2. Remove the user/chat IDs from config.
3. Rotate the bot token.
4. Review jobs and monitor state; preserve evidence before deleting anything.

### 10.8 Troubleshooting

| Symptom | Likely cause | Action |
| --- | --- | --- |
| `409 Conflict` | Another poller or a webhook | Stop the other poller; clear the webhook explicitly; restart |
| `401 Unauthorized` | Invalid token | Fix owner-local config; never print the token |
| No updates | Wrong offset, blocked bot or network | Check `getMe`, clear the offset only with owner approval, verify egress |
| `429` repeatedly | Rate limit or duplicate pollers | Honor `retry_after`; ensure one instance |
| Status stale | Worker exited and reconciliation has not run | Run `dev status`; the monitor will refresh |
| Cancel refused | Job not RUNNING or guard identity mismatch | Inspect status; do not signal by name |
| Docs path refused | Traversal, symlink, hidden or sensitive name | Use the listed path inside an allowed root |
| Config refused | Group/world permissions or missing allowlist | `chmod 600`; add numeric IDs |
| Duplicate STARTED | State was reset or cursor corrupted | Inspect `event_cursors`; delete only the monitor state, not job state |
| Monitor state corrupt | Crash or disk issue | Back up, delete monitor DB, restart; jobs are unaffected |

## 11. Risks, limitations and open owner decisions

### 11.1 Known limitations

- The monitor is a privileged owner client, not a sandbox.
- It cannot inject live messages into a running OpenCode turn.
- The global guard allows only one heavyweight execution across all projects.
- Per-project admission is a monitor rule, not yet a hard v3 cross-client lock.
- Telegram messages and callbacks are external; the chat is a sensitive surface.
- Redaction is pattern-based and not a proof of secret removal.
- Document hardlink escapes are residual; the docs root must remain
  owner-controlled.
- Long polling adds latency and depends on Telegram availability.
- `dev status` reconciliation writes job state by design; the monitor does not
  perform arbitrary writes.
- Existing v3 stores prompts and guard commands unredacted; the monitor hides
  them but does not fix the underlying storage. A separate v3 hardening task is
  recommended.

### 11.2 Open owner decisions

1. Default mode: keep `read_only` until the owner is satisfied with the UI, or
   enable `control` immediately for a single chat?
2. Require the local unlock passphrase for start/resume/cancel/accept, or rely on
   the Telegram user allowlist alone?
3. Allow binary document downloads, or keep text-only redacted downloads?
4. When a project is busy, reject immediately or save one manually confirmed
   queued request?
5. Approve Phase 3 additive v3 changes (`CANCELLED`, `dev cancel`, optional
   `dev resume --prompt-file -`)?
6. Which chats receive CLI-started final notifications versus monitor-only
   messages?
7. What retention period applies to queued owner instructions and audit records?
8. Should the monitor ever auto-start a queued request? Recommendation: no; keep
   owner confirmation and avoid scheduler semantics.

## 12. Validation of this document

This task is documentation-only. The following commands were run after writing
the document and before committing it:

```bash
cd /home/iffi/dev-workspace/control-plane
python3 tools/validate_control_plane.py
python3 tools/validate_skills.py
python3 tools/validate_security.py .
git diff --check -- docs/operations/QORTIUM-DEV-MONITOR-ARCHITECTURE.md
```

Results at authoring time:

```text
Control-plane validation passed: 53 active Markdown files, 203 relative links,
37 required files.
Skills validation passed: 17 active skills indexed exactly once.
Security validation passed: 123 file(s) scanned.
Document diff check: clean (exit 0).
```

A repository-wide `git diff --check` also reports a pre-existing trailing
whitespace line in `skills/qortium/qdn-resource-discovery/SKILL.md`. That change
was present before this task and was intentionally left untouched. The only
staged file for this task is this architecture document. The final handoff/report
records the exact output and the commit SHA.

The document must not contain:

- real tokens, passwords, private keys or owner-local identifiers;
- public or private infrastructure IP addresses;
- absolute Markdown links that escape the control-plane root;
- any instruction to modify the Qortium node or VPS system configuration.

## 13. References

- [Control-plane contract](../../AGENTS.md)
- [Shared workflow](../../WORKFLOW.md)
- [Git and durable handoff](../../GIT-AND-HANDOFF.md)
- [Project registry](../../PROJECT-REGISTRY.md)
- [Environment registry](../../ENVIRONMENT.md)
- [Report storage policy](../REPORT-STORAGE-POLICY.md)
- [Workflow v3 development jobs](DEV-WORKFLOW-V3.md)
- [Unattended OpenCode execution](UNATTENDED-OPENCODE.md)
- [OpenCode permission semantics](OPENCODE-PERMISSIONS.md)
- [OpenCode tmux sessions](OPENCODE-TMUX-SESSIONS.md)
- [OpenCode adapter](../../adapters/opencode/README.md)
- [Dev CLI](../../tools/dev.py)
- [Job store](../../tools/devjob/store.py)
- [Job runner](../../tools/devjob/runner.py)
- [Detection](../../tools/devjob/detect.py)
- [Notification module](../../tools/devjob/notify.py)
- [Session state](../../tools/session_state.py)
- [Execution guard](../../tools/opencode_guard.py)
- [Report template](../../templates/REPORT.md)
- [Task template](../../templates/TASK.md)
- [Control-plane validator](../../tools/validate_control_plane.py)
- [Skills validator](../../tools/validate_skills.py)
- [Security validator](../../tools/validate_security.py)


