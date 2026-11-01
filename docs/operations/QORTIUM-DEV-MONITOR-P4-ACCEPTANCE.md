# Qortium Dev Monitor P4 — real-runtime owner acceptance checklist

Status: **P4 automated hardening is implemented and tested. Real-runtime owner
acceptance remains pending until the owner executes this checklist with the real
bot.** This document does not authorize Telegram actions, a service restart or a
live-job cancellation by an agent.

| Field | Value |
| --- | --- |
| Executing agent | `DeepSeek` |
| Report/handoff writer | `DeepSeek` (same agent) |
| Executing-agent evidence | Work performed in this session by the `deepseek/deepseek-flash` model through the owner-authorized Workflow v3 job. No second agent produced the work. |
| Artifact type | Operations / owner acceptance checklist |
| Project scope | Cross-project Workflow v3 control plane (`workspace` material) |
| Canonical path | `docs/operations/QORTIUM-DEV-MONITOR-P4-ACCEPTANCE.md` |
| Control-plane contract | [AGENTS.md](../../AGENTS.md), [WORKFLOW.md](../../WORKFLOW.md), [GIT-AND-HANDOFF.md](../../GIT-AND-HANDOFF.md) |
| Runbook | [QORTIUM-DEV-MONITOR.md](QORTIUM-DEV-MONITOR.md) |
| Architecture | [QORTIUM-DEV-MONITOR-ARCHITECTURE.md](QORTIUM-DEV-MONITOR-ARCHITECTURE.md) |

## 1. What the owner is accepting

The checklist proves the real deployed monitor still satisfies the P1-P4 safety
contract:

- only numeric allowlisted users in the configured private chat can act;
- every mutating action needs an explicit one-time confirmation;
- callback replays and duplicate updates do not repeat actions;
- credentials never appear in chat, logs, audit rows, reports or attachments;
- document browsing refuses traversal, symlinks, hidden/sensitive names, special
  files and oversize files;
- start, resume and cancel go only through the existing Workflow v3 CLI;
- queued owner instructions are delivered exactly once at the next resume;
- STARTED, RESUMED and terminal notifications are not duplicated after restart;
- polling recovers from transient Telegram failures without losing updates;
- the monitor opens no listener and never touches Qortium or VPS configuration.

## 2. Preconditions and safety rules

1. Read [QORTIUM-DEV-MONITOR.md](QORTIUM-DEV-MONITOR.md) first.
2. Confirm `monitor.mode` is the intended mode. Start with `read_only`; enable
   `control` only for a deliberate acceptance window.
3. Keep the owner-local `telegram.json` at mode `0600`. Never paste its token,
   chat ID or passphrase hash into a report, commit, chat message or terminal
   transcript.
4. Run `dev_monitor.py check` and record the sanitized output before testing.
5. Use a disposable acceptance job and an isolated repository/worktree. Do not
   cancel or resume a real production job as part of acceptance.
6. Do not install, restart, stop, reconfigure or signal the Qortium node. Do not
   change VPS networking, mounts, packages, services or firewall rules.
7. Do not run `sudo`, a service manager with mutating verbs, `crontab`, `at`, or
   a name-based process kill.
8. Before and after the matrix, record the Qortium PID/RSS and listening
   sockets. They must be unchanged except for normal process activity.

Useful read-only preflight:

```bash
cd /home/iffi/dev-workspace/control-plane
python3 tools/dev_monitor.py check
python3 tools/dev_monitor.py status --json
systemctl --user status qortium-dev-monitor.service --no-pager || true
journalctl --user -u qortium-dev-monitor.service -n 50 --no-pager || true
ps -o pid,rss,args -p "$(pgrep -f 'Qortium.jar' | head -n1)" || true
ss -ltnp | grep -E 'qortium|dev-monitor|python' || true
```

`pgrep` above is read-only PID discovery for `ps`; never use a name-based kill.
If the service is not installed, the foreground runbook path applies.

## 3. Acceptance matrix

Record the exact timestamp, Telegram message IDs and sanitized evidence for each
row. A row passes only when the expected observable result is reproduced.

