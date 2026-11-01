"""Read-only parser and validator for PROJECT-REGISTRY.md.

Only the verified registered-projects table is routable. Platform source
references and deferred entries are intentionally not parsed as projects. A
parse failure fails closed for future job mutation while still allowing document
browsing from explicitly configured roots.

Each project also carries a validated delivery policy from the registry columns
``Git remote``, ``GitHub repository``, ``Development branch pattern`` and
``Automatic push``. A project with an unavailable repository or an invalid
policy remains visible for document browsing but is not job-eligible.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from devjob import project_policy

SECTION = "## Registered projects"
RegistryError = project_policy.RegistryError


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


@dataclass(frozen=True)
class Project:
    project_id: str
    platform: str
    repo_path: Path
    has_project_agents: bool
    central_root: Path
    delivery: project_policy.DeliveryConfig = field(
        default_factory=project_policy.DeliveryConfig
    )

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
    delivery: project_policy.DeliveryPolicy
    reason: str = ""

    @property
    def project_id(self) -> str:
        return self.project.project_id

    @property
    def delivery_valid(self) -> bool:
        return bool(self.repo_available and self.delivery.valid)

    @property
    def job_eligible(self) -> bool:
        return bool(self.repo_available and self.delivery.valid)

    def __repr__(self) -> str:
        return (
            f"ValidatedProject({self.project.project_id!r}, "
            f"repo_available={self.repo_available}, docs_available={self.docs_available}, "
            f"delivery_valid={self.delivery_valid})"
        )


def parse_registry(path: str | Path) -> list[Project]:
    raw_projects = project_policy.parse_registry(path)
    return [
        Project(
            project_id=item.project_id,
            platform=item.platform,
            repo_path=item.repo_path,
            has_project_agents=item.has_project_agents,
            central_root=item.central_root,
            delivery=item.delivery,
        )
        for item in raw_projects
    ]


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

        policy = project_policy.validate_delivery(
            project.delivery,
            repo_real or project.repo_path,
            project.project_id,
        )
        validated.append(
            ValidatedProject(
                project=project,
                repo_available=repo_available,
                repo_real=repo_real,
                docs_available=docs_available,
                docs_real=docs_real,
                delivery=policy,
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
