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
    mode = "read-only" if config.read_only else "control (P1 actions are read-only)"
    return (
        "Qortium Dev Monitor\n"
        f"mode: {mode}\n\n"
        "Jobs, projects and the central documents tree are read-only in this "
        "phase. Use the buttons below or /help."
    )


def help_text(config) -> str:
    mode = "read-only" if config.read_only else "control (P1 actions are read-only)"
    return (
        "Commands\n"
        "/start or /menu - main menu\n"
        "/jobs - recent and active jobs\n"
        "/status [job] - compact job status\n"
        "/projects - registered projects\n"
        "/docs - allowlisted documents\n"
        "/help - this help\n\n"
        f"mode: {mode}\n"
        "P1 is an observer: start, resume, cancel and accept are not available.\n"
        "Credentials are redacted. Only the configured private owner chat is allowed."
    )


def _short_id(value: object, limit: int = 8) -> str:
    text = str(value or "-")
    return text if len(text) <= limit else text[:limit] + "..."


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


def projects_text(projects: Sequence[object], error: str | None = None) -> str:
    if error:
        return f"Project registry unavailable: {error}\nDocument browsing remains limited to configured roots."
    if not projects:
        return "No registered projects."
    lines = ["Registered projects", ""]
    for item in projects:
        repo_state = "repo ok" if item.repo_available else f"repo unavailable: {item.reason}"
        docs_state = "docs ok" if item.docs_available else "docs unavailable"
        lines.append(f"{item.project_id} [{item.project.platform}]")
        lines.append(f"  {repo_state}; {docs_state}")
    lines.append("")
    lines.append("P1 does not start jobs from Telegram.")
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