| ID | Scenario | Steps | Expected evidence |
| --- | --- | --- | --- |
| R-01 | Authorized owner menu | From the owner private chat send `/start` and `/help`. | Menu and help open; active mode is visible; no token, path or allowlist value is shown. |
| R-02 | Unauthorized account | From a second account (not in `authorized_user_ids`) send `/start`, `/jobs` and press a stale menu button from another chat. | Generic `Access denied.` only; no job names, project IDs, paths or configuration. |
| R-03 | Read-only browsing | Send `/jobs`, open a job, open Run log and Report, and browse `/docs`. | Bounded, redacted previews; traversal and hidden names are refused; source files are unchanged. |
| R-04 | Document traversal and symlink | Ask the bot for a path containing `..`, an absolute path, a backslash or a percent-encoded traversal; try a symlink inside a docs root. | All are refused; audit records a refusal with no document content. |
| R-05 | Redacted download | Download a report and a text document that contain a test marker such as `password=...` in an isolated fixture. | Download filename contains `.redacted`; the marker value is replaced by `<redacted>`; the source file hash is unchanged. |
| R-06 | Start a disposable job | In control mode send `/start_job`, select a registered project, enter a small prompt and one command criterion, inspect the exact preview and Confirm once. | Exactly one `dev start` invocation; STARTED appears once; job view shows attempt #1, PIDs and criteria. |
| R-07 | Duplicate confirmation | Press the same confirmation button twice, or replay the same update through a test transport. | Exactly one job exists; the second click reports expired/already used; no duplicate STARTED. |
| R-08 | Queue an instruction | While the disposable job is RUNNING open it, choose Queue instruction and send a short instruction. | Reply says delivery happens on the next resume, not live; `/messages` shows it queued. |
| R-09 | Cancel only the disposable job | Open the disposable RUNNING job, choose Cancel job, read the preview and Confirm once. | `dev cancel` revalidates the guard; only that job becomes CANCELLED; worktree and session are preserved; no name-based kill. |
| R-10 | Resume and deliver once | Resume the cancelled disposable job. The preview must list the queued instruction and the confirmation must count it. | RESUMED once; same job/session; queued instruction appears in the resume prompt; `/messages` marks it delivered at the new attempt; a second resume does not include it again. |
| R-11 | Failed resume keeps the queue | Cause a deliberate refused resume (for example an unknown session without New session, or a busy project) after queueing a new instruction. | The instruction remains `queued`; a short redacted error is shown; a later successful resume delivers it once. |
| R-12 | Restart persistence | While a disposable job is RUNNING, restart only the monitor process/service. Do not touch Qortium. | The job continues; existing STARTED/RESUMED/terminal messages are not duplicated; offset, queue and confirmation state survive. |
| R-13 | Polling fault recovery | With a test transport or an owner-approved network fault, inject a timeout, `5xx` and `429` response. | The monitor backs off, honors `retry_after`, stays alive and does not lose the pending update. |
| R-14 | Token rotation | Rotate the bot token with BotFather, update the owner-local config at `0600`, restart the monitor and run `check`. | Old token fails cleanly; new token works; no token appears in journal, audit rows, reports or chat. |
| R-15 | No listener and no Qortium/VPS change | Before and after the matrix compare `ss -ltnp`, Qortium PID/RSS and service/config mtimes. | No new LISTEN socket owned by the monitor; no Qortium or VPS configuration change. |
| R-16 | Graceful shutdown | Stop the monitor by the documented flag/service path, not by a name-based kill. | Exit is graceful; the disposable job is unaffected; the single-instance lock is released. |

## 4. Evidence capture

Store a short sanitized record under the central workspace validation tree:

```text
/home/iffi/dev-workspace/docs/workspace/validation/
```

Include:

- exact application commit SHA and monitor version;
- `dev_monitor.py check` output (sanitized);
- each R-row result, timestamp and short observation;
- before/after Qortium PID/RSS and listener comparison;
- any owner-only step that could not be executed and why;
- no tokens, chat IDs, passphrases, prompts, private paths or raw logs.

Do not copy the owner-local `telegram.json` or monitor SQLite database into Git or
a report.

## 5. Sign-off

| Field | Value |
| --- | --- |
| Owner | |
| Date / time (UTC) | |
| Application SHA | |
| Monitor version | |
| Mode (`read_only` / `control`) | |
| Rows passed | |
| Rows failed or not executed | |
| Reason for any exception | |
| Rollback performed? | |
| Remaining risk accepted? | |

A failed security row (authorization, redaction, traversal/symlink, cancel
identity, duplicate side effect) blocks acceptance. Revert `monitor.mode` to
`read_only`, stop the monitor through its documented path, and record the failure
without modifying Qortium or VPS configuration.
