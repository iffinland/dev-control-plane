"""Plain-text rendering for Telegram messages.

All output is plain text (no parse mode), bounded and redacted. Absolute job
state paths are not shown; the owner sees relative artifact names and can use
the read-only buttons instead.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Sequence

from .redact import redact_text

TELEGRAM_SAFE_CHARS = 3800
ACTIVE_STATES = {"RUNNING"}


def format_seconds(value: object) -> str:
    try:
        total = max(0, int(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "-"
    hours, remainder = divmod(total, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}h{minutes:02d}m{seconds:02d}s"
    if minutes:
        return f"{minutes}m{seconds:02d}s"
    return f"{seconds}s"


def truncate(text: str, limit: int = TELEGRAM_SAFE_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 20)].rstrip() + "\n... [truncated]"


def chunk_text(text: str, limit: int = TELEGRAM_SAFE_CHARS) -> list[str]:
    """Split text into Telegram-safe chunks without dropping content."""

    limit = max(200, min(int(limit), TELEGRAM_SAFE_CHARS))
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break
        cut = remaining.rfind("\n", 0, limit)
        if cut < limit // 2:
            cut = limit
        chunks.append(remaining[:cut])
        remaining = remaining[cut:].lstrip("\n")
    return chunks


def main_menu_text(config) -> str:
    if config.control_enabled:
        mode = "control"
        action_text = (
            "Start and resume are available with an explicit confirmation. "
            "Only one heavyweight execution and one active job per project are allowed."
        )
    else:
        mode = "read-only"
        action_text = (
            "Jobs, projects and the central documents tree are read-only. "
            "Start and resume require an explicit owner-configured control mode."
        )
    return (
        "Qortium Dev Monitor\n"
        f"mode: {mode}\n\n"
        f"{action_text}\n"
        "Use the buttons below or /help."
    )


def help_text(config) -> str:
    mode = "read-only" if config.read_only else "control"
    lines = [
        "Commands",
        "/start or /menu - main menu",
        "/jobs - recent and active jobs",
        "/status [job] - compact job status",
        "/projects - registered projects",
        "/docs - allowlisted documents",
        "/help - this help",
    ]
    if config.control_enabled:
        lines.extend(
            [
                "/start_job - start a registered-project job wizard",
                "/resume [job] - open the resume wizard",
                "/cancel - cancel the active wizard (not a running job)",
            ]
        )
        if config.control_passphrase_hash:
            lines.extend(
                [
                    "/unlock <passphrase> - unlock control actions for this process",
                    "/lock - re-lock control actions",
                ]
            )
    lines.extend(
        [
            "",
            f"mode: {mode}",
            (
                "Control actions require explicit confirmation and are restricted to "
                "the configured private owner chat."
                if config.control_enabled
                else "Read-only mode: start and resume are disabled."
            ),
            "Credentials are redacted. Only the configured private owner chat is allowed.",
        ]
    )
    return "\n".join(lines)


def _short_id(value: object, limit: int = 8) -> str:
    text = str(value or "-")
    return text if len(text) <= limit else text[:limit] + "..."


def _attempt_count(job: dict) -> int:
    attempts = job.get("attempts")
    if isinstance(attempts, list):
        return len(attempts)
    try:
        return int(attempts or 0)
    except (TypeError, ValueError):
        return 0


def jobs_list_text(jobs: Sequence[dict], *, page: int, total_pages: int) -> str:
    if not jobs:
        return "No development jobs found."
    lines = [f"Jobs (page {page + 1}/{total_pages})", ""]
    for job in jobs:
        state = str(job.get("state") or "UNKNOWN")
        title = str(job.get("title") or "(untitled)")[:64]
        attempt = job.get("attempt_number") or "-"
        elapsed = format_seconds(job.get("elapsed_seconds"))
        lines.append(f"{state:8} {_short_id(job.get('id')):12} attempt {attempt} {elapsed}")
        lines.append(f"  {title}")
    lines.append("")
    lines.append("Select a job for status, logs and report.")
    return "\n".join(lines)


def job_status_text(payload: dict) -> str:
    state = str(payload.get("state") or "UNKNOWN")
    lines = [
        f"Job {_short_id(payload.get('id'), 20)}",
        f"Title: {payload.get('title') or '(untitled)'}",
        f"State: {state}",
        f"Repo: {payload.get('repo') or '-'} ({payload.get('branch') or 'detached'})",
        f"Elapsed: total {format_seconds(payload.get('elapsed_seconds'))} / "
        f"attempt {format_seconds(payload.get('attempt_elapsed_seconds'))} / "
        f"timeout {format_seconds(payload.get('timeout_seconds'))}",
        f"Attempt: #{payload.get('attempt_number') or 0} "
        f"({payload.get('attempt_started_at') or '-'} -> "
        f"{payload.get('attempt_ended_at') or '-'})",
        f"PIDs: worker={payload.get('worker_pid') or '-'} "
        f"guard={payload.get('guard_pid') or '-'} "
        f"child={payload.get('child_pid') or '-'} alive={payload.get('worker_alive')}",
        "PIDs are evidence only; the monitor never signals processes.",
        f"Session: {_short_id(payload.get('session_id'), 16)}",
        f"Resumes: {payload.get('resume_count') or 0}",
    ]
    pending = payload.get("pending_criteria") or []
    if pending:
        lines.append("Pending criteria: " + ", ".join(str(item) for item in pending[:20]))
    issues = payload.get("issues") or []
    if issues:
        lines.append(f"Detected issues: {len(issues)}")
        for issue in issues[:5]:
            if isinstance(issue, dict):
                message = {
                    "severity": issue.get("severity"),
                    "kind": issue.get("kind"),
                    "message": issue.get("message"),
                }
                lines.append(
                    f"  [{message['severity'] or '-'}] {message['kind'] or '-'}: "
                    f"{str(message['message'] or '')[:200]}"
                )
            else:
                lines.append(f"  - {str(issue)[:200]}")
    if payload.get("blocker"):
        lines.append(f"Blocker: {payload['blocker']}")
    notifications = payload.get("notifications") or []
    if notifications and isinstance(notifications[-1], dict):
        last = notifications[-1]
        lines.append(
            f"Last notification: {last.get('state') or '-'} "
            f"sent={last.get('sent')} ({last.get('reason') or '-'})"
        )
    lines.append("Artifacts: run.log / worker.log / report.md")
    return "\n".join(lines)


def logs_text(job: dict, log) -> str:
    truncated = " (truncated window)" if getattr(log, "truncated", False) else ""
    header = (
        f"Job {_short_id(job.get('id'), 20)} - {log.kind} log{truncated}\n"
        f"Lines: newest {len(log.text.splitlines())}; bytes: {log.bytes_read}\n"
    )
    return truncate(header + "\n" + log.text, 3400)


def report_text(job: dict, report) -> str:
    truncated = " (truncated)" if getattr(report, "truncated", False) else ""
    header = f"Report for {_short_id(job.get('id'), 20)}{truncated}\n\n"
    return truncate(header + report.text, 3500)


def projects_text(
    projects: Sequence[object], error: str | None = None, *, control: bool = False
) -> str:
    if error:
        return f"Project registry unavailable: {error}\nDocument browsing remains limited to configured roots."
    if not projects:
        return "No registered projects."
    lines = ["Registered projects", ""]
    for item in projects:
        repo_state = "repo ok" if item.repo_available else f"repo unavailable: {item.reason}"
        docs_state = "docs ok" if item.docs_available else "docs unavailable"
        eligible = "job eligible" if getattr(item, "job_eligible", False) else "not job eligible"
        lines.append(f"{item.project_id} [{item.project.platform}]")
        lines.append(f"  {repo_state}; {docs_state}; {eligible}")
    lines.append("")
    if control:
        lines.append("Use Start job to select a registered project and open the start wizard.")
    else:
        lines.append("Read-only mode: start and resume are disabled.")
    return "\n".join(lines)


def documents_roots_text(roots: Sequence[object]) -> str:
    if not roots:
        return "No document roots are configured."
    lines = ["Document roots", ""]
    for root in roots:
        lines.append(f"- {root.label}")
    lines.append("")
    lines.append("Hidden files, symlinks and sensitive names are excluded.")
    return "\n".join(lines)


def listing_text(listing) -> str:
    if not listing.entries:
        body = "(empty directory)"
    else:
        body = "\n".join(
            f"{'[dir] ' if entry.is_dir else ''}{entry.name}"
            for entry in listing.entries
        )
    return (
        f"Documents: {listing.rel_dir or '/'} "
        f"(page {listing.page + 1}/{listing.total_pages}, {listing.total_entries} entries)\n\n"
        f"{body}"
    )


def preview_text(preview) -> str:
    return (
        f"{preview.rel_path} ({preview.size} bytes)\n"
        f"Redacted text preview:\n\n{preview.text}"
    )


def confirmation_text(name: str, size: int) -> str:
    return (
        f"Binary download: {name} ({size} bytes)\n"
        "This file type is not text. Confirm only if you trust this document."
    )


# ---- P2 control rendering ------------------------------------------------------


def _project_line(project) -> str:
    return (
        f"{project.project_id} [{project.project.platform}]\n"
        f"  repo: {project.repo_real or project.project.repo_path}"
    )


def start_project_text() -> str:
    return (
        "Start a development job\n\n"
        "Select a registered project. Only projects with an available repository "
        "and inside an allowed repository root are shown."
    )


def start_title_text(project) -> str:
    return (
        "Start wizard: title\n\n"
        f"Project: {project.project_id}\n"
        "Send a short job title (maximum 120 characters).\n\n"
        "Send /cancel or press Cancel to stop without starting a job."
    )


def start_prompt_text() -> str:
    return (
        "Start wizard: prompt\n\n"
        "Send the complete authorized task prompt (maximum 20000 characters). "
        "It is passed to Workflow v3 over standard input, never through a shell."
    )


def start_criteria_text() -> str:
    return (
        "Start wizard: acceptance criteria\n\n"
        "At least one criterion is mandatory. Send one per line:\n"
        "  Label::command\n"
        "  manual: text verified by the owner\n\n"
        "Commands run with bash in the selected repository. The monitor never "
        "treats OpenCode exit code 0 as acceptance."
    )


def start_timeout_text() -> str:
    return (
        "Start wizard: timeout\n\n"
        "Send a wall-clock timeout such as 8h, 2h, 90m or 3600s. "
        "The maximum is 8h."
    )


def start_branch_text() -> str:
    return (
        "Start wizard: branch label\n\n"
        "Send an optional branch label, or /skip to record the detected branch."
    )


def _criteria_lines(request) -> list[str]:
    lines: list[str] = []
    for label, command in request.command_criteria:
        lines.append(f"  - command [{label}]: {command}")
    for manual in request.manual_criteria:
        lines.append(f"  - manual: {manual}")
    return lines


def start_preview_text(request) -> str:
    prompt_preview = request.prompt
    if len(prompt_preview) > 1200:
        prompt_preview = prompt_preview[:1200].rstrip() + "\n... [preview truncated]"
    lines = [
        "Confirm job start",
        "",
        f"Project: {request.project_id}",
        f"Repository: {request.repo}",
        f"Title: {request.title}",
        f"Branch label: {request.branch or '(detected)'}",
        f"Timeout: {format_seconds(request.timeout_seconds)}",
        f"Agent: {request.agent}",
        f"Model: {request.model}",
        "",
        "Acceptance criteria (authoritative):",
        *_criteria_lines(request),
        "",
        "Prompt preview (redacted at the send boundary):",
        prompt_preview,
        "",
        "Press Confirm to invoke the existing `dev start` CLI. Acceptance commands "
        "run with bash in the repository. Nothing is started until Confirm.",
    ]
    return "\n".join(lines)


def resume_prompt_text() -> str:
    return (
        "Resume wizard: instruction\n\n"
        "Send an optional resume instruction, or /skip to use the Workflow v3 "
        "default. The instruction is passed as one argv element, not a shell command."
    )


def resume_preview_text(job: dict, data: dict) -> str:
    flags = []
    if data.get("new_session"):
        flags.append("new session (session continuity abandoned)")
    if data.get("force"):
        flags.append("force rerun (a SUCCESS job may run again)")
    prompt = data.get("prompt")
    lines = [
        "Resume job",
        "",
        f"Job: {job.get('id')}",
        f"Title: {job.get('title') or '(untitled)'}",
        f"State: {job.get('state') or 'UNKNOWN'}",
        f"Attempt: #{job.get('attempt_number') or 0}",
        f"Session: {_short_id(job.get('session_id'), 16)}",
        f"Resumes so far: {job.get('resume_count') or 0}",
        f"Blocker: {job.get('blocker') or '-'}",
        f"Options: {', '.join(flags) if flags else 'normal resume'}",
        "",
        "Resume instruction:",
        prompt or "(Workflow v3 default)",
        "",
        "Confirm opens a final one-time confirmation. No attempt starts before that.",
    ]
    return "\n".join(lines)


def resume_confirmation_text(job: dict, request) -> str:
    lines = [
        "Confirm resume",
        "",
        f"Job: {request.job_id}",
        f"Title: {job.get('title') or '(untitled)'}",
        f"Current state: {job.get('state') or 'UNKNOWN'}",
        f"New session: {'yes' if request.new_session else 'no'}",
        f"Force rerun: {'yes' if request.force else 'no'}",
        f"Timeout: {format_seconds(request.timeout_seconds) if request.timeout_seconds else '(existing)'}",
        f"Instruction: {request.prompt or '(Workflow v3 default)'}",
        "",
        "Press Confirm to invoke `dev resume` for this exact job.",
    ]
    return "\n".join(lines)


def job_started_text(job: dict, project_id: str | None = None) -> str:
    return (
        "Job started\n\n"
        f"Project: {project_id or '-'}\n"
        f"Job: {job.get('id')}\n"
        f"Title: {job.get('title') or '(untitled)'}\n"
        f"State: {job.get('state') or 'UNKNOWN'}\n"
        f"Timeout: {format_seconds(job.get('timeout_seconds'))}\n\n"
        "STARTED was sent. Use the job view for live status, logs and the report."
    )


def job_resumed_text(job: dict) -> str:
    return (
        "Job resumed\n\n"
        f"Job: {job.get('id')}\n"
        f"Title: {job.get('title') or '(untitled)'}\n"
        f"State: {job.get('state') or 'UNKNOWN'}\n"
        f"Resume count: {job.get('resume_count') or 0}\n\n"
        "RESUMED was sent. The same job and session continue."
    )


def job_refused_text(job: dict, project_id: str | None = None, *, resumed: bool = False) -> str:
    action = "resume" if resumed else "start"
    return (
        f"Job {action} was refused or did not enter RUNNING.\n\n"
        f"Project: {project_id or job.get('repo') or '-'}\n"
        f"Job: {job.get('id') or '-'}\n"
        f"State: {job.get('state') or 'UNKNOWN'}\n"
        f"Blocker: {job.get('blocker') or 'none recorded'}\n\n"
        "No STARTED/RESUMED notification is sent for a non-RUNNING job."
    )


def lifecycle_started_text(job: dict, project_id: str | None = None) -> str:
    return (
        "STARTED\n"
        f"Project: {project_id or '-'}\n"
        f"Job: {_short_id(job.get('id'), 20)}\n"
        f"Title: {job.get('title') or '(untitled)'}\n"
        f"Attempt: #{job.get('attempt_number') or _attempt_count(job) or 1}\n"
        f"Timeout: {format_seconds(job.get('timeout_seconds'))}"
    )


def lifecycle_resumed_text(job: dict) -> str:
    return (
        "RESUMED\n"
        f"Job: {_short_id(job.get('id'), 20)}\n"
        f"Title: {job.get('title') or '(untitled)'}\n"
        f"Attempt: #{job.get('attempt_number') or _attempt_count(job) or 1}\n"
        f"Resume count: {job.get('resume_count') or 0}\n"
        f"State: {job.get('state') or 'RUNNING'}"
    )


def lifecycle_terminal_text(job: dict, state: str) -> str:
    return (
        f"Job {state}\n"
        f"Job: {_short_id(job.get('id'), 20)}\n"
        f"Title: {job.get('title') or '(untitled)'}\n"
        f"Blocker: {job.get('blocker') or '-'}\n"
        f"Elapsed: {format_seconds(job.get('elapsed_seconds') or job.get('duration_seconds'))}"
    )


def lifecycle_alert_text(job: dict, kind: str, detail: str = "") -> str:
    label = {
        "reconciled_stale": "WORKER LOST",
        "worker_lock_conflict": "WORKER LOCK CONFLICT",
        "worker_error": "WORKER ERROR",
    }.get(kind, kind.upper())
    lines = [
        label,
        f"Job: {_short_id(job.get('id'), 20)}",
        f"Title: {job.get('title') or '(untitled)'}",
    ]
    if detail:
        lines.append(f"Detail: {detail[:400]}")
    return "\n".join(lines)


def service_status_text(snapshot: dict, *, running: bool) -> str:
    lines = [
        f"Qortium Dev Monitor: {'running' if running else 'stopped'}",
        f"state: {snapshot.get('path')}",
        f"update offset: {snapshot.get('update_offset')}",
        f"last poll: {snapshot.get('last_poll_at')}",
    ]
    counts = snapshot.get("counts") or {}
    if counts:
        lines.append(
            "state rows: " + ", ".join(f"{key}={value}" for key, value in sorted(counts.items()))
        )
    return "\n".join(lines)


def safe_outbound(text: str, config, limit: int | None = None) -> str:
    return redact_text(text, config.secrets, limit or config.max_inline_chars)


def relative_artifact(path: str | Path) -> str:
    return Path(path).name
