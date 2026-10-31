# Unattended OpenCode execution

Status: active operating procedure, implemented 2026-10-31.
Scope: owner-authorized, bounded unattended OpenCode work on the Debian VPS.
Related: [control-plane contract](../../AGENTS.md),
[workflow](../../WORKFLOW.md), [tmux session runbook](OPENCODE-TMUX-SESSIONS.md),
[OpenCode adapter](../../adapters/opencode/README.md).

## Purpose and boundary

This runbook defines the minimal way to run one authorized OpenCode task without
an attached terminal and without a scheduler, daemon, timer, service or network
listener. The owner still authorizes the repository, outcome, allowed external
actions, forbidden actions and stop condition before the run starts.

The implementation consists of:

| Component | Canonical path | Purpose |
| --- | --- | --- |
| Unattended agent profile | `adapters/opencode/agents/opencode-unattended.md` | Restricted permissions and an 80-step limit |
| Installed agent copy | `~/.config/opencode/agents/opencode-unattended.md` | What the local OpenCode client loads |
| Execution guard | `tools/opencode_guard.py` | Preflight, one-session lock, resource checks, four-hour timeout, safe cancellation |
| Guard tests | `tools/test_opencode_guard.py` | Threshold, timeout, cancellation, lock, permission and Qortium-safety tests |
| tmux runbook | `docs/operations/OPENCODE-TMUX-SESSIONS.md` | Terminal persistence and reattachment |
| Task state | `templates/TASK.md`, `templates/STATUS.json` | Optional unattended fields, backward compatible with schema version 2 |

The existing interactive OpenCode configuration is not changed. The new agent is
an additional profile; the global `opencode.jsonc` and the interactive `build`
agent remain as they were.

## Owner decisions recorded

- autonomous work starts immediately when the owner submits an authorized task;
- maximum wall-clock time is four hours per task;
- no monetary or credit limit and no pricing-window logic;
- no automatic delayed scheduling;
- no scheduler, daemon or orchestration service;
- maximum one heavyweight OpenCode execution at a time;
- the interactive OpenCode configuration is preserved;
- the unattended profile is separate and restricted;
- Qortium is never modified or restarted.

## Preflight and phase boundaries

Run the guard before starting and at every phase boundary:

```bash
python3 /home/iffi/dev-workspace/control-plane/tools/opencode_guard.py check
```

Exit codes:

| Code | Meaning | Action |
| --- | --- | --- |
| `0` | PASS | Continue |
| `10` | WARN | Continue with caution and record the warning |
| `20` | REFUSE | Do not start new work; write a recoverable handoff |

Candidate resource thresholds:

| Check | Warning | Refusal |
| --- | --- | --- |
| Available RAM | below 3 GiB | below 1.5 GiB |
| Five-minute load average | above 5 | none; warning only |
| Available disk | below 20 GiB | none; warning only |
| Heavyweight OpenCode executions | more than one | a second execution when the maximum is one |

The guard reads Qortium only to report its PID and RSS. It never uses a
process-name kill, never signals Qortium, and only terminates the process group
it created for the unattended command.

## Start an authorized four-hour task

Use a named tmux session, one repository/worktree per session, and start in the
task working directory:

```bash
SESSION=oc-<project>-<task>-<YYYYMMDD>
WORKDIR=/home/iffi/dev-workspace/projects/<repository>
tmux new-session -s "$SESSION" -c "$WORKDIR"
```

Inside the tmux session:

```bash
python3 /home/iffi/dev-workspace/control-plane/tools/opencode_guard.py run \
  --timeout 4h \
  --log "/home/iffi/dev-workspace/logs/opencode-<task>-$(date -u +%Y%m%dT%H%M%SZ).log" \
  -- opencode run \
    --agent opencode-unattended \
    --model deepseek/deepseek-flash \
    --title "<task title>" \
    "<authorized task prompt>"
```

Do not add `--auto`. The restricted profile declares explicit permissions. The
guard refuses to start a new OpenCode execution if another heavyweight OpenCode
execution is already running, so exit the interactive TUI normally or wait for
it to finish; do not kill it.

The command is intentionally a direct `opencode run` invocation. The guard's
one-session check inspects direct OpenCode processes; wrapping the command in an
unrelated shell hides it from that check.

