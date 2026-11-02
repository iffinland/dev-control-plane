"""Plain-text rendering for Telegram messages.

All output is plain text (no parse mode), bounded and redacted. Absolute job
state paths are not shown; the owner sees relative artifact names and can use
the read-only buttons instead.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping, Sequence

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
                "/newproject [GitHub URL] - clone, inspect and register a new GitHub project",
                "/resume [job] - open the resume wizard",
                "/cancel [job] - cancel the active wizard, or cancel a RUNNING job",
                "/queue [job] - queue an instruction for the next resume",
                "/messages [job] - show queued and delivered instructions",
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


def short_title(value: object, limit: int = 42) -> str:
    text = " ".join(str(value or "").split())
    if not text:
        return "(untitled)"
    if len(text) <= limit:
        return text
    cut = text.rfind(" ", 0, limit + 1)
    if cut < max(12, limit // 2):
        cut = limit
    return text[:cut].rstrip(" ,.;:-") + "..."


def _format_date(value: object) -> str:
    text = str(value or "")
    if not text:
        return "-"
    try:
        parsed = datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        return text[:16] + ("Z" if len(text) >= 16 else "")
    return parsed.strftime("%Y-%m-%d %H:%MZ")


def _attempt_count(job: dict) -> int:
    attempts = job.get("attempts")
    if isinstance(attempts, list):
        return len(attempts)
    try:
        return int(attempts or 0)
    except (TypeError, ValueError):
        return 0


def job_button_label(job: dict, project: str | None = None) -> str:
    """Return a readable inline-button label for a job.

    The title identifies the actual task; the state remains visible but never
    replaces the title. Job IDs stay in the detailed job view.
    """

    state = str(job.get("state") or "UNKNOWN")
    title = short_title(job.get("title"), 38)
    label = f"{state} · {title}"
    if len(label) > 59:
        label = label[:58] + "…"
    return label


def jobs_list_text(
    jobs: Sequence[dict],
    *,
    page: int,
    total_pages: int,
    projects: Mapping[str, str] | None = None,
) -> str:
    if not jobs:
        return "No development jobs found."
    projects = projects or {}
    lines = [f"Jobs (page {page + 1}/{total_pages})", ""]
    for job in jobs:
        state = str(job.get("state") or "UNKNOWN")
        title = short_title(job.get("title"), 64)
        project = projects.get(str(job.get("id") or ""), "(unregistered)")
        attempt = job.get("attempt_number") or "-"
        active = format_seconds(job.get("attempt_elapsed_seconds"))
        total = format_seconds(job.get("elapsed_seconds"))
        date = _format_date(
            job.get("attempt_started_at") or job.get("started_at")
        )
        runtime = (
            f"attempt {attempt} · active {active} · total {total}"
            if state == "RUNNING"
            else f"attempt {attempt} · ran {active} · total {total}"
        )
        lines.append(f"{state} · {project}")
        lines.append(f"  {title}")
        lines.append(f"  {runtime} · {date}")
    lines.append("")
    lines.append("Select a job for status, logs and report.")
    return "\n".join(lines)


def job_status_text(
    payload: dict,
    *,
    queued_instructions: int = 0,
    project: str | None = None,
    summary: str | None = None,
) -> str:
    state = str(payload.get("state") or "UNKNOWN")
    lines = [
        f"Job {_short_id(payload.get('id'), 20)}",
        f"Title: {payload.get('title') or '(untitled)'}",
        f"State: {state}",
        f"Project: {project or '(unregistered)'}",
        f"Repo: {payload.get('repo') or '-'} ({payload.get('branch') or 'detached'})",
        f"Runtime: active attempt {format_seconds(payload.get('attempt_elapsed_seconds'))}; "
        f"total wall-clock {format_seconds(payload.get('elapsed_seconds'))}; "
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
        f"Queued owner instructions: {int(queued_instructions)}",
    ]
    pending = payload.get("pending_criteria") or []
    if pending:
        lines.append("Pending criteria: " + ", ".join(str(item) for item in pending[:20]))
    contract = payload.get("completion_contract") or {}
    if isinstance(contract, dict) and contract.get("configured"):
        source = payload.get("completion_contract_source")
        suffix = f" ({source})" if source else ""
        lines.append(f"Contract: {contract.get('state') or 'UNKNOWN'}{suffix}")
        for check in contract.get("checks") or []:
            if isinstance(check, dict) and check.get("status") in {"failed", "pending"}:
                lines.append(
                    f"  [{check.get('status')}] {check.get('id')}: {check.get('detail')}"
                )
    elif payload.get("completion_contract_required"):
        lines.append("Contract: required - not evaluated yet")
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
    if summary:
        lines.extend(["", summary.strip()])
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
        "Select a registered project. Only projects with an available repository, "
        "an allowed repository root and a valid Git delivery policy are shown."
    )


def start_description_text(project) -> str:
    return (
        "Start a development job\n\n"
        f"Project: {project.project_id} [{project.project.platform}]\n\n"
        "What should be changed or fixed? Describe the task in plain language. "
        "A readable job title is derived automatically.\n\n"
        "Acceptance commands and project instructions are loaded from the project's "
        "verified acceptance profile. You do not need to type them.\n\n"
        "Send /cancel or press Cancel to stop without starting a job."
    )


def start_runtime_text(title: str, *, read_only: bool = False) -> str:
    return (
        "Choose maximum runtime\n\n"
        f"Task: {title}\n\n"
        "This is the wall-clock limit for each attempt, not a target. "
        "Choose 1h, 2h, 4h or 8h.\n\n"
        f"Read-only audit: {'on' if read_only else 'off'}\n"
        "A read-only audit may inspect the repository but must not commit or "
        "push; the completion contract verifies that nothing changed.\n\n"
        "Advanced options are optional: custom acceptance commands, a custom "
        "timeout or a branch label."
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


def onboard_url_text() -> str:
    return (
        "New project from GitHub\n\n"
        "Send the GitHub repository URL, for example:\n"
        "  https://github.com/owner/repo\n"
        "  git@github.com:owner/repo.git\n\n"
        "Only github.com is accepted. The URL must not contain credentials. "
        "An existing checkout is never overwritten and no repository script is "
        "executed during onboarding.\n\n"
        "Send /cancel to stop without cloning or registering anything."
    )


def onboard_description_text(identity) -> str:
    return (
        "New project from GitHub\n\n"
        f"Repository: {identity.repository}\n\n"
        "Describe the first task. A readable job title is derived automatically. "
        "The project is cloned and registered first, then this task starts "
        "immediately in the prepared development branch.\n\n"
        "Send /cancel to stop; nothing has been cloned or registered yet."
    )


def onboard_runtime_text(title: str, *, read_only: bool = False) -> str:
    return (
        "Choose maximum runtime\n\n"
        f"Task: {title}\n\n"
        "This is the wall-clock limit for the first attempt. "
        "Choose 1h, 2h, 4h or 8h.\n\n"
        f"Read-only audit: {'on' if read_only else 'off'}\n"
        "A read-only audit may inspect the repository but must not commit or "
        "push; the completion contract verifies that nothing changed.\n\n"
        "Acceptance commands are discovered conservatively from known manifests "
        "and are not executed during onboarding."
    )


def onboard_preview_text(
    identity, target, title: str, timeout_seconds: int, *, read_only: bool = False
) -> str:
    return "\n".join(
        [
            "Confirm new project",
            "",
            f"GitHub repository: {identity.repository}",
            f"Target checkout: {target}",
            f"Title: {title}",
            f"Maximum runtime: {format_seconds(timeout_seconds)}",
            f"Mode: {'read-only audit (no commit or push)' if read_only else 'development delivery'}",
            "",
            "On Confirm the repository is cloned (if needed), inspected without "
            "running its scripts, registered in the project registry with an "
            "agent/* delivery policy, given a verified acceptance profile, and the "
            "first job starts immediately. No repository script is executed before "
            "the normal acceptance commands.",
        ]
    )


def onboard_result_text(project, job: dict | None, error: str | None = None) -> str:
    lines = [
        "Project onboarding",
        "",
        f"Project: {project.project_id} [{project.platform}]",
        f"GitHub: {project.github_repository}",
        f"Checkout: {project.repo_path}",
        f"Branch: {project.branch or '-'}",
        f"Cloned: {'yes' if project.cloned else 'no'}",
        f"Acceptance: {len(project.commands)} command(s), {len(project.manual)} manual",
        f"Made available to Telegram: yes",
    ]
    if error:
        lines.extend(["", f"First job not started: {error}"])
    elif job is not None:
        lines.extend(
            [
                "",
                f"First job: {job.get('id')} ({job.get('state')})",
                f"Branch: {job.get('branch') or '-'}",
            ]
        )
    return "\n".join(lines)


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
        f"Branch: {request.branch or '(current detected branch; push only if policy allows)'}",
        f"Maximum runtime: {format_seconds(request.timeout_seconds)}",
        f"Acceptance profile: {request.profile_source or 'explicit advanced criteria'}",
        f"Mode: {'read-only audit (no commit or push)' if getattr(request, 'read_only', False) else 'development delivery'}",
        f"Auto-loaded context files: {len(request.context_paths)}",
        "",
        "Acceptance criteria (authoritative):",
        *_criteria_lines(request),
        "",
        "Prompt preview (redacted at the send boundary):",
        prompt_preview,
        "",
        "Press Confirm to invoke the existing `dev start` CLI. Acceptance commands "
        "run with bash in the repository. Nothing is started until Confirm. A "
        "passing build or test is technical evidence, not proof that the owner's "
        "underlying bug is fixed.",
    ]
    return "\n".join(lines)


def resume_prompt_text() -> str:
    return (
        "Resume wizard: instruction\n\n"
        "Send an optional resume instruction, or /skip to use the Workflow v3 "
        "default. The instruction is passed as one argv element, not a shell command."
    )


def _queued_lines(messages) -> list[str]:
    messages = list(messages or [])
    if not messages:
        return ["Queued instructions: none"]
    lines = [f"Queued instructions for the next resume: {len(messages)}"]
    for item in messages[:5]:
        body = " ".join(str(item.get("body") or "").split())
        lines.append(f"  - {body[:180]}")
    if len(messages) > 5:
        lines.append(f"  ... and {len(messages) - 5} more")
    return lines


def resume_preview_text(job: dict, data: dict, pending: object = ()) -> str:
    flags = []
    if data.get("new_session"):
        flags.append("new session (session continuity abandoned)")
    if data.get("force"):
        flags.append("allow another attempt after success")
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
        f"Options: {', '.join(flags) if flags else 'normal continuation'}",
        "",
        "Continue this job with an optional instruction:",
        prompt or "(Workflow v3 default)",
        "",
        *_queued_lines(pending),
        "",
        "Queued instructions are delivered on this continuation, not injected live.",
        "A completed (SUCCESS) job needs 'Allow another attempt' before it can continue;",
        "this prevents accidental repetition. A job without a known OpenCode session",
        "requires the explicit New session option.",
        "Confirm opens a final one-time confirmation. No attempt starts before that.",
    ]
    return "\n".join(lines)


def resume_confirmation_text(job: dict, request, pending_count: int = 0) -> str:
    lines = [
        "Confirm resume",
        "",
        f"Job: {request.job_id}",
        f"Title: {job.get('title') or '(untitled)'}",
        f"Current state: {job.get('state') or 'UNKNOWN'}",
        f"New session: {'yes' if request.new_session else 'no'}",
        (
            "Allow another attempt after success: "
            f"{'yes - a new attempt will run' if request.force else 'no'}"
        ),
        f"Timeout: {format_seconds(request.timeout_seconds) if request.timeout_seconds else '(existing)'}",
        f"Queued instructions included: {int(pending_count)}",
        f"Instruction: {request.prompt or '(Workflow v3 default)'}",
        "",
        "Press Confirm to invoke `dev resume` for this exact job. Queued instructions "
        "are marked delivered only after Workflow v3 accepts the resume.",
    ]
    return "\n".join(lines)


def queue_prompt_text(job: dict) -> str:
    return (
        "Queue an owner instruction\n\n"
        f"Job: {_short_id(job.get('id'), 20)}\n"
        f"State: {job.get('state') or 'UNKNOWN'}\n\n"
        "Send the instruction (text only, maximum configured length). It is stored "
        "durably and delivered in the resume prompt at the next resume. It is never "
        "injected into a running OpenCode turn and never executed as a shell command."
    )


def queue_confirmation_text(job: dict, pending_count: int) -> str:
    return (
        "Instruction queued\n\n"
        f"Job: {_short_id(job.get('id'), 20)}\n"
        f"Queued for the next resume: {pending_count}\n\n"
        "While the job is RUNNING this is not delivered live. Open Resume after the "
        "current attempt ends to deliver queued instructions exactly once."
    )


def owner_messages_text(job_id: str, messages) -> str:
    messages = list(messages or [])
    lines = [f"Owner instructions for {_short_id(job_id, 20)}", ""]
    if not messages:
        lines.append("None queued or delivered.")
        return "\n".join(lines)
    for item in messages[:20]:
        state = str(item.get("delivery_state") or "queued")
        if state == "delivered":
            suffix = f"delivered at attempt #{item.get('delivered_attempt') or '-'}"
        else:
            suffix = "queued for the next resume"
        body = " ".join(str(item.get("body") or "").split())
        lines.append(f"- [{state}] {body[:300]}")
        lines.append(f"  {suffix}")
    if len(messages) > 20:
        lines.append(f"... and {len(messages) - 20} older entries")
    return "\n".join(lines)


def cancel_preview_text(job: dict) -> str:
    return (
        "Cancel this running job?\n\n"
        f"Job: {job.get('id')}\n"
        f"Title: {job.get('title') or '(untitled)'}\n"
        f"State: {job.get('state') or 'UNKNOWN'}\n"
        f"Attempt: #{job.get('attempt_number') or 0}\n"
        f"Worker PID: {job.get('worker_pid') or '-'}\n"
        f"Guard PID: {job.get('guard_pid') or '-'}\n\n"
        "Workflow v3 re-verifies the guard process identity and sends SIGTERM to "
        "that exact guard only. The guard stops only the child process group it "
        "created. The working tree and OpenCode session are preserved, and the job "
        "remains resumable. No name-based kill is used."
    )


def cancel_result_text(payload: dict) -> str:
    job = payload.get("job") or {}
    status = str(payload.get("cancel_status") or "unknown")
    return (
        f"Cancel result: {status}\n"
        f"Job: {job.get('id') or '-'}\n"
        f"State: {job.get('state') or 'UNKNOWN'}\n"
        f"Detail: {payload.get('detail') or '-'}\n\n"
        + (
            "The working tree and session history are preserved. Resume when ready."
            if status in {"cancelled", "pending"}
            else "No cancellation signal was escalated."
        )
    )


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


def lifecycle_terminal_text(job: dict, state: str, summary: str | None = None) -> str:
    lines = [
        f"Job {state}",
        f"Job: {_short_id(job.get('id'), 20)}",
        f"Title: {job.get('title') or '(untitled)'}",
        f"Blocker: {job.get('blocker') or '-'}",
        f"Runtime: active attempt {format_seconds(job.get('attempt_elapsed_seconds'))}; "
        f"total {format_seconds(job.get('elapsed_seconds') or job.get('duration_seconds'))}",
    ]
    if summary:
        lines.extend(["", summary.strip()])
    return "\n".join(lines)


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
