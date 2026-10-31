# Persistent OpenCode sessions with tmux

Status: active operating procedure, verified 2026-10-31.
Scope: Debian VPS workspace `/home/iffi/dev-workspace`.
Related: [workflow](../../WORKFLOW.md), [OpenCode adapter](../../adapters/opencode/README.md),
[unattended execution runbook](UNATTENDED-OPENCODE.md).

## Purpose and boundary

`tmux` keeps an OpenCode process and its terminal state alive when the
Termius/SSH connection closes, so the owner can reconnect to the same terminal
and continue the same OpenCode session.

This is terminal-session persistence only. It is **not** autonomous task
execution:

- tmux does not schedule work, poll, auto-restart, or make decisions;
- it does not grant commit, push, merge, publish, deploy, signing, transaction
  or server-change authority;
- unattended/overnight work still requires explicit owner authorization under
  [WORKFLOW.md](../../WORKFLOW.md), including repository, outcome, allowed and
  forbidden actions, and a stop condition;
- no systemd linger, service, timer, scheduler or background polling loop is
  configured or authorized by this procedure.

## Verified environment

Observed on the VPS on 2026-10-31:

| Item | Verified state |
| --- | --- |
| OS | Debian GNU/Linux 13 (trixie), kernel 6.12 |
| CPU / memory | 6 vCPU, 11 GiB RAM, no swap |
| Disk | 197 GB root filesystem, about 142 GB free |
| OpenCode | `1.19.5` at `/home/iffi/.opencode/bin/opencode` |
| OpenCode sessions | SQLite `~/.local/share/opencode/opencode.db`; `opencode session list` shows persistent history |
| tmux | `3.5a` installed at `/usr/bin/tmux`; no user `.tmux.conf` |
| systemd | version 257 user manager; `Linger=no`; no user unit directory |
| SSH | `ClientAliveInterval 120`; Termius is only the SSH client |

The current OpenCode process is not itself inside tmux. A direct SSH TUI can
lose its terminal on disconnect even though its session history remains in the
OpenCode database. Start new sessions in tmux when disconnect survival matters.

## Session naming convention

Use:

```text
oc-<project>-<task>-<YYYYMMDD>
```

- Lowercase ASCII letters, digits and hyphens only; no `.` or `:`.
- `<project>` is the short project name (`control-plane`, `docs`, `blogs`,
  `nodefm-station`, etc.).
- `<task>` is a short slug, for example `audit`, `review` or `nightly`.
- Keep the name under 40 characters where practical.
- One session per repository/worktree and task. Do not reuse a name for a
  different task.
- If the name already exists, list sessions and choose a unique name. Do not
  attach to or kill someone else's session without owner approval.

Examples:

```text
oc-control-plane-review-20261031
oc-docs-report-20261031
oc-nodefm-station-audit-20261031
```

## Working-directory policy

Always start tmux with an absolute `-c` working directory. One session serves
one repository or worktree; do not mix unrelated repositories in one session.

| Work target | Working directory |
| --- | --- |
| Control plane | `/home/iffi/dev-workspace/control-plane` |
| Central docs | `/home/iffi/dev-workspace/docs` |
| Application project | `/home/iffi/dev-workspace/projects/<repository>` |
| Isolated worktree | the explicit worktree path |

For parallel work, use separate Git worktrees rather than two agents writing the
same checkout. Run only one heavy OpenCode session at a time on this VPS. The
Qortium Java process already uses roughly 2.5 GiB and the host has no swap.

## Start, detach, list and reattach

Set the names once in the shell:

```bash
SESSION=oc-control-plane-review-20261031
WORKDIR=/home/iffi/dev-workspace/control-plane
```

Preflight:

```bash
tmux -V
tmux ls 2>/dev/null || true
opencode session list
pgrep -af 'opencode|qortium.jar'
free -h
```

Start an interactive session:

```bash
tmux new-session -s "$SESSION" -c "$WORKDIR"
```

Inside the tmux session:

```bash
opencode                 # new session
opencode -c              # continue the most recent OpenCode session
opencode --session <id>  # continue a specific OpenCode session
```

Detach without stopping the process:

```text
Ctrl-b d
```

or from another shell:

```bash
tmux detach-client -s "$SESSION"
```

