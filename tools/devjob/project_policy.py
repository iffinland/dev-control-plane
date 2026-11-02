"""Canonical project-scoped GitHub delivery policy for Workflow v3.

A new Workflow v3 job must not guess which Git remote to verify. The project
registry carries an explicit delivery policy per registered project:

* the Git remote name (for example ``origin`` or ``dev-control-plane``);
* the expected GitHub repository (``owner/name`` or a GitHub URL);
* the development-branch pattern (``agent/*``);
* whether automatic push is authorized for matching branches.

The policy is validated against the actual checkout before a job is created.
Missing, ambiguous, non-GitHub or mismatched remotes are rejected instead of
silently falling back to another project's remote. Automatic push is limited to
non-protected branches matching the configured ``agent/*`` pattern. Merges,
tags, releases, deployment, QDN writes, wallet transactions and server changes
are never granted by this module.
"""

from __future__ import annotations

import fnmatch
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

CONTROL_PLANE = Path(__file__).resolve().parents[2]
DEFAULT_REGISTRY = CONTROL_PLANE / "PROJECT-REGISTRY.md"
REGISTRY_ENV = "DEV_CONTROL_PLANE_REGISTRY"
SECTION = "## Registered projects"
PROTECTED_BRANCHES = frozenset({"main", "master", "trunk", "release", "production"})
REMOTE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
# Automatic delivery is intentionally limited to agent/* development branches.
BRANCH_PATTERN_RE = re.compile(r"^agent/[A-Za-z0-9._/-]*\*$")
GITHUB_PART_RE = re.compile(r"^[A-Za-z0-9._-]+$")


class RegistryError(RuntimeError):
    """The project registry could not be parsed or is ambiguous."""


class DeliveryPolicyError(ValueError):
    """A validated project delivery policy is missing or unsafe."""


def default_registry_path() -> Path:
    value = os.environ.get(REGISTRY_ENV)
    return Path(value).expanduser() if value else DEFAULT_REGISTRY


def _clean(value: str) -> str:
    return value.strip().strip("`").strip()


def _split_row(line: str) -> list[str]:
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return []
    return [cell.strip() for cell in stripped[1:-1].split("|")]


def _is_separator(cells: Iterable[str]) -> bool:
    return all(cell and set(cell) <= {"-", ":", " "} for cell in cells)


def _normalise_header(value: str) -> str:
    return " ".join(_clean(value).lower().split())


@dataclass(frozen=True)
class DeliveryConfig:
    """Raw registry delivery fields, before validation against a checkout."""

    remote: str | None = None
    github_repository: str | None = None
    branch_pattern: str | None = None
    automatic_push: str | None = None

    @property
    def configured(self) -> bool:
        return bool(
            self.remote
            or self.github_repository
            or self.branch_pattern
            or self.automatic_push
        )


@dataclass(frozen=True)
class RawProject:
    project_id: str
    platform: str
    repo_path: Path
    has_project_agents: bool
    central_root: Path
    delivery: DeliveryConfig = field(default_factory=DeliveryConfig)


@dataclass(frozen=True)
class DeliveryPolicy:
    project_id: str
    repo_path: Path
    remote: str | None
    github_repository: str | None
    branch_pattern: str | None
    automatic_push: bool
    remote_url: str | None = None
    valid: bool = False
    error: str = ""

    def matches_branch(self, branch: str | None) -> bool:
        if not self.valid or not branch or branch in PROTECTED_BRANCHES:
            return False
        if not branch.startswith("agent/"):
            return False
        pattern = self.branch_pattern or ""
        if not BRANCH_PATTERN_RE.match(pattern):
            return False
        return fnmatch.fnmatchcase(branch, pattern)

    def automatic_push_allowed(self, branch: str | None) -> bool:
        return bool(self.automatic_push and self.matches_branch(branch))

    def snapshot(self) -> dict:
        return {
            "version": 1,
            "project_id": self.project_id,
            "repo": str(self.repo_path),
            "remote": self.remote,
            "github_repository": self.github_repository,
            "branch_pattern": self.branch_pattern,
            "automatic_push": self.automatic_push,
            "remote_url": self.remote_url,
        }