## Reconnect and inspect progress

Reattach to the same terminal:

```bash
tmux attach-session -t "$SESSION"
```

Read-only or non-attached inspection:

```bash
tmux list-clients -t "$SESSION"
tmux capture-pane -p -t "$SESSION" -S -100
tail -n 100 /home/iffi/dev-workspace/logs/opencode-<task>-<timestamp>.log
```

Inspect OpenCode history and resume manually:

```bash
opencode session list --format json --max-count 10
opencode export <session-id> --sanitize
opencode --session <session-id>
# or, for another non-interactive turn:
opencode run --session <session-id> --agent opencode-unattended "<next instruction>"
```

## Timeout, cancellation and recovery

- The guard enforces the four-hour maximum and records exit code `124` on
  timeout.
- `SIGINT` to the guard records exit code `130`; `SIGTERM` records `143`.
- On timeout or signal the guard sends `SIGTERM` to the child process group,
  waits for the grace period, then sends `SIGKILL` to that same group. It does
  not use a global process-name kill.
- Development children normally share the process group and are terminated. A
  child that deliberately creates a new session can escape the group; this is a
  known limitation, not a guarantee.
- A timed-out OpenCode run is **not** a graceful checkpoint. The guard logs the
  timeout and the recent session list, but the agent may not have written its
  final checkpoint. OpenCode session history is preserved in the SQLite store
  and can be resumed with `--session <id>`.
- Exit code `0` is not acceptance. Accept work only with the task report, exact
  diff/commit, required checks, runtime evidence and the STATUS evidence.

## Acceptance evidence

The task controller and STATUS record at least:

- the exact command, agent profile, timeout and log path;
- the OpenCode session ID and the final exit code or timeout/signal;
- the resource snapshot before and after;
- the repository, branch, base SHA and final SHA or dirty state;
- the checks actually executed and their results;
- the claim-by-claim evidence and any missing evidence;
- the owner-only steps and the merge/publish state.

The `unattended` object in `STATUS.json` is optional and additive; existing
schema version 2 readers can ignore it.

## Permissions and security limits

The unattended profile denies `question`, `task` subagents, `plan_enter`,
`plan_exit`, `sudo`, `systemctl`, `service`, `systemd-run`, reboot/shutdown,
`kill`/`pkill`/`killall`, `tmux kill-server`, `opencode serve`/`web`/`acp`,
`git push`, `git merge`, `gh`, `ssh`, `scp`, `rsync`, container/orchestration
commands, package publication, `qortium*` and `qortal*`. It also denies `.env`,
key and certificate edits and permits workspace paths only under
`/home/iffi/dev-workspace/**`.

These are permission patterns, not a security sandbox. A shell command can run a
script that does more than its pattern suggests. The control-plane contract,
task authorization, Git hooks, branch protection and owner review remain the
authoritative controls. The restricted profile also denies feature-branch
pushes and PR creation; the owner integrates local work unless a separately
approved profile is used for external writes.

## Stop and cleanup

1. Reach a phase boundary, write the checkpoint/report and stop starting new
   work.
2. Exit OpenCode normally. If cleanup is required, kill only the named tmux
   session with `tmux kill-session -t "$SESSION"`.
3. Never run `tmux kill-server`, `pkill -f opencode` or any signal to Qortium.
4. Verify Qortium's PID and RSS are unchanged and no new listener, service or
   timer exists.

## Known limitations

- no hard monetary cap; the four-hour bound and 80-step limit are the only
  native proxies;
- no graceful checkpoint guarantee at timeout;
- tmux sessions do not survive a reboot;
- the one-session check recognises direct OpenCode invocations, not an
  OpenCode process hidden inside an arbitrary wrapper;
- permission patterns are not a sandbox;
- OpenCode upgrades can change flags, permission semantics or output events;
- the owner must confirm the real SSH/Termius reconnect after the first
  authorized use.

## Agent step limit

The unattended OpenCode agent uses `steps: 500` (previously 80).
This is a per-run agent step limit, independent of the execution guard's
maximum four-hour wall-clock timeout.

When the step limit is reached, preserve the existing working tree and
session history. Resume the same task in a new guarded execution rather
than starting implementation from scratch.
