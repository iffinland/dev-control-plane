"""Read-only parser and validator for PROJECT-REGISTRY.md.

Only the verified registered-projects table is routable. Platform source
references and deferred entries are intentionally not parsed as projects. A
parse failure fails closed for future job mutation while still allowing document
browsing from explicitly configured roots.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

SECTION = "## Registered projects"


class RegistryError(RuntimeError):
    """The project registry could not be parsed safely."""


def _clean(value: str) -> str:
    return value.strip().strip("`").strip()


def _split_row(line: str) -> list[str]:
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return []
    return [cell.strip() for cell in stripped[1:-1].split("|")]


def _is_separator(cells: Iterable[str]) -> bool:
    return all(cell and set(cell) <= {"-", ":", " "} for cell in cells)


@dataclass(frozen=True)
class Project:
    project_id: str
    platform: str
    repo_path: Path
    has_project_agents: bool
    central_root: Path

    @property
    def slug(self) -> str:
        safe = "".join(ch if ch.isalnum() else "-" for ch in self.project_id.lower())
        while "--" in safe:
            safe = safe.replace("--", "-")
        return safe.strip("-") or "project"


@dataclass(frozen=True)
class ValidatedProject:
    project: Project
    repo_available: bool
    repo_real: Path | None
    docs_available: bool
    docs_real: Path | None
    reason: str = ""

    @property
    def project_id(self) -> str:
        return self.project.project_id

    @property
    def job_eligible(self) -> bool:
        return self.repo_available

    def __repr__(self) -> str:
        return (
            f"ValidatedProject({self.project.project_id!r}, "
            f"repo_available={self.repo_available}, docs_available={self.docs_available})"
        )


def parse_registry(path: str | Path) -> list[Project]:
    target = Path(path).expanduser()
    try:
        lines = target.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise RegistryError(f"project registry could not be read: {exc.__class__.__name__}") from exc

    try:
        start = next(index for index, line in enumerate(lines) if line.strip() == SECTION)
    except StopIteration as exc:
        raise RegistryError("project registry is missing the registered-projects table") from exc

    table: list[list[str]] = []
    for line in lines[start + 1 :]:
        if line.startswith("## "):
            break
        cells = _split_row(line)
        if not cells:
            if table:
                break
            continue
        if _is_separator(cells):
            continue
        table.append(cells)

    if not table:
        raise RegistryError("registered-projects table is empty")
    header = [_clean(cell).lower() for cell in table[0]]
    expected = ("id", "platform", "verified local path")
    positions: dict[str, int] = {}
    for name in expected:
        try:
            positions[name] = header.index(name)
        except ValueError as exc:
            raise RegistryError(f"registered-projects table is missing column: {name}") from exc

    projects: list[Project] = []
    for cells in table[1:]:
        if len(cells) <= max(positions.values()):
            continue
        project_id = _clean(cells[positions["id"]])
        platform = _clean(cells[positions["platform"]])
        repo = _clean(cells[positions["verified local path"]])
        if not project_id or not repo:
            continue
        agents_cell = cells[3] if len(cells) > 3 else ""
        central_cell = cells[5] if len(cells) > 5 else ""
        projects.append(
            Project(
                project_id=project_id,
                platform=platform,
                repo_path=Path(repo),
                has_project_agents=_clean(agents_cell).lower().startswith("yes"),
                central_root=Path(_clean(central_cell)),
            )
        )
    if not projects:
        raise RegistryError("registered-projects table has no project rows")
    return projects


def _under_roots(real: Path, roots: Iterable[Path]) -> bool:
    checked = False
    for root in roots:
        checked = True
        try:
            real.relative_to(Path(root).expanduser().resolve())
            return True
        except ValueError:
            continue
    return not checked


def validate_projects(
    projects: Iterable[Project], allowed_repo_roots: Iterable[Path] = ()
) -> list[ValidatedProject]:
    roots = tuple(Path(root).expanduser().resolve() for root in allowed_repo_roots)
    validated: list[ValidatedProject] = []
    for project in projects:
        repo_available = False
        repo_real: Path | None = None
        reason = ""
        try:
            repo_real = project.repo_path.expanduser().resolve(strict=True)
            if not repo_real.is_dir():
                reason = "repository path is not a directory"
            elif not _under_roots(repo_real, roots):
                reason = "repository path is outside allowed repository roots"
            else:
                repo_available = True
        except OSError:
            reason = "repository path does not exist"

        docs_available = False
        docs_real: Path | None = None
        try:
            docs_real = project.central_root.expanduser().resolve(strict=True)
            docs_available = docs_real.is_dir()
        except OSError:
            docs_available = False

        validated.append(
            ValidatedProject(
                project=project,
                repo_available=repo_available,
                repo_real=repo_real,
                docs_available=docs_available,
                docs_real=docs_real,
                reason=reason,
            )
        )
    return validated


@dataclass
class Registry:
    """Small mtime-aware cache around the registry parser."""

    path: Path
    allowed_repo_roots: tuple[Path, ...] = ()
    ttl_seconds: float = 30.0
    _cache: list[ValidatedProject] | None = field(default=None, repr=False)
    _mtime: float = field(default=-1.0, repr=False)
    _loaded_at: float = field(default=0.0, repr=False)
    _clock: object = field(default=time.monotonic, repr=False)

    def load(self, force: bool = False) -> list[ValidatedProject]:
        try:
            mtime = self.path.stat().st_mtime
        except OSError as exc:
            raise RegistryError("project registry is missing") from exc
        now = float(self._clock())
        if (
            not force
            and self._cache is not None
            and mtime == self._mtime
            and now - self._loaded_at < self.ttl_seconds
        ):
            return self._cache
        projects = parse_registry(self.path)
        validated = validate_projects(projects, self.allowed_repo_roots)
        self._cache = validated
        self._mtime = mtime
        self._loaded_at = now
        return validated

    def project_roots(self, force: bool = False) -> list[ValidatedProject]:
        return [item for item in self.load(force=force) if item.docs_available]


def project_by_id(projects: Iterable[ValidatedProject], project_id: str) -> ValidatedProject | None:
    for item in projects:
        if item.project_id == project_id:
            return item
    return None
