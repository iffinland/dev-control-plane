"""Verified project acceptance profiles and task-context discovery.

The Telegram start flow intentionally asks the owner for only three things:
project, task description and maximum runtime. Acceptance criteria therefore
come from a project-specific profile instead of being typed into a phone.

A profile is a small, explicit JSON document. It is never inferred from a test
file name or from a package manager guess. Two discovery locations are
supported:

1. ``<repository>/.workflow/acceptance.json`` (project-owned, preferred);
2. ``acceptance-profiles.json`` next to the project registry, keyed by the
   registered project ID (central fallback).

Both are read-only inputs. A missing, malformed, empty or unsafe profile fails
closed with a user-facing error; this module never silently invents commands.
The mandatory Workflow v3 completion contract, GitHub delivery policy and branch
protection remain independent and are not weakened here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

CONTROL_PLANE = Path(__file__).resolve().parents[2]
PROJECT_PROFILE_RELATIVE = Path(".workflow/acceptance.json")
CENTRAL_PROFILE_NAME = "acceptance-profiles.json"
MAX_COMMANDS = 12
MAX_COMMAND = 1000
MAX_LABEL = 80
MAX_MANUAL = 300
MAX_TIMEOUT = 8 * 3600
DEFAULT_TIMEOUT = 1800
MAX_CONTEXT_ITEMS = 24


class ProfileError(ValueError):
    """A safe acceptance profile could not be resolved."""


@dataclass(frozen=True)
class AcceptanceCommand:
    label: str
    command: str
    timeout_seconds: int = DEFAULT_TIMEOUT

    def as_criterion(self) -> tuple[str, str]:
        return (self.label, self.command)


@dataclass(frozen=True)
class AcceptanceProfile:
    project_id: str
    commands: tuple[AcceptanceCommand, ...]
    manual: tuple[str, ...] = ()
    source: str = ""
    docs: tuple[str, ...] = ()
    skills: tuple[str, ...] = ()
    central_root: Path | None = None
    project_root: Path | None = None

    @property
    def command_criteria(self) -> tuple[tuple[str, str], ...]:
        return tuple(item.as_criterion() for item in self.commands)

    def summary_line(self) -> str:
        count = len(self.commands) + len(self.manual)
        return f"{count} criterion{'' if count == 1 else 'a'} from {self.source}"


@dataclass(frozen=True)
class ContextItem:
    kind: str
    path: Path

    def label(self) -> str:
        return f"{self.kind}: {self.path}"


def central_profiles_path(registry_path: str | Path | None = None) -> Path:
    """Return the central profile file next to the registry (or the default)."""

    if registry_path:
        return Path(registry_path).expanduser().resolve().parent / CENTRAL_PROFILE_NAME
    return CONTROL_PLANE / CENTRAL_PROFILE_NAME


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ProfileError(f"acceptance profile could not be read: {path.name}") from exc
    except json.JSONDecodeError as exc:
        raise ProfileError(f"acceptance profile is not valid JSON: {path.name}") from exc
    if not isinstance(data, dict):
        raise ProfileError(f"acceptance profile must be a JSON object: {path.name}")
    return data


def _text(value: object, *, field_name: str, limit: int) -> str:
    if not isinstance(value, str):
        raise ProfileError(f"{field_name} must be text")
    cleaned = value.strip()
    if not cleaned:
        raise ProfileError(f"{field_name} must not be empty")
    if "\x00" in cleaned:
        raise ProfileError(f"{field_name} contains a NUL character")
    if len(cleaned) > limit:
        raise ProfileError(f"{field_name} is longer than {limit} characters")
    return cleaned


def _commands(value: object, *, field_name: str) -> tuple[AcceptanceCommand, ...]:
    if not isinstance(value, list) or not value:
        raise ProfileError(f"{field_name} must be a non-empty list of commands")
    if len(value) > MAX_COMMANDS:
        raise ProfileError(f"{field_name} has more than {MAX_COMMANDS} commands")
    commands: list[AcceptanceCommand] = []
    for index, item in enumerate(value, start=1):
        if isinstance(item, str):
            command = _text(item, field_name=f"{field_name}[{index}]", limit=MAX_COMMAND)
            label = f"Acceptance {index}"
            timeout = DEFAULT_TIMEOUT
        elif isinstance(item, dict):
            label = _text(
                item.get("label") or f"Acceptance {index}",
                field_name=f"{field_name}[{index}].label",
                limit=MAX_LABEL,
            )
            command = _text(
                item.get("command"),
                field_name=f"{field_name}[{index}].command",
                limit=MAX_COMMAND,
            )
            try:
                timeout = int(item.get("timeout_seconds", DEFAULT_TIMEOUT))
            except (TypeError, ValueError) as exc:
                raise ProfileError(
                    f"{field_name}[{index}].timeout_seconds must be an integer"
                ) from exc
            if not 1 <= timeout <= MAX_TIMEOUT:
                raise ProfileError(
                    f"{field_name}[{index}].timeout_seconds is outside 1..{MAX_TIMEOUT}"
                )
        else:
            raise ProfileError(f"{field_name}[{index}] must be a string or object")
        commands.append(AcceptanceCommand(label=label, command=command, timeout_seconds=timeout))
    return tuple(commands)


def _strings(value: object, *, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ProfileError(f"{field_name} must be a list")
    result: list[str] = []
    for index, item in enumerate(value, start=1):
        result.append(_text(item, field_name=f"{field_name}[{index}]", limit=MAX_COMMAND))
    return tuple(result)


def _safe_relative(value: str, *, field_name: str) -> Path:
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        raise ProfileError(f"{field_name} must be a relative path inside its root")
    if any(part.startswith(".") and part not in {".workflow", ".github"} for part in relative.parts):
        raise ProfileError(f"{field_name} must not contain hidden path segments")
    return relative


def _resolve_listed(
    values: Iterable[str],
    *,
    root: Path,
    field_name: str,
) -> tuple[str, ...]:
    root = root.expanduser().resolve()
    result: list[str] = []
    for value in values:
        relative = _safe_relative(value, field_name=field_name)
        candidate = (root / relative).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as exc:
            raise ProfileError(f"{field_name} escapes its root: {value}") from exc
        if not candidate.is_file():
            raise ProfileError(f"{field_name} does not exist: {value}")
        text = str(candidate)
        if text not in result:
            result.append(text)
    return tuple(result)


def _project_profile(
    repo: Path, project_id: str, platform: str
) -> AcceptanceProfile | None:
    path = (repo / PROJECT_PROFILE_RELATIVE).resolve()
    if not path.is_file():
        return None
    data = _read_json(path)
    raw_commands = data.get("commands")
    commands = (
        _commands(raw_commands, field_name="commands")
        if raw_commands not in (None, [])
        else ()
    )
    manual = _strings(data.get("manual"), field_name="manual")
    if not commands and not manual:
        raise ProfileError(
            "commands must be a non-empty list or a manual criterion must be present"
        )
    docs = _resolve_listed(
        _strings(data.get("docs"), field_name="docs"),
        root=repo,
        field_name="docs",
    )
    skills = _resolve_listed(
        _strings(data.get("skills"), field_name="skills"),
        root=repo,
        field_name="skills",
    )
    return AcceptanceProfile(
        project_id=project_id,
        commands=commands,
        manual=manual,
        source=f"project profile {PROJECT_PROFILE_RELATIVE.as_posix()}",
        docs=docs,
        skills=skills,
        project_root=repo,
    )


def _central_profile(
    registry_path: str | Path | None,
    project_id: str,
    platform: str,
    repo: Path,
) -> AcceptanceProfile | None:
    path = central_profiles_path(registry_path)
    if not path.is_file():
        return None
    data = _read_json(path)
    profiles = data.get("profiles")
    if not isinstance(profiles, dict):
        raise ProfileError("central acceptance profiles must contain a 'profiles' object")
    entry = profiles.get(project_id)
    if entry is None:
        return None
    if not isinstance(entry, dict):
        raise ProfileError(f"acceptance profile for {project_id} must be an object")
    raw_commands = entry.get("commands")
    commands = (
        _commands(raw_commands, field_name="commands")
        if raw_commands not in (None, [])
        else ()
    )
    manual = _strings(entry.get("manual"), field_name="manual")
    if not commands and not manual:
        raise ProfileError(
            f"acceptance profile for {project_id} needs a command or manual criterion"
        )
    # Central context paths are relative to the control-plane checkout.
    docs = _resolve_listed(
        _strings(entry.get("docs"), field_name="docs"),
        root=CONTROL_PLANE,
        field_name="docs",
    )
    skills = _resolve_listed(
        _strings(entry.get("skills"), field_name="skills"),
        root=CONTROL_PLANE,
        field_name="skills",
    )
    source = str(entry.get("source") or f"central profile {path.name}")
    return AcceptanceProfile(
        project_id=project_id,
        commands=commands,
        manual=manual,
        source=source,
        docs=docs,
        skills=skills,
        project_root=repo,
    )


def resolve_profile(
    *,
    project_id: str,
    platform: str,
    repo: str | Path,
    registry_path: str | Path | None = None,
) -> AcceptanceProfile:
    """Resolve exactly one safe profile for a registered project.

    A project-local profile takes precedence over the central file. If neither
    exists, or the selected profile is malformed, this raises ``ProfileError``.
    No command is guessed from repository contents.
    """

    project_root = Path(repo).expanduser().resolve()
    try:
        project = _project_profile(project_root, project_id, platform)
    except ProfileError as exc:
        raise ProfileError(f"project acceptance profile is invalid: {exc}") from exc
    if project is not None:
        return project
    try:
        central = _central_profile(registry_path, project_id, platform, project_root)
    except ProfileError as exc:
        raise ProfileError(f"central acceptance profile is invalid: {exc}") from exc
    if central is not None:
        return central
    raise ProfileError(
        f"no verified acceptance profile is configured for {project_id}. "
        "Add .workflow/acceptance.json in the project or a matching entry in "
        f"{central_profiles_path(registry_path).name}. A job is not started "
        "without explicit acceptance commands."
    )


def discover_context(
    profile: AcceptanceProfile,
    *,
    platform: str,
    platform_pack: str | None = None,
) -> tuple[ContextItem, ...]:
    """Return existing instruction/document/skill paths for the task prompt.

    Only paths explicitly listed by the profile, the standard control-plane
    contract, the matching platform pack, the project AGENTS.md and the central
    report root are included. Nothing is recursively imported or concatenated.
    """

    items: list[ContextItem] = []
    seen: set[str] = set()

    def add(kind: str, path: Path | None) -> None:
        if path is None:
            return
        try:
            resolved = path.expanduser().resolve(strict=True)
        except OSError:
            return
        if not resolved.is_file():
            return
        key = str(resolved)
        if key in seen:
            return
        seen.add(key)
        items.append(ContextItem(kind=kind, path=resolved))

    add("control-plane instruction", CONTROL_PLANE / "AGENTS.md")
    add("control-plane workflow", CONTROL_PLANE / "WORKFLOW.md")
    add("control-plane handoff", CONTROL_PLANE / "GIT-AND-HANDOFF.md")

    pack = platform_pack or platform.lower().strip()
    if pack in {"qortal", "qortium"}:
        add("platform pack", CONTROL_PLANE / "platforms" / pack / "README.md")
    else:
        add("platform pack", CONTROL_PLANE / "platforms" / "README.md")

    add("skill index", CONTROL_PLANE / "skills" / "README.md")
    for skill in profile.skills:
        add("project skill", Path(skill))
    for doc in profile.docs:
        add("project documentation", Path(doc))

    if profile.project_root is not None:
        add("project instruction", profile.project_root / "AGENTS.md")

    return tuple(items[:MAX_CONTEXT_ITEMS])