def parse_registry(path: str | Path) -> list[RawProject]:
    """Parse only the verified registered-projects table."""

    target = Path(path).expanduser()
    try:
        lines = target.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise RegistryError(
            f"project registry could not be read: {exc.__class__.__name__}"
        ) from exc

    try:
        start = next(index for index, line in enumerate(lines) if line.strip() == SECTION)
    except StopIteration as exc:
        raise RegistryError(
            "project registry is missing the registered-projects table"
        ) from exc

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

    header = [_normalise_header(cell) for cell in table[0]]
    positions: dict[str, int] = {}
    for name in ("id", "platform", "verified local path"):
        try:
            positions[name] = header.index(name)
        except ValueError as exc:
            raise RegistryError(
                f"registered-projects table is missing column: {name}"
            ) from exc

    def optional(*names: str) -> int | None:
        for name in names:
            if name in header:
                return header.index(name)
        return None

    id_pos = positions["id"]
    platform_pos = positions["platform"]
    repo_pos = positions["verified local path"]
    agents_pos = optional("project-level `agents.md`", "project-level agents.md")
    if agents_pos is None:
        for index, name in enumerate(header):
            if name.startswith("project-level"):
                agents_pos = index
                break
    central_pos = optional("central report root")
    remote_pos = optional("git remote")
    github_pos = optional("github repository")
    pattern_pos = optional("development branch pattern")
    push_pos = optional("automatic push")

    projects: list[RawProject] = []
    seen_ids: set[str] = set()
    for cells in table[1:]:
        if len(cells) <= max(id_pos, platform_pos, repo_pos):
            continue
        project_id = _clean(cells[id_pos])
        platform = _clean(cells[platform_pos])
        repo = _clean(cells[repo_pos])
        if not project_id or not repo:
            continue
        if project_id in seen_ids:
            raise RegistryError(f"duplicate registered project id: {project_id}")
        seen_ids.add(project_id)

        def cell(position: int | None) -> str:
            if position is None or len(cells) <= position:
                return ""
            return _clean(cells[position])

        agents_cell = cell(agents_pos)
        central_cell = cell(central_pos)
        projects.append(
            RawProject(
                project_id=project_id,
                platform=platform,
                repo_path=Path(repo),
                has_project_agents=agents_cell.lower().startswith("yes"),
                central_root=Path(central_cell) if central_cell else Path(""),
                delivery=DeliveryConfig(
                    remote=cell(remote_pos) or None,
                    github_repository=cell(github_pos) or None,
                    branch_pattern=cell(pattern_pos) or None,
                    automatic_push=cell(push_pos) or None,
                ),
            )
        )
    if not projects:
        raise RegistryError("registered-projects table has no project rows")
    return projects


def normalise_github_repository(value: str | None) -> str | None:
    """Return ``owner/name`` (case-folded) or ``None`` for a non-GitHub value.

    Accepts the URL forms Git actually stores in a remote: HTTPS (including an
    explicit ``:443`` port), scp-like SSH, ``ssh://``/``git+ssh://`` (including
    an explicit port) and a bare ``owner/name``. Credentials in the URL are not
    echoed or used; only the repository identity is returned.
    """

    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.startswith(("git@github.com:", "github.com:")):
        text = text.split(":", 1)[1]
    else:
        match = re.match(
            r"^(?:git\+ssh|ssh|https?)://(?:[^/@\s]+@)?github\.com(?::\d+)?/(.+)$",
            text,
            re.IGNORECASE,
        )
        if match:
            text = match.group(1)
        elif re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://", text):
            return None
        elif ":" in text and "github.com" in text.lower():
            text = text.split(":", 1)[1]
        elif "/" not in text:
            return None

    text = text.strip().strip("/")
    if text.endswith(".git"):
        text = text[:-4]
    parts = [part for part in text.split("/") if part]
    if len(parts) != 2:
        return None
    owner, repo = parts
    if owner in {".", ".."} or repo in {".", ".."}:
        return None
    if not GITHUB_PART_RE.match(owner) or not GITHUB_PART_RE.match(repo):
        return None
    return f"{owner}/{repo}".casefold()


def normalise_remote_url(value: str | None) -> str | None:
    return normalise_github_repository(value)


def _parse_bool(value: str | None) -> tuple[bool | None, str]:
    if value is None or not str(value).strip():
        return None, "automatic push is not configured"
    text = str(value).strip().casefold()
    if text in {"yes", "true", "1"}:
        return True, ""
    if text in {"no", "false", "0"}:
        return False, ""
    return None, f"automatic push value is invalid: {value!r}"


def _run_git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(["git", *args], 1, "", str(exc))


