# Implementation — control-plane/workflow-v3-20261031

Executing agent (actual executor of the work): DeepSeek
Report/handoff writer (if different from the executing agent): DeepSeek
Exact application repository / branch / SHA:
`/home/iffi/dev-workspace/control-plane`,
`agent/control-plane/workflow-v3-20261031`,
implementation commit recorded in `STATUS.json` after the first commit.
Verdict and measurable acceptance achieved: implementation complete and locally
validated; owner review/merge and real-environment acceptance remain pending.

## Changes

- Raised the execution guard's hard maximum and default from 4h to 8h
  (`tools/opencode_guard.py`). Added optional `--pid-file` child PID/PGID
  evidence. Updated guard tests for 8h and the PID file.
- Added the Workflow v3 CLI at `tools/dev.py` and engine under
  `tools/devjob/`:
  - `start`: explicit acceptance criteria, guard preflight, detached worker.
  - `status`, `report`, `logs`, `resume`, plus manual `accept`.
  - durable `job.json`, `events.jsonl`, logs, child PID, `report.md` under
    `~/.local/state/dev-control-plane` by default.
  - states RUNNING/SUCCESS/FAILED/BLOCKED/TIMEOUT with evidence-based success.
  - detectors for permission rejection, failed commands, missing dependencies,
    step exhaustion and incomplete implementation.
  - safe resume of the same OpenCode session/worktree; no reset/clean/stash.
  - Telegram final-state notifications loaded from a file outside Git.
- Added the unattended development OpenCode profile
  (`adapters/opencode/agents/opencode-development.md`) and installer
  (`tools/install_opencode_profiles.sh`). The existing restricted profile is
  unchanged.
- Added CLI tests (`tools/test_dev_cli.py`), docs
  (`docs/operations/DEV-WORKFLOW-V3.md`), examples (`examples/workflow-v3/`) and
  migration instructions (`docs/migration/2026-10-31-workflow-v3.md`).
- Wired the new CLI test and required files into validation/CI.
- Hardened runtime state file modes (0700 directories, 0600 files) and kept
  Telegram credentials out of jobs/logs/reports.

## Preserved security boundaries

- The guard still reads Qortium only for PID/RSS, refuses a second heavyweight
  OpenCode execution, and terminates only its own process group.
- The development profile denies Qortium commands/paths, system administration,
  global package installs, force-push, merge/release, process-name kills and
  listener creation.
- No Qortium, systemd/service, system package or blockchain transaction was
  touched. Tests use a fake `opencode` and synthetic procfs.

## Evidence by layer

- `python3 tools/test_opencode_guard.py` — 30 tests OK (8h maximum/default,
  rejection of 9h, timeout/cancellation, lock, PID file, profile boundaries).
- `python3 tools/test_dev_cli.py` — 21 tests OK (exit 0 + failing acceptance
  becomes FAILED; permission/missing dependency BLOCKED; step exhaustion and
  incomplete FAILED; TIMEOUT; resume; manual accept; logs/report; Telegram
  redaction; default 8h).
- `python3 tools/validate_control_plane.py` — PASS.
- `python3 tools/validate_skills.py` — PASS.
- `python3 tools/validate_security.py .` — PASS.
- `python3 tools/test_git_hooks.py` — PASS.
- `python3 -m compileall -q tools` — OK.
- `python3 tools/opencode_guard.py check` — PASS at baseline/phase boundaries.

## Checks not executed and why

Real OpenCode model execution, Telegram network delivery, QDN publish/update,
development-wallet transactions and live application tests were not executed in
this implementation task. They require an owner-authorized real job and explicit
scope. No real blockchain transaction was performed.

## Adversarial self-audit

- Verified success cannot come from exit code alone: a test runs OpenCode exit 0
  with a failing acceptance command and asserts FAILED.
- Verified timeouts map to TIMEOUT (guard exit 124), permission/missing
  dependency map to BLOCKED, and step exhaustion/incomplete implementation map
  to FAILED.
- Verified resume keeps the same job ID, appends an attempt and passes
  `--session`; it never resets/cleans the working tree.
- Verified notification failure/reason redaction never includes the token.
- Verified tests cannot signal Qortium and do not start real OpenCode.

## External actions

Local commit only on the dedicated feature branch. No push, merge, deploy,
release, QDN write, signing or transaction.

## Remaining risks / follow-ups

1. Install the development profile and restart OpenCode before the first real
   job (`tools/install_opencode_profiles.sh`).
2. Configure Telegram outside Git (mode 0600) if notifications are wanted.
3. Owner must run one real bounded job and confirm the detached/SSH-disconnect
   behavior, Telegram delivery and real acceptance commands.
4. Detectors are conservative log heuristics; acceptance commands remain
   authoritative.
5. Each resume attempt has its own 8h bound; this is not a cumulative cap.

## Capability harvest

No platform skill was created or changed. This is control-plane operational
tooling, documented as a reusable runbook (`docs/operations/DEV-WORKFLOW-V3.md`).
The skills index was not edited because it contains unrelated owner work in
progress; promoting a new shared skill would have required staging that work.

## Report path

Canonical central report:
`/home/iffi/dev-workspace/docs/workspace/implementation/2026-10-31-workflow-v3.md`
