"""Authorized control flows for start, resume, cancel and owner messaging.

The manager owns wizard state transitions, input validation, confirmation
payloads and the fixed-shape ``dev start`` / ``dev resume`` / ``dev cancel``
invocations. It never uses a shell, never accepts an arbitrary repository, agent,
model or timeout, and never starts jobs in tests by itself.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from . import menus, render
from .admission import (
    AdmissionError,
    AdmissionLockTimeout,
    GlobalGuardBusy,
    ProjectBusy,
)
from .config import MonitorConfig
from .jobs import JobError, JobFacade, validate_job_id
from .projects import Registry, RegistryError, ValidatedProject, project_by_id
from .redact import sanitize_control
from .state import MonitorState

from devjob import acceptance_profiles, onboarding

MAX_TITLE = 120
MAX_PROMPT = 20000
MAX_CRITERIA = 12
MAX_COMMAND = 1000
MAX_LABEL = 80
MAX_MANUAL = 300
MAX_BRANCH = 120
MAX_QUEUED_MESSAGES = 20
MIN_TIMEOUT = 60
MAX_TIMEOUT = 8 * 3600
WIZARD_TTL = 3600
RUNTIME_CHOICES = (3600, 7200, 14400, 28800)
SKIP_VALUES = frozenset({"", "-", "skip", "/skip", "auto", "none", "default"})
GITHUB_REFERENCE_RE = re.compile(
    r"(?:https?://github\.com/|git@github\.com:)([A-Za-z0-9._-]+/[A-Za-z0-9._-]+)"
)
ABSOLUTE_PROJECT_PATH_RE = re.compile(r"(/(?:[^\s`'\"]+/)*projects/[^\s`'\"]+)")
FOLLOW_UP_HEADER = (
    "The owner queued the following follow-up instructions through the authorized "
    "Telegram control surface. Continue the existing authorized task, preserve the "
    "working tree and all completed work, do not expand scope beyond the original "
    "task and these instructions, and finish with verifiable evidence."
)


class ControlError(RuntimeError):
    """A user-correctable control-flow error."""


def derive_title(description: str, limit: int = 80) -> str:
    """Derive a readable, bounded title from the owner's task description."""

    lines = [line.strip() for line in sanitize_control(description).splitlines() if line.strip()]
    if not lines:
        raise ControlError("task description must not be empty")
    first = lines[0]
    first = re.sub(r"^#{1,6}\s*", "", first)
    first = re.sub(r"^(?:[-*+]\s+|\d+[.)]\s+)", "", first)
    first = " ".join(first.split())
    if not first:
        raise ControlError("task description must not be empty")
    if len(first) <= limit:
        return first
    cut = first.rfind(" ", 0, limit + 1)
    if cut < max(20, limit // 2):
        cut = limit
    return first[:cut].rstrip(" ,.;:-") + "..."


def _context_block(items: Sequence[acceptance_profiles.ContextItem]) -> str:
    if not items:
        return ""
    lines = [
        "",
        "## Auto-discovered project context",
        "",
        "Read these existing instructions and load only matching skills before",
        "implementing. Current source and runtime remain authoritative.",
        "",
    ]
    for item in items:
        lines.append(f"- {item.kind}: `{item.path}`")
    lines.extend(
        [
            "",
            "Use the project's existing discovery mechanisms. Do not invent test",
            "commands or claim functional proof that the evidence does not support.",
        ]
    )
    return "\n".join(lines)


def compose_task_prompt(
    description: str,
    profile: acceptance_profiles.AcceptanceProfile,
    context: Sequence[acceptance_profiles.ContextItem],
) -> str:
    """Build the normal-flow prompt from the owner description plus context."""

    body = sanitize_control(description).strip()
    if not body:
        raise ControlError("task description must not be empty")
    block = _context_block(context)
    return (body + "\n" + block).strip() if block else body


@dataclass(frozen=True)
class StartRequest:
    project_id: str
    repo: str
    title: str
    prompt: str
    command_criteria: tuple[tuple[str, str], ...]
    manual_criteria: tuple[str, ...]
    timeout_seconds: int
    branch: str | None
    agent: str
    model: str
    profile_source: str = ""
    context_paths: tuple[str, ...] = ()
    read_only: bool = False

    def payload(self, wizard_id: str) -> dict[str, Any]:
        return {
            "wizard_id": wizard_id,
            "project_id": self.project_id,
            "repo": self.repo,
            "title": self.title,
            "prompt": self.prompt,
            "command_criteria": [list(item) for item in self.command_criteria],
            "manual_criteria": list(self.manual_criteria),
            "timeout_seconds": int(self.timeout_seconds),
            "branch": self.branch,
            "agent": self.agent,
            "model": self.model,
            "profile_source": self.profile_source,
            "context_paths": list(self.context_paths),
            "read_only": bool(self.read_only),
        }


@dataclass(frozen=True)
class ResumeRequest:
    job_id: str
    prompt: str | None
    timeout_seconds: int | None
    new_session: bool
    force: bool

    def payload(self, wizard_id: str) -> dict[str, Any]:
        return {
            "wizard_id": wizard_id,
            "job_id": self.job_id,
            "prompt": self.prompt,
            "timeout_seconds": self.timeout_seconds,
            "new_session": bool(self.new_session),
            "force": bool(self.force),
        }


@dataclass
class ControlResult:
    text: str
    markup: dict | None = None
    job_id: str | None = None
    project_id: str | None = None
    notification: str | None = None


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def _attempt_number(job: Mapping[str, Any]) -> int:
    try:
        return int(job.get("attempt_number") or 0)
    except (TypeError, ValueError):
        return 0


def validate_text(value: str, *, limit: int, field: str, allow_newlines: bool = False) -> str:
    if not isinstance(value, str):
        raise ControlError(f"{field} must be text")
    if "\x00" in value:
        raise ControlError(f"{field} contains a NUL character")
    cleaned = sanitize_control(value).strip()
    if not cleaned:
        raise ControlError(f"{field} must not be empty")
    if not allow_newlines:
        cleaned = " ".join(cleaned.split())
    if len(cleaned) > limit:
        raise ControlError(f"{field} is longer than {limit} characters")
    return cleaned


def parse_timeout(value: str) -> int:
    raw = _text(value).strip().lower()
    if not raw:
        raise ControlError("timeout is required, for example 8h or 90m")
    unit = raw[-1]
    number_text = raw[:-1] if unit in "smhd" else raw
    try:
        number = int(number_text)
    except ValueError as exc:
        raise ControlError("timeout must be an integer with s, m, h or d") from exc
    multiplier = {"s": 1, "m": 60, "h": 3600, "d": 86400}.get(unit, 1)
    seconds = number * multiplier
    if seconds < MIN_TIMEOUT:
        raise ControlError(f"timeout must be at least {MIN_TIMEOUT} seconds")
    if seconds > MAX_TIMEOUT:
        raise ControlError("timeout exceeds the eight-hour maximum")
    return seconds


def parse_criteria(value: str) -> tuple[tuple[tuple[str, str], ...], tuple[str, ...]]:
    if not isinstance(value, str):
        raise ControlError("acceptance criteria must be text")
    lines = [line.strip() for line in sanitize_control(value).splitlines() if line.strip()]
    if not lines:
        raise ControlError(
            "at least one acceptance criterion is required; one criterion per line"
        )
    if len(lines) > MAX_CRITERIA:
        raise ControlError(f"at most {MAX_CRITERIA} acceptance criteria are allowed")
    commands: list[tuple[str, str]] = []
    manuals: list[str] = []
    for line in lines:
        lowered = line.lower()
        if lowered.startswith("manual:"):
            manual = validate_text(
                line.split(":", 1)[1], limit=MAX_MANUAL, field="manual criterion"
            )
            manuals.append(manual)
            continue
        if "::" in line:
            label, command = line.split("::", 1)
            label = validate_text(label, limit=MAX_LABEL, field="criterion label")
            command = line.split("::", 1)[1].strip()
        else:
            label = "Acceptance"
            command = line
        if not command:
            raise ControlError("an acceptance command must not be empty")
        command = validate_text(command, limit=MAX_COMMAND, field="acceptance command")
        commands.append((label, command))
    if not commands and not manuals:
        raise ControlError("at least one acceptance criterion is required")
    return tuple(commands), tuple(manuals)


def _skip(value: str) -> bool:
    return _text(value).strip().lower() in SKIP_VALUES


def compose_resume_prompt(
    base_prompt: str | None,
    messages: Sequence[dict],
    *,
    limit: int = MAX_PROMPT,
) -> str | None:
    """Compose a resume prompt with a clearly delimited owner follow-up block.

    The result is passed to Workflow v3 over standard input, never through a
    shell. With no queued messages the base prompt is returned unchanged so a
    normal resume keeps its existing behaviour.
    """

    messages = [item for item in messages if str(item.get("body") or "").strip()]
    if not messages:
        return base_prompt
    parts: list[str] = []
    if base_prompt and base_prompt.strip():
        parts.append(base_prompt.strip())
        parts.append("")
    parts.append(FOLLOW_UP_HEADER)
    parts.append("")
    for index, item in enumerate(messages, start=1):
        body = sanitize_control(str(item.get("body") or "")).strip()
        parts.append(f"{index}. {body}")
    composed = "\n".join(parts).strip()
    if len(composed) > limit:
        raise ControlError(
            f"the resume instruction plus queued messages exceeds {limit} characters"
        )
    return composed


class ControlManager:
    def __init__(
        self,
        config: MonitorConfig,
        state: MonitorState,
        jobs: JobFacade,
        registry: Registry,
        admission,
        notifier=None,
    ) -> None:
        self.config = config
        self.state = state
        self.jobs = jobs
        self.registry = registry
        self.admission = admission
        self.notifier = notifier

    # ---- shared helpers ----------------------------------------------------------
    def _projects(self) -> list[ValidatedProject]:
        try:
            return list(self.registry.load())
        except RegistryError as exc:
            raise ControlError(f"project registry is unavailable: {exc}") from exc

    def _eligible(self) -> list[ValidatedProject]:
        return [item for item in self._projects() if item.job_eligible]

    def _project_policy(self, project: ValidatedProject):
        from devjob import project_policy

        return project_policy.resolve(
            project.repo_real or project.project.repo_path,
            registry_path=self.registry.path,
            project_id=project.project_id,
        )

    def _default_agent(self) -> str:
        return self.config.agent_allowlist[0] if self.config.agent_allowlist else ""

    def _default_model(self) -> str:
        return self.config.model_allowlist[0] if self.config.model_allowlist else ""

    def _wizard(self, wizard_id: str, user_id: int, chat_id: int) -> dict[str, Any]:
        wizard = self.state.get_wizard(wizard_id, user_id, chat_id)
        if not wizard:
            raise ControlError("this wizard has expired or belongs to another chat")
        return wizard

    def _cancel(self, wizard: dict[str, Any], user_id: int, chat_id: int) -> ControlResult:
        self.state.delete_wizard(str(wizard["wizard_id"]), user_id, chat_id)
        return ControlResult("Wizard cancelled. No job was started or resumed.", menus.back_to_main())

    # ---- cancel flow -------------------------------------------------------------
    def begin_cancel(self, job_id: str, user_id: int, chat_id: int) -> ControlResult:
        job_id = validate_job_id(job_id)
        job = self.jobs.job_status(job_id)
        if str(job.get("state")) != "RUNNING":
            raise ControlError(f"job {job_id} is not RUNNING; nothing was signalled")
        nonce = self.state.create_confirmation(
            user_id,
            chat_id,
            "cancel_job",
            {"job_id": job_id, "attempt_number": _attempt_number(job)},
        )
        return ControlResult(
            render.cancel_preview_text(job),
            menus.control_confirmation_menu(nonce, "Cancel running job"),
            job_id=job_id,
        )

    def perform_cancel(self, payload: dict[str, Any], decision) -> ControlResult:
        job_id = validate_job_id(_text(payload.get("job_id")))
        job = self.jobs.job_status(job_id)
        expected_attempt = payload.get("attempt_number")
        if expected_attempt is None:
            raise ControlError(
                "this cancellation confirmation has no attempt identity; open the job again"
            )
        try:
            expected = int(expected_attempt)
        except (TypeError, ValueError) as exc:
            raise ControlError("the cancellation confirmation is malformed") from exc
        if _attempt_number(job) != expected:
            raise ControlError(
                "this cancellation confirmation belongs to an earlier attempt; "
                "open the job again"
            )
        key = self.admission.project_key_for_job(job)
        try:
            with self.admission.reserve(key):
                payload_result = self.jobs.cancel_job(job_id)
        except (AdmissionLockTimeout, AdmissionError) as exc:
            raise ControlError(str(exc)) from exc
        return ControlResult(
            render.cancel_result_text(payload_result),
            self._job_menu(job_id, decision),
            job_id=job_id,
            notification=None,
        )

    # ---- queued owner instructions ----------------------------------------------
    def begin_queue(self, job_id: str, user_id: int, chat_id: int) -> ControlResult:
        job_id = validate_job_id(job_id)
        job = self.jobs.job_status(job_id)
        if not self.config.queue_owner_messages:
            raise ControlError("queued owner messages are disabled by configuration")
        if self.state.count_pending_owner_messages(job_id) >= MAX_QUEUED_MESSAGES:
            raise ControlError(
                f"this job already has {MAX_QUEUED_MESSAGES} queued instructions; "
                "resume it to deliver them first"
            )
        data = {"job_id": job_id}
        wizard_id = self.state.create_wizard(
            user_id, chat_id, "queue", "text", data, ttl_seconds=WIZARD_TTL
        )
        return ControlResult(
            render.queue_prompt_text(job),
            menus.wizard_cancel_menu(wizard_id),
            job_id=job_id,
        )

    def queue_text(self, wizard: dict[str, Any], text: str, decision) -> ControlResult:
        if str(wizard["step"]) != "text":
            raise ControlError("this wizard is waiting for a button, not text")
        if not self.config.queue_owner_messages:
            raise ControlError("queued owner messages are disabled by configuration")
        wizard_id = str(wizard["wizard_id"])
        user_id = int(decision.user_id or 0)
        chat_id = int(decision.chat_id or 0)
        job_id = validate_job_id(_text(wizard["data"].get("job_id")))
        self.jobs.job_status(job_id)
        body = validate_text(
            text,
            limit=self.config.owner_message_max_chars,
            field="owner instruction",
            allow_newlines=True,
        )
        if self.state.count_pending_owner_messages(job_id) >= MAX_QUEUED_MESSAGES:
            raise ControlError(
                f"this job already has {MAX_QUEUED_MESSAGES} queued instructions; "
                "resume it to deliver them first"
            )
        self.state.add_owner_message(job_id, user_id, chat_id, body)
        self.state.delete_wizard(wizard_id, user_id, chat_id)
        job = self.jobs.job_status(job_id)
        pending = self.state.count_pending_owner_messages(job_id)
        return ControlResult(
            render.queue_confirmation_text(job, pending),
            self._job_menu(job_id, decision),
            job_id=job_id,
        )

    # ---- start wizard ------------------------------------------------------------
    def begin_start(self, user_id: int, chat_id: int) -> ControlResult:
        projects = self._eligible()
        if not projects:
            return ControlResult(
                "No registered project has an available repository and a valid delivery policy, so a job cannot be started.",
                menus.back_to_main(),
            )
        data = {
            "project_ids": [project.project_id for project in projects],
            "step_count": 0,
        }
        wizard_id = self.state.create_wizard(
            user_id, chat_id, "start", "project", data, ttl_seconds=WIZARD_TTL
        )
        wizard = {"wizard_id": wizard_id, "kind": "start", "step": "project", "data": data}
        return ControlResult(
            render.start_project_text(),
            menus.start_project_menu(wizard_id, projects),
        )

    # ---- new project onboarding --------------------------------------------------
    def _projects_root(self) -> Path:
        roots = list(self.config.allowed_repo_roots)
        for root in roots:
            if root.name == "projects":
                return root.expanduser().resolve()
        if roots:
            return roots[0].expanduser().resolve()
        return onboarding.PROJECTS_ROOT

    def begin_onboard(
        self, user_id: int, chat_id: int, url: str | None = None
    ) -> ControlResult:
        data: dict[str, Any] = {"url": None}
        step = "url"
        text = render.onboard_url_text()
        if url is not None and str(url).strip():
            identity = onboarding.parse_github_identity(str(url))
            data["url"] = str(url).strip()
            data["repository"] = identity.repository
            step = "description"
            text = render.onboard_description_text(identity)
        wizard_id = self.state.create_wizard(
            user_id, chat_id, "onboard", step, data, ttl_seconds=WIZARD_TTL
        )
        return ControlResult(text, menus.wizard_cancel_menu(wizard_id))

    def onboard_text(self, wizard: dict[str, Any], text: str, decision) -> ControlResult:
        wizard_id = str(wizard["wizard_id"])
        user_id = int(decision.user_id or 0)
        chat_id = int(decision.chat_id or 0)
        data = dict(wizard["data"])
        step = str(wizard["step"])
        if step == "url":
            identity = onboarding.parse_github_identity(
                validate_text(text, limit=500, field="GitHub repository URL")
            )
            data["url"] = text.strip()
            data["repository"] = identity.repository
            self.state.update_wizard(
                wizard_id, user_id, chat_id, step="description", data=data, ttl_seconds=WIZARD_TTL
            )
            return ControlResult(
                render.onboard_description_text(identity),
                menus.wizard_cancel_menu(wizard_id),
            )
        if step == "description":
            description = validate_text(
                text,
                limit=MAX_PROMPT,
                field="task description",
                allow_newlines=True,
            )
            data["description"] = description
            data["title"] = derive_title(description)
            self.state.update_wizard(
                wizard_id, user_id, chat_id, step="runtime", data=data, ttl_seconds=WIZARD_TTL
            )
            return ControlResult(
                render.onboard_runtime_text(data["title"]),
                menus.onboard_runtime_menu(wizard_id),
            )
        raise ControlError("this wizard is waiting for a button, not text")

    def onboard_callback(
        self, wizard: dict[str, Any], action: str, parts: Sequence[str], decision
    ) -> ControlResult:
        wizard_id = str(wizard["wizard_id"])
        user_id = int(decision.user_id or 0)
        chat_id = int(decision.chat_id or 0)
        if action == "cancel":
            return self._cancel(wizard, user_id, chat_id)
        if action != "t":
            raise ControlError("unknown new-project action")
        try:
            timeout_seconds = int(parts[0]) if parts else 0
        except (TypeError, ValueError) as exc:
            raise ControlError("invalid runtime selection") from exc
        if timeout_seconds not in RUNTIME_CHOICES:
            raise ControlError("runtime must be one of 1h, 2h, 4h or 8h")
        data = dict(wizard["data"])
        url = _text(data.get("url"))
        if not url:
            raise ControlError("the GitHub URL is missing from this wizard")
        identity = onboarding.parse_github_identity(url)
        title = validate_text(data.get("title"), limit=MAX_TITLE, field="title")
        data["timeout_seconds"] = timeout_seconds
        data["wizard_id"] = wizard_id
        nonce = self.state.create_confirmation(user_id, chat_id, "onboard_project", data)
        self.state.update_wizard(
            wizard_id, user_id, chat_id, step="confirm", data=data, ttl_seconds=WIZARD_TTL
        )
        target = self._projects_root() / identity.name
        return ControlResult(
            render.onboard_preview_text(identity, target, title, timeout_seconds),
            menus.control_confirmation_menu(nonce, "Register and start job"),
        )

    def perform_onboard(self, payload: dict[str, Any], decision) -> ControlResult:
        wizard_id = _text(payload.get("wizard_id"))
        url = validate_text(payload.get("url"), limit=500, field="GitHub repository URL")
        identity = onboarding.parse_github_identity(url)
        timeout_seconds = int(payload.get("timeout_seconds") or 0)
        if not MIN_TIMEOUT <= timeout_seconds <= MAX_TIMEOUT:
            raise ControlError("timeout is outside the supported range")
        description = validate_text(
            payload.get("description"),
            limit=MAX_PROMPT,
            field="task description",
            allow_newlines=True,
        )
        try:
            onboarded = onboarding.onboard(
                url=url,
                registry_path=self.registry.path,
                projects_root=self._projects_root(),
                docs_root=onboarding.DOCS_ROOT,
                state_root=self.config.job_state_root,
            )
        except (onboarding.OnboardError, OSError) as exc:
            raise ControlError(str(exc)) from exc

        self.registry.load(force=True)
        project = project_by_id(self._projects(), onboarded.project_id)
        if project is None or not project.job_eligible or project.repo_real is None:
            return ControlResult(
                render.onboard_result_text(
                    onboarded,
                    None,
                    "the new registration is not yet job-eligible; open Projects and retry",
                ),
                menus.back_to_main(),
                project_id=onboarded.project_id,
            )

        data: dict[str, Any] = {
            "project_id": project.project_id,
            "repo": str(project.repo_real),
            "description": description,
            "timeout_seconds": timeout_seconds,
            "branch": None,
        }
        request = self._normal_start_request(data)
        if wizard_id:
            self.state.delete_wizard(
                wizard_id, int(decision.user_id or 0), int(decision.chat_id or 0)
            )
        key = request.project_id
        try:
            with self.admission.reserve(key):
                self.admission.check_project(key)
                if not self.state.hit_rate_limit(
                    "starts:global", self.config.max_starts_per_hour, 3600
                ):
                    raise ControlError(
                        "start rate limit reached; the project is registered but no job was started"
                    )
                job = self.jobs.start_job(
                    repo=request.repo,
                    title=request.title,
                    prompt=request.prompt,
                    command_criteria=request.command_criteria,
                    manual_criteria=request.manual_criteria,
                    timeout_seconds=request.timeout_seconds,
                    agent=request.agent,
                    model=request.model,
                    branch=request.branch,
                    project_id=request.project_id,
                    registry_path=self.registry.path,
                    read_only=request.read_only,
                )
        except (AdmissionError, ControlError, JobError) as exc:
            return ControlResult(
                render.onboard_result_text(onboarded, None, str(exc)),
                menus.back_to_main(),
                project_id=request.project_id,
            )
        job_id = str(job.get("id"))
        state = str(job.get("state") or "UNKNOWN")
        if state == "RUNNING" and self.notifier is not None:
            self.notifier.notify_started(job, project_id=request.project_id)
        return ControlResult(
            render.onboard_result_text(onboarded, job),
            self._job_menu(job_id, decision),
            job_id=job_id,
            project_id=request.project_id,
            notification="STARTED" if state == "RUNNING" else None,
        )

    def _profile_and_context(
        self, project: ValidatedProject
    ) -> tuple[acceptance_profiles.AcceptanceProfile, tuple[acceptance_profiles.ContextItem, ...]]:
        try:
            profile = acceptance_profiles.resolve_profile(
                project_id=project.project_id,
                platform=project.project.platform,
                repo=project.repo_real or project.project.repo_path,
                registry_path=self.registry.path,
            )
            context = acceptance_profiles.discover_context(
                profile, platform=project.project.platform
            )
        except acceptance_profiles.ProfileError as exc:
            raise ControlError(str(exc)) from exc
        return profile, context

    def _selected_project(self, data: dict[str, Any]) -> ValidatedProject:
        project_id = validate_text(data.get("project_id"), limit=200, field="project")
        project = project_by_id(self._projects(), project_id)
        if project is None or not project.job_eligible or project.repo_real is None:
            raise ControlError("the selected project is no longer job-eligible")
        return project

    def detect_project_mismatch(self, project: ValidatedProject, text: str) -> str | None:
        """Refuse an obvious explicit reference to a different registered project.

        This is deliberately conservative: only explicit GitHub repository URLs
        and absolute project paths are compared. A vague mention of another app
        name is not treated as proof of a mismatch.
        """

        from devjob import project_policy

        references = {
            project_policy.normalise_github_repository(match)
            for match in GITHUB_REFERENCE_RE.findall(text or "")
        }
        references.discard(None)
        paths = ABSOLUTE_PROJECT_PATH_RE.findall(text or "")
        for other in self._projects():
            if other.project_id == project.project_id:
                continue
            repository = project_policy.normalise_github_repository(
                other.project.delivery.github_repository
            )
            if repository and repository in references:
                return (
                    f"the task explicitly names {repository}, which is registered as "
                    f"{other.project_id}, not {project.project_id}. Select the correct "
                    "project or remove the unrelated repository reference."
                )
            if other.repo_real is not None:
                for raw in paths:
                    try:
                        candidate = Path(raw).expanduser().resolve()
                    except (OSError, ValueError):
                        continue
                    try:
                        candidate.relative_to(other.repo_real)
                    except ValueError:
                        continue
                    return (
                        f"the task references {other.project_id} at {other.repo_real}, "
                        f"not the selected {project.project_id}. Select the correct project."
                    )
        return None

    def _normal_start_request(self, data: dict[str, Any]) -> StartRequest:
        project = self._selected_project(data)
        profile, context = self._profile_and_context(project)
        description = validate_text(
            data.get("description"),
            limit=MAX_PROMPT,
            field="task description",
            allow_newlines=True,
        )
        mismatch = self.detect_project_mismatch(project, description)
        if mismatch:
            raise ControlError(mismatch)
        data["title"] = derive_title(description)
        data["prompt"] = compose_task_prompt(description, profile, context)
        data["command_criteria"] = [list(item) for item in profile.command_criteria]
        data["manual_criteria"] = list(profile.manual)
        data["profile_source"] = profile.source
        data["context_paths"] = [str(item.path) for item in context]
        data["branch"] = None
        data["read_only"] = bool(data.get("read_only"))
        return self._start_request(data)

    def start_callback(
        self, wizard: dict[str, Any], action: str, parts: Sequence[str], decision
    ) -> ControlResult:
        wizard_id = str(wizard["wizard_id"])
        chat_id = int(decision.chat_id or 0)
        user_id = int(decision.user_id or 0)
        if action == "cancel":
            return self._cancel(wizard, user_id, chat_id)
        if action == "p":
            if len(parts) < 1:
                raise ControlError("missing project selection")
            try:
                index = int(parts[0])
            except (TypeError, ValueError) as exc:
                raise ControlError("invalid project selection") from exc
            projects = self._eligible()
            project_ids = list(wizard["data"].get("project_ids") or [])
            if index < 0 or index >= len(project_ids):
                raise ControlError("project selection is no longer available")
            project_id = project_ids[index]
            project = project_by_id(projects, project_id)
            if project is None or not project.job_eligible or project.repo_real is None:
                raise ControlError("the selected project is no longer job-eligible")
            data = dict(wizard["data"])
            data.update(
                {
                    "project_id": project.project_id,
                    "repo": str(project.repo_real),
                    "step_count": int(data.get("step_count") or 0) + 1,
                }
            )
            self.state.update_wizard(
                wizard_id, user_id, chat_id, step="prompt", data=data, ttl_seconds=WIZARD_TTL
            )
            return ControlResult(
                render.start_description_text(project),
                menus.wizard_cancel_menu(wizard_id),
            )
        if action == "t":
            if str(wizard.get("step")) not in {"runtime", "prompt"}:
                raise ControlError("runtime selection is not available at this step")
            try:
                timeout_seconds = int(parts[0]) if parts else 0
            except (TypeError, ValueError) as exc:
                raise ControlError("invalid runtime selection") from exc
            if timeout_seconds not in RUNTIME_CHOICES:
                raise ControlError("runtime must be one of 1h, 2h, 4h or 8h")
            data = dict(wizard["data"])
            data["timeout_seconds"] = timeout_seconds
            request = self._normal_start_request(data)
            self.state.update_wizard(
                wizard_id, user_id, chat_id, step="preview", data=data, ttl_seconds=WIZARD_TTL
            )
            return self._start_preview(wizard_id, request, user_id, chat_id)
        if action == "ro":
            if str(wizard.get("step")) not in {"runtime", "preview", "prompt"}:
                raise ControlError("read-only mode is not available at this step")
            data = dict(wizard["data"])
            data["read_only"] = not bool(data.get("read_only"))
            if str(wizard.get("step")) == "preview":
                request = self._start_request(data)
                self.state.update_wizard(
                    wizard_id, user_id, chat_id, step="preview", data=data, ttl_seconds=WIZARD_TTL
                )
                return self._start_preview(wizard_id, request, user_id, chat_id)
            self.state.update_wizard(
                wizard_id, user_id, chat_id, step="runtime", data=data, ttl_seconds=WIZARD_TTL
            )
            return ControlResult(
                render.start_runtime_text(
                    data.get("title") or "", read_only=bool(data.get("read_only"))
                ),
                menus.start_runtime_menu(wizard_id, read_only=bool(data.get("read_only"))),
            )
        if action == "a":
            if str(wizard.get("step")) not in {"runtime", "preview", "prompt"}:
                raise ControlError("advanced options are not available at this step")
            data = dict(wizard["data"])
            self.state.update_wizard(
                wizard_id, user_id, chat_id, step="criteria", data=data, ttl_seconds=WIZARD_TTL
            )
            return ControlResult(
                render.start_criteria_text(), menus.wizard_cancel_menu(wizard_id)
            )
        raise ControlError("unknown start-wizard action")

    def start_text(self, wizard: dict[str, Any], text: str, decision) -> ControlResult:
        wizard_id = str(wizard["wizard_id"])
        chat_id = int(decision.chat_id or 0)
        user_id = int(decision.user_id or 0)
        data = dict(wizard["data"])
        step = str(wizard["step"])

        if step in {"prompt", "title"}:
            # "title" is accepted only for a wizard created by an older monitor.
            description = validate_text(
                text,
                limit=MAX_PROMPT,
                field="task description",
                allow_newlines=True,
            )
            data["description"] = description
            data["title"] = derive_title(description)
            self.state.update_wizard(
                wizard_id, user_id, chat_id, step="runtime", data=data, ttl_seconds=WIZARD_TTL
            )
            return ControlResult(
                render.start_runtime_text(data["title"]),
                menus.start_runtime_menu(wizard_id),
            )
        if step == "criteria":
            commands, manuals = parse_criteria(text)
            data["command_criteria"] = [list(item) for item in commands]
            data["manual_criteria"] = list(manuals)
            if not data.get("prompt") and data.get("description"):
                data["prompt"] = str(data["description"])
            self.state.update_wizard(
                wizard_id, user_id, chat_id, step="timeout", data=data, ttl_seconds=WIZARD_TTL
            )
            return ControlResult(
                render.start_timeout_text(), menus.wizard_cancel_menu(wizard_id)
            )
        if step == "timeout":
            data["timeout_seconds"] = parse_timeout(text)
            self.state.update_wizard(
                wizard_id, user_id, chat_id, step="branch", data=data, ttl_seconds=WIZARD_TTL
            )
            return ControlResult(
                render.start_branch_text(), menus.wizard_cancel_menu(wizard_id)
            )
        if step == "branch":
            if _skip(text):
                data["branch"] = None
            else:
                data["branch"] = validate_text(
                    text, limit=MAX_BRANCH, field="branch label"
                )
            request = self._start_request(data)
            self.state.update_wizard(
                wizard_id, user_id, chat_id, step="preview", data=data, ttl_seconds=WIZARD_TTL
            )
            return self._start_preview(wizard_id, request, user_id, chat_id)
        raise ControlError("this wizard is waiting for a button, not text")

    def _start_request(self, data: dict[str, Any]) -> StartRequest:
        project_id = validate_text(data.get("project_id"), limit=200, field="project")
        repo = validate_text(data.get("repo"), limit=4096, field="repository")
        title = validate_text(data.get("title"), limit=MAX_TITLE, field="title")
        prompt = validate_text(
            data.get("prompt"), limit=MAX_PROMPT, field="prompt", allow_newlines=True
        )
        commands_raw = data.get("command_criteria") or []
        manuals_raw = data.get("manual_criteria") or []
        commands: list[tuple[str, str]] = []
        for item in commands_raw:
            if not isinstance(item, (list, tuple)) or len(item) != 2:
                raise ControlError("stored acceptance commands are malformed")
            label = validate_text(item[0], limit=MAX_LABEL, field="criterion label")
            command = validate_text(item[1], limit=MAX_COMMAND, field="acceptance command")
            commands.append((label, command))
        manuals = [
            validate_text(item, limit=MAX_MANUAL, field="manual criterion")
            for item in manuals_raw
        ]
        if not commands and not manuals:
            raise ControlError("at least one acceptance criterion is required")
        if len(commands) + len(manuals) > MAX_CRITERIA:
            raise ControlError(f"at most {MAX_CRITERIA} acceptance criteria are allowed")
        timeout_seconds = int(data.get("timeout_seconds") or 0)
        if not MIN_TIMEOUT <= timeout_seconds <= MAX_TIMEOUT:
            raise ControlError("timeout is outside the supported range")
        branch = data.get("branch")
        if branch is not None:
            branch = validate_text(branch, limit=MAX_BRANCH, field="branch label")
        agent = validate_text(data.get("agent") or self._default_agent(), limit=120, field="agent")
        model = validate_text(data.get("model") or self._default_model(), limit=200, field="model")
        if agent not in self.config.agent_allowlist:
            raise ControlError("agent is not in the configured allowlist")
        if model not in self.config.model_allowlist:
            raise ControlError("model is not in the configured allowlist")
        # Revalidate against the registry on every preview and confirmation.
        project = project_by_id(self._projects(), project_id)
        if project is None or not project.job_eligible or project.repo_real is None:
            raise ControlError("the selected project is no longer job-eligible")
        if str(project.repo_real) != str(Path(repo).resolve()):
            raise ControlError("the selected repository does not match the registry")
        try:
            policy = self._project_policy(project)
        except (ValueError, RegistryError) as exc:
            raise ControlError(f"project delivery policy is invalid: {exc}") from exc
        if branch is not None and not policy.matches_branch(branch):
            raise ControlError(
                f"branch {branch!r} is outside the project development pattern "
                f"{policy.branch_pattern}; automatic push is not authorized"
            )
        profile_source = data.get("profile_source") or ""
        if profile_source:
            profile_source = validate_text(
                profile_source, limit=300, field="acceptance profile source"
            )
        context_paths = data.get("context_paths") or []
        if not isinstance(context_paths, (list, tuple)):
            raise ControlError("stored context paths are malformed")
        context = tuple(
            validate_text(item, limit=4096, field="context path")
            for item in context_paths
        )
        read_only = bool(data.get("read_only"))
        return StartRequest(
            project_id=project.project_id,
            repo=str(project.repo_real),
            title=title,
            prompt=prompt,
            command_criteria=tuple(commands),
            manual_criteria=tuple(manuals),
            timeout_seconds=timeout_seconds,
            branch=branch,
            agent=agent,
            model=model,
            profile_source=profile_source,
            context_paths=context,
            read_only=read_only,
        )

    def _start_preview(
        self, wizard_id: str, request: StartRequest, user_id: int, chat_id: int
    ) -> ControlResult:
        nonce = self.state.create_confirmation(
            user_id, chat_id, "start_job", request.payload(wizard_id)
        )
        return ControlResult(
            render.start_preview_text(request),
            menus.control_confirmation_menu(nonce, "Create job"),
            project_id=request.project_id,
        )

    def perform_start(self, payload: dict[str, Any], decision) -> ControlResult:
        wizard_id = _text(payload.get("wizard_id"))
        data = {
            "project_id": payload.get("project_id"),
            "repo": payload.get("repo"),
            "title": payload.get("title"),
            "prompt": payload.get("prompt"),
            "command_criteria": payload.get("command_criteria"),
            "manual_criteria": payload.get("manual_criteria"),
            "timeout_seconds": payload.get("timeout_seconds"),
            "branch": payload.get("branch"),
            "agent": payload.get("agent"),
            "model": payload.get("model"),
            "profile_source": payload.get("profile_source"),
            "context_paths": payload.get("context_paths"),
            "read_only": payload.get("read_only"),
        }
        request = self._start_request(data)
        key = request.project_id
        try:
            with self.admission.reserve(key):
                self.admission.check_project(key)
                if not self.state.hit_rate_limit(
                    "starts:global", self.config.max_starts_per_hour, 3600
                ):
                    raise ControlError(
                        "start rate limit reached; wait before starting another job"
                    )
                job = self.jobs.start_job(
                    repo=request.repo,
                    title=request.title,
                    prompt=request.prompt,
                    command_criteria=request.command_criteria,
                    manual_criteria=request.manual_criteria,
                    timeout_seconds=request.timeout_seconds,
                    agent=request.agent,
                    model=request.model,
                    branch=request.branch,
                    project_id=request.project_id,
                    registry_path=self.registry.path,
                    read_only=request.read_only,
                )
        except (ProjectBusy, GlobalGuardBusy, AdmissionLockTimeout) as exc:
            raise ControlError(str(exc)) from exc
        except AdmissionError as exc:
            raise ControlError(str(exc)) from exc
        if wizard_id:
            self.state.delete_wizard(
                wizard_id, int(decision.user_id or 0), int(decision.chat_id or 0)
            )
        job_id = str(job.get("id"))
        state = str(job.get("state") or "UNKNOWN")
        if state == "RUNNING":
            if self.notifier is not None:
                self.notifier.notify_started(job, project_id=request.project_id)
            return ControlResult(
                render.job_started_text(job, request.project_id),
                self._job_menu(job_id, decision),
                job_id=job_id,
                project_id=request.project_id,
                notification="STARTED",
            )
        return ControlResult(
            render.job_refused_text(job, request.project_id),
            self._job_menu(job_id, decision),
            job_id=job_id,
            project_id=request.project_id,
        )

    # ---- resume wizard -----------------------------------------------------------
    def begin_resume(self, job_id: str, user_id: int, chat_id: int) -> ControlResult:
        job_id = validate_job_id(job_id)
        job = self.jobs.job_status(job_id)
        if str(job.get("state")) == "RUNNING":
            raise ControlError("this job is RUNNING; cancel it before resuming")
        data = {
            "job_id": job_id,
            "prompt": None,
            "timeout_seconds": None,
            "new_session": False,
            "force": False,
        }
        wizard_id = self.state.create_wizard(
            user_id, chat_id, "resume", "preview", data, ttl_seconds=WIZARD_TTL
        )
        wizard = {"wizard_id": wizard_id, "kind": "resume", "step": "preview", "data": data}
        return self._resume_preview(wizard, job, user_id, chat_id)

    def resume_callback(
        self, wizard: dict[str, Any], action: str, parts: Sequence[str], decision
    ) -> ControlResult:
        wizard_id = str(wizard["wizard_id"])
        user_id = int(decision.user_id or 0)
        chat_id = int(decision.chat_id or 0)
        if action == "cancel":
            return self._cancel(wizard, user_id, chat_id)
        data = dict(wizard["data"])
        job_id = _text(data.get("job_id"))
        if action == "i":
            self.state.update_wizard(
                wizard_id, user_id, chat_id, step="prompt", data=data, ttl_seconds=WIZARD_TTL
            )
            return ControlResult(
                render.resume_prompt_text(), menus.wizard_cancel_menu(wizard_id)
            )
        if action in {"ns", "force"}:
            if action == "ns":
                data["new_session"] = not bool(data.get("new_session"))
            else:
                data["force"] = not bool(data.get("force"))
            self.state.update_wizard(
                wizard_id, user_id, chat_id, step="preview", data=data, ttl_seconds=WIZARD_TTL
            )
            job = self.jobs.job_status(validate_job_id(job_id))
            return self._resume_preview(wizard | {"data": data}, job, user_id, chat_id)
        if action == "confirm":
            job = self.jobs.job_status(validate_job_id(job_id))
            request = self._resume_request(data)
            self._resume_preconditions(job, request)
            pending = self.state.list_owner_messages(job_id, pending_only=True)
            composed = compose_resume_prompt(
                request.prompt, pending, limit=MAX_PROMPT
            )
            confirmation_payload = request.payload(wizard_id)
            confirmation_payload["prompt"] = composed
            confirmation_payload["owner_message_ids"] = [
                str(item["message_id"]) for item in pending
            ]
            nonce = self.state.create_confirmation(
                user_id, chat_id, "resume_job", confirmation_payload
            )
            self.state.update_wizard(
                wizard_id, user_id, chat_id, step="confirm", data=data, ttl_seconds=WIZARD_TTL
            )
            confirmation_request = ResumeRequest(
                job_id=request.job_id,
                prompt=composed,
                timeout_seconds=request.timeout_seconds,
                new_session=request.new_session,
                force=request.force,
            )
            return ControlResult(
                render.resume_confirmation_text(job, confirmation_request, len(pending)),
                menus.control_confirmation_menu(nonce, "Resume job"),
                job_id=job_id,
            )
        raise ControlError("unknown resume-wizard action")

    def resume_text(self, wizard: dict[str, Any], text: str, decision) -> ControlResult:
        if str(wizard["step"]) != "prompt":
            raise ControlError("this wizard is waiting for a button, not text")
        wizard_id = str(wizard["wizard_id"])
        user_id = int(decision.user_id or 0)
        chat_id = int(decision.chat_id or 0)
        data = dict(wizard["data"])
        if _skip(text):
            data["prompt"] = None
        else:
            data["prompt"] = validate_text(
                text, limit=MAX_PROMPT, field="resume instruction", allow_newlines=True
            )
        self.state.update_wizard(
            wizard_id, user_id, chat_id, step="preview", data=data, ttl_seconds=WIZARD_TTL
        )
        job = self.jobs.job_status(validate_job_id(_text(data.get("job_id"))))
        return self._resume_preview(wizard | {"data": data}, job, user_id, chat_id)

    def _resume_preview(
        self, wizard: dict[str, Any], job: dict, user_id: int, chat_id: int
    ) -> ControlResult:
        data = dict(wizard["data"])
        pending = self.state.list_owner_messages(str(job["id"]), pending_only=True)
        return ControlResult(
            render.resume_preview_text(job, data, pending),
            menus.resume_preview_menu(
                str(wizard["wizard_id"]),
                job_ref=self.state.get_or_create_job_ref(str(job["id"]), chat_id),
                new_session=bool(data.get("new_session")),
                force=bool(data.get("force")),
            ),
            job_id=str(job.get("id")),
        )

    def _resume_request(self, data: dict[str, Any]) -> ResumeRequest:
        job_id = validate_job_id(_text(data.get("job_id")))
        prompt = data.get("prompt")
        if prompt is not None:
            prompt = validate_text(
                prompt, limit=MAX_PROMPT, field="resume instruction", allow_newlines=True
            )
        timeout = data.get("timeout_seconds")
        if timeout is not None:
            timeout = int(timeout)
            if not MIN_TIMEOUT <= timeout <= MAX_TIMEOUT:
                raise ControlError("timeout is outside the supported range")
        return ResumeRequest(
            job_id=job_id,
            prompt=prompt,
            timeout_seconds=timeout,
            new_session=bool(data.get("new_session")),
            force=bool(data.get("force")),
        )

    def _resume_preconditions(self, job: dict, request: ResumeRequest) -> None:
        state = str(job.get("state"))
        if state == "RUNNING":
            raise ControlError("this job is RUNNING; cancel it before resuming")
        if state == "SUCCESS" and not request.force:
            raise ControlError(
                "this job already succeeded; enable Force rerun only if another attempt is intended"
            )
        attempts = job.get("attempts") or 0
        attempt_count = len(attempts) if isinstance(attempts, list) else int(attempts)
        if (
            not request.new_session
            and attempt_count > 0
            and not job.get("session_id")
        ):
            raise ControlError(
                "the OpenCode session id is unknown; enable New session to continue safely"
            )

    def perform_resume(self, payload: dict[str, Any], decision) -> ControlResult:
        wizard_id = _text(payload.get("wizard_id"))
        data = {
            "job_id": payload.get("job_id"),
            "prompt": payload.get("prompt"),
            "timeout_seconds": payload.get("timeout_seconds"),
            "new_session": payload.get("new_session"),
            "force": payload.get("force"),
        }
        request = self._resume_request(data)
        owner_message_ids = [
            str(item)
            for item in (payload.get("owner_message_ids") or [])
            if isinstance(item, str) and item
        ]
        job = self.jobs.job_status(request.job_id)
        self._resume_preconditions(job, request)
        previous_attempts = job.get("attempts") or 0
        previous_attempt_count = (
            len(previous_attempts)
            if isinstance(previous_attempts, list)
            else int(previous_attempts)
        )
        key = self.admission.project_key_for_job(job)
        try:
            with self.admission.reserve(key):
                self.admission.check_project(
                    key, exclude_job_id=request.job_id
                )
                resumed = self.jobs.resume_job(
                    request.job_id,
                    prompt=request.prompt,
                    timeout_seconds=request.timeout_seconds,
                    new_session=request.new_session,
                    force=request.force,
                )
        except (ProjectBusy, GlobalGuardBusy, AdmissionLockTimeout) as exc:
            if owner_message_ids:
                self.state.record_owner_message_error(owner_message_ids, str(exc))
            raise ControlError(str(exc)) from exc
        except AdmissionError as exc:
            if owner_message_ids:
                self.state.record_owner_message_error(owner_message_ids, str(exc))
            raise ControlError(str(exc)) from exc
        except (JobError, ControlError) as exc:
            if owner_message_ids:
                self.state.record_owner_message_error(owner_message_ids, str(exc))
            raise
        if wizard_id:
            self.state.delete_wizard(
                wizard_id, int(decision.user_id or 0), int(decision.chat_id or 0)
            )
        if not isinstance(resumed, dict) or not resumed.get("id"):
            raise ControlError("Workflow v3 returned an unexpected resume result")
        job_id = str(resumed.get("id"))
        if str(resumed.get("state")) != "RUNNING":
            return ControlResult(
                render.job_refused_text(resumed, resumed=True),
                self._job_menu(job_id, decision),
                job_id=job_id,
            )
        if owner_message_ids:
            delivered = self.state.mark_owner_messages_delivered(
                owner_message_ids,
                int(resumed.get("attempt_number") or (previous_attempt_count + 1)),
            )
            resumed["owner_messages_delivered"] = delivered
        if self.notifier is not None:
            self.notifier.notify_resumed(resumed)
        return ControlResult(
            render.job_resumed_text(resumed),
            self._job_menu(job_id, decision),
            job_id=job_id,
            notification="RESUMED",
        )

    def _job_menu(self, job_id: str, decision) -> dict:
        ref = self.state.get_or_create_job_ref(job_id, int(decision.chat_id or 0))
        resumable = False
        cancellable = False
        try:
            job = self.jobs.job_status(job_id)
            resumable, cancellable = menus.job_action_flags(job)
        except JobError:
            pass
        return menus.job_menu(
            ref, control=True, resumable=resumable, cancellable=cancellable
        )