def validate_delivery(
    config: DeliveryConfig | None,
    repo_path: str | Path,
    project_id: str = "unknown",
) -> DeliveryPolicy:
    """Validate raw registry fields against the actual checkout/remote."""

    path = Path(repo_path).expanduser()
    config = config or DeliveryConfig()
    errors: list[str] = []
    if not config.remote:
        errors.append("missing Git remote name")
    if not config.github_repository:
        errors.append("missing GitHub repository")
    if not config.branch_pattern:
        errors.append("missing development branch pattern")

    automatic_push, auto_error = _parse_bool(config.automatic_push)
    if auto_error:
        errors.append(auto_error)

    remote = (config.remote or "").strip() or None
    if remote and not REMOTE_NAME_RE.match(remote):
        errors.append("Git remote name contains unsupported characters")

    expected_repository = normalise_github_repository(config.github_repository)
    if config.github_repository and expected_repository is None:
        errors.append("GitHub repository must be a github.com owner/name value")

    pattern = (config.branch_pattern or "").strip() or None
    if pattern and not BRANCH_PATTERN_RE.match(pattern):
        errors.append("development branch pattern must be agent/*")

    remote_url = None
    if not errors:
        if _run_git(path, "rev-parse", "--git-dir").returncode != 0:
            errors.append("repository is not a Git checkout")
        else:
            result = _run_git(path, "config", "--get", f"remote.{remote}.url")
            if result.returncode != 0 or not (result.stdout or "").strip():
                errors.append(f"git remote {remote!r} is not configured")
            else:
                remote_url = (result.stdout or "").strip()
                actual_repository = normalise_remote_url(remote_url)
                if actual_repository is None:
                    errors.append(
                        f"remote {remote!r} does not point at a GitHub repository"
                    )
                elif actual_repository != expected_repository:
                    errors.append(
                        f"remote {remote!r} points at {actual_repository}, "
                        f"expected {expected_repository}"
                    )

    return DeliveryPolicy(
        project_id=project_id,
        repo_path=path,
        remote=remote,
        github_repository=expected_repository,
        branch_pattern=pattern,
        automatic_push=bool(automatic_push),
        remote_url=remote_url,
        valid=not errors,
        error="; ".join(errors),
    )


def _same_repo(left: Path, right: Path) -> bool:
    try:
        return left.expanduser().resolve() == right.expanduser().resolve()
    except OSError:
        return left.expanduser().absolute() == right.expanduser().absolute()


def resolve(
    repo: str | Path,
    *,
    registry_path: str | Path | None = None,
    project_id: str | None = None,
) -> DeliveryPolicy:
    """Resolve exactly one validated project policy for a repository.

    A missing registry entry, duplicate match, missing policy columns or a
    mismatched remote raises instead of guessing.
    """

    path = Path(registry_path).expanduser() if registry_path else default_registry_path()
    projects = parse_registry(path)
    repo_path = Path(repo).expanduser()
    if project_id:
        matches = [item for item in projects if item.project_id == project_id]
        if not matches:
            raise DeliveryPolicyError(
                f"project {project_id!r} is not registered in {path}"
            )
        if not _same_repo(matches[0].repo_path, repo_path):
            raise DeliveryPolicyError(
                f"repository {repo_path} does not match registered project "
                f"{project_id} at {matches[0].repo_path}"
            )
    else:
        matches = [
            item for item in projects if _same_repo(item.repo_path, repo_path)
        ]
        if not matches:
            raise DeliveryPolicyError(
                f"repository {repo_path} is not a registered project in {path}; "
                "add a project row with Git remote, GitHub repository, "
                "development branch pattern and automatic push columns"
            )
    if len(matches) > 1:
        identifiers = ", ".join(sorted(item.project_id for item in matches))
        raise DeliveryPolicyError(
            f"repository {repo_path} matches multiple registered projects: {identifiers}"
        )
    project = matches[0]
    policy = validate_delivery(project.delivery, repo_path, project.project_id)
    if not policy.valid:
        raise DeliveryPolicyError(
            f"project {project.project_id} has no valid delivery policy: {policy.error}"
        )
    return policy


def policy_matches_snapshot(policy: DeliveryPolicy, snapshot: dict) -> bool:
    """True when an explicit contract snapshot equals the validated policy."""

    if not isinstance(snapshot, dict):
        return False
    expected = policy.snapshot()
    for key in (
        "project_id",
        "remote",
        "github_repository",
        "branch_pattern",
        "automatic_push",
    ):
        if snapshot.get(key) != expected.get(key):
            return False
    return True