List sessions and panes:

```bash
tmux ls
tmux list-panes -a -F '#{session_name} pid=#{pane_pid} cmd=#{pane_current_command} cwd=#{pane_current_path}'
```

Reattach to the same terminal:

```bash
tmux attach-session -t "$SESSION"
```

Read-only attach (useful for inspection without typing into the session):

```bash
tmux attach-session -r -t "$SESSION"
```

Check liveness and recent output without attaching:

```bash
tmux has-session -t "$SESSION"
tmux list-clients -t "$SESSION"
tmux capture-pane -p -t "$SESSION" -S -50
```

Optional explicitly authorized detached run (non-interactive):

```bash
tmux new-session -d -s "$SESSION" -c "$WORKDIR" \
  'opencode run "task message" >> /tmp/opencode/'"$SESSION"'.log 2>&1'
```

This starts the command detached; it is not a supervisor and does not restart
the command. Use it only after the owner authorizes the bounded task and stop
condition.

## Safe termination

Inspect the target first:

```bash
tmux list-panes -t "$SESSION" -F '#{pane_pid} #{pane_current_command} #{pane_current_path}'
```

Exit OpenCode normally inside the session, then remove only that session:

```bash
tmux kill-session -t "$SESSION"
```

Verify cleanup:

```bash
tmux ls 2>/dev/null || true
```

Never run `tmux kill-server`: it terminates every tmux session owned by the
user. Do not terminate a session you did not create without explicit owner
approval.

## Persistence and resume limits

- tmux keeps the server and its processes alive after the SSH/Termius client
  disconnects.
- OpenCode session history persists independently in its SQLite database. After
  an OpenCode process exits or restarts, list sessions with
  `opencode session list` and resume with `-c` or `--session <id>`.
- tmux sessions do **not** survive a VPS reboot. No reboot persistence is
  configured. Do not enable systemd linger or create a service without separate
  owner approval.
- A disconnected tmux session can still consume memory and may hold repository
  locks. Inspect and clean up finished sessions.
- tmux pane buffers and OpenCode logs may contain sensitive task output. The
  tmux socket is per-user; lock the terminal and do not expose the session to
  other users.

## Resource and safety limits

Run one heavy OpenCode session at a time. Monitor before and during the session:

```bash
free -h
ps -o pid,etime,rss,pcpu,cmd -C opencode
ps -o pid,etime,rss,pcpu,cmd -p "$(pgrep -f qortium.jar | head -1)"
```

- There is no swap. Memory pressure can trigger the OOM killer.
- Do not use `opencode serve`, `--mdns`, `--hostname 0.0.0.0` or any network
  listener. This procedure uses terminal tmux only.
- Do not use `--auto` unless the owner explicitly authorizes it for the bounded
  task.
- Do not run concurrent agents against the same worktree, node, host or shared
  runtime.
- Unattended/overnight work remains governed by the authorization, validation
  and handoff rules in `WORKFLOW.md`.

## Verification record

On 2026-10-31 a test session named
`oc-selftest-20261031T073750Z-278528` ran a harmless heartbeat loop in
`/tmp/opencode`:

1. The session started detached and the heartbeat advanced.
2. A terminal client attached; `tmux list-clients` reported one client.
3. The client exited; the session remained alive and the heartbeat continued
   from 3 to 7 lines.
4. A second client reattached successfully; after it exited, the session
   remained alive and the heartbeat continued from 8 to 11 lines.
5. Only the test session was killed; no tmux server or test session remained.

The owner's OpenCode process (PID 270751) and Qortium Java process (PID 13615)
kept the same PIDs and continued running. Memory remained stable at roughly
3.6 GiB used and 8.1 GiB available. No OpenCode listener, systemd unit, linger
setting or network port was created.

Actual TCP/SSH teardown was not simulated during the 2026-10-31 verification
because it would risk the owner's live connection. The client-exit test
exercises the server-side persistence mechanism that protects against
SSH/Termius disconnects. On 2026-10-31 the owner subsequently reported a
successful real Termius/SSH disconnect and reconnect against a tmux session.
That is owner-provided evidence, not an independently re-simulated network drop;
it closes the previously documented remaining real-network step for this
workflow.
