"""Safe automatic onboarding of a GitHub project for Workflow v3.

The owner supplies only a GitHub URL, a task description and a runtime. This
module validates the repository identity, clones when necessary, inspects the
project without executing any of its scripts, derives a conservative acceptance
profile from well-known manifests, and registers the project in
``PROJECT-REGISTRY.md`` and ``acceptance-profiles.json``.

Safety rules:

* only a GitHub ``owner/name`` identity is accepted; no local paths, file URLs
  or credentials embedded in a URL;
* an existing directory is never overwritten, reset or cleaned;
* no repository script, hook or test command is executed during onboarding;
* duplicate registrations are detected by normalized GitHub repository and by
  path;
* registry/profile writes are serialized by a state-directory lock and applied
  atomically;
* the clone is staged in a temporary sibling and moved into place only after a
  successful clone, so a failed clone never leaves a half-registered project.
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator

from . import git_remote, project_policy, store

CONTROL_PLANE = Path(__file__).resolve().parents[2]
PROJECTS_ROOT = CONTROL_PLANE.parent / "projects"
DOCS_ROOT = CONTROL_PLANE.parent / "docs"
REGISTRY_SECTION = "## Registered projects"
PROJECT_PROFILE = ".workflow/acceptance.json"
CENTRAL_PROFILE = "acceptance-profiles.json"
DEFAULT_TIMEOUT_SECONDS = 300
MAX_INSPECT_BYTES = 256 * 1024
GITHUB_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")
PROJECT_ID_PART_RE = re.compile(r"[^a-z0-9._-]+")


class OnboardError(ValueError):
    """A project cannot be onboarded safely."""


@dataclass(frozen=True)
class GithubIdentity:
    owner: str
    name: str
    repository: str
    url: str


@dataclass(frozen=True)
class ProjectInspection:
    platform: str
    manifests: tuple[str, ...] = ()
    has_agents: bool = False
    has_readme: bool = False
    instructions: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class OnboardedProject:
    project_id: str
    platform: str
    repo_path: Path
    repo_url: str
    github_repository: str
    cloned: bool
    reused_registration: bool
    inspection: ProjectInspection
    commands: tuple[dict, ...] = ()
    manual: tuple[str, ...] = ()
    profile_source: str = ""
    central_root: Path | None = None
    branch: str = ""
    head: str = ""
    notes: tuple[str, ...] = field(default_factory=tuple)


def parse_github_identity(value: str) -> GithubIdentity:
    """Validate a GitHub URL/scp form and return its canonical identity."""

    text = str(value or "").strip()
    if not text or "\x00" in text or any(ch.isspace() for ch in text):
        raise OnboardError("a GitHub repository URL is required")
    if len(text) > 500:
        raise OnboardError("the GitHub repository URL is too long")
    if "://" in text and not re.match(r"^(?:https?|ssh|git\+ssh)://", text, re.I):
        raise OnboardError("only GitHub HTTPS or SSH URLs are supported")
    if "://" not in text and not re.match(r"^[^/@\s]+@[^/:\s]+:", text):
        raise OnboardError(
            "use a GitHub URL such as https://github.com/owner/repo or "
            "git@github.com:owner/repo.git"
        )
    # Reject embedded credentials without echoing them.
    if re.match(r"^https?://[^/@\s]+@", text, re.I):
        raise OnboardError("the URL must not contain embedded credentials")
    repository = project_policy.normalise_github_repository(text)
    if repository is None:
        raise OnboardError(
            "the URL is not a github.com owner/name repository"
        )
    owner, name = repository.split("/", 1)
    if not GITHUB_NAME_RE.match(owner) or not GITHUB_NAME_RE.match(name):
        raise OnboardError("the GitHub owner or repository name is not supported")
    return GithubIdentity(
        owner=owner,
        name=name,
        repository=repository,
        url=text,
    )


def _read_text(path: Path, limit: int = MAX_INSPECT_BYTES) -> str:
    try:
        with path.open("rb") as handle:
            data = handle.read(limit + 1)
    except OSError:
        return ""
    return data[:limit].decode("utf-8", "replace")


def _package_scripts(root: Path) -> tuple[dict, str]:
    raw = _read_text(root / "package.json")
    if not raw:
        return {}, ""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}, ""
    scripts = data.get("scripts") if isinstance(data, dict) else None
    if not isinstance(scripts, dict):
        return {}, ""
    cleaned = {
        str(key): str(value)
        for key, value in scripts.items()
        if isinstance(key, str) and isinstance(value, str)
    }
    manager = "npm"
    if (root / "pnpm-lock.yaml").is_file():
        manager = "pnpm"
    elif (root / "yarn.lock").is_file():
        manager = "yarn"
    return cleaned, manager


def _has_makefile_target(root: Path, target: str) -> bool:
    text = _read_text(root / "Makefile", limit=65536)
    return bool(re.search(rf"^{re.escape(target)}\s*:", text, re.MULTILINE))


def discover_commands(root: str | Path) -> tuple[tuple[dict, ...], tuple[str, ...]]:
    """Return conservative command criteria without executing anything."""

    path = Path(root).expanduser().resolve()
    commands: list[dict] = []
    manual: list[str] = []

    scripts, manager = _package_scripts(path)
    if scripts:
        preferences = (
            ("test", "Test suite"),
            ("test:unit", "Unit tests"),
            ("check", "Project checks"),
            ("lint", "Lint"),
            ("typecheck", "Typecheck"),
            ("build", "Production build"),
        )
        for script, label in preferences:
            if script in scripts:
                commands.append(
                    {
                        "label": label,
                        "command": f"{manager} run {script}",
                        "timeout_seconds": 1800,
                    }
                )

    pyproject = _read_text(path / "pyproject.toml", limit=131072)
    pytest_configured = bool(
        (path / "pytest.ini").is_file()
        or (path / "tox.ini").is_file()
        or "[tool.pytest" in pyproject
        or re.search(r"^\[pytest\]", _read_text(path / "setup.cfg", 65536), re.MULTILINE)
    )
    has_tests_dir = (path / "tests").is_dir()
    if pytest_configured:
        commands.append(
            {"label": "Pytest suite", "command": "python3 -m pytest -q", "timeout_seconds": 1800}
        )
    elif has_tests_dir and any((path / "tests").glob("test_*.py")):
        commands.append(
            {
                "label": "Unittest suite",
                "command": "python3 -m unittest discover -s tests -p 'test_*.py'",
                "timeout_seconds": 1800,
            }
        )

    if (path / "go.mod").is_file():
        commands.append({"label": "Go tests", "command": "go test ./...", "timeout_seconds": 1800})
    if (path / "Cargo.toml").is_file():
        commands.append({"label": "Cargo tests", "command": "cargo test", "timeout_seconds": 1800})
    if not commands and _has_makefile_target(path, "test"):
        commands.append({"label": "Make test", "command": "make test", "timeout_seconds": 1800})

    deduped: list[dict] = []
    seen: set[str] = set()
    for item in commands:
        command = str(item["command"])
        if command in seen:
            continue
        seen.add(command)
        deduped.append(item)

    if not deduped:
        manual.append(
            "Owner verifies the requested functional outcome in the running application"
        )
    return tuple(deduped[:12]), tuple(manual)


def inspect_project(root: str | Path) -> ProjectInspection:
    """Inspect project files and instructions without running project code."""

    path = Path(root).expanduser().resolve()
    manifests = tuple(
        name
        for name in (
            "package.json",
            "pnpm-lock.yaml",
            "yarn.lock",
            "pyproject.toml",
            "requirements.txt",
            "Cargo.toml",
            "go.mod",
            "Makefile",
            "Dockerfile",
        )
        if (path / name).is_file()
    )
    instructions = tuple(
        name
        for name in ("AGENTS.md", "README.md", "CLAUDE.md", PROJECT_PROFILE)
        if (path / name).is_file()
    )
    text = " ".join(
        _read_text(path / name, limit=65536)
        for name in ("README.md", "AGENTS.md", "package.json", "pyproject.toml")
    ).lower()
    qortium = text.count("qortium")
    qortal = text.count("qortal")
    if qortium and qortium >= qortal:
        platform = "Qortium"
    elif qortal:
        platform = "Qortal"
    else:
        platform = "Generic"
    notes: list[str] = []
    if (path / ".gitmodules").is_file():
        notes.append("submodules are not initialized automatically")
    if (path / ".workflow" / "acceptance.json").is_file():
        notes.append("project-owned acceptance profile takes precedence")
    return ProjectInspection(
        platform=platform,
        manifests=manifests,
        has_agents="AGENTS.md" in instructions,
        has_readme="README.md" in instructions,
        instructions=instructions,
        notes=tuple(notes),
    )


def _packs(platform: str) -> tuple[str, list[str]]:
    pack = platform.strip().casefold()
    if pack in {"qortal", "qortium"}:
        return pack, [f"platforms/{pack}/README.md"]
    return "generic", ["platforms/README.md"]


def _project_id(platform: str, name: str) -> str:
    prefix = PROJECT_ID_PART_RE.sub("-", platform.casefold()).strip("-") or "project"
    suffix = PROJECT_ID_PART_RE.sub("-", name.casefold()).strip("-") or "project"
    return f"{prefix}/{suffix}"


def _registry_rows(text: str) -> tuple[list[int], list[list[str]]]:
    lines = text.splitlines()
    try:
        start = next(index for index, line in enumerate(lines) if line.strip() == REGISTRY_SECTION)
    except StopIteration as exc:
        raise OnboardError("PROJECT-REGISTRY.md has no registered-projects table") from exc
    table_start = None
    table_end = None
    for index in range(start + 1, len(lines)):
        line = lines[index]
        if line.startswith("## ") and table_start is not None:
            break
        if not line.strip():
            if table_start is not None:
                break
            continue
        if line.strip().startswith("|"):
            if table_start is None:
                table_start = index
            table_end = index
    if table_start is None or table_end is None:
        raise OnboardError("PROJECT-REGISTRY.md has no registered-projects table")
    rows: list[list[str]] = []
    for index in range(table_start, table_end + 1):
        stripped = lines[index].strip()
        if not stripped.startswith("|") or not stripped.endswith("|"):
            continue
        cells = [cell.strip() for cell in stripped[1:-1].split("|")]
        if cells and all(set(cell) <= {"-", ":", " "} for cell in cells if cell):
            continue
        if index == table_start:
            continue
        rows.append(cells)
    return list(range(table_start, table_end + 1)), rows


def _existing_registration(
    text: str, path: Path, repository: str
) -> tuple[str, str] | None:
    _indexes, rows = _registry_rows(text)
    for cells in rows:
        if len(cells) < 10:
            continue
        project_id = cells[0].strip("` ")
        repo_cell = cells[2].strip("` ")
        github_cell = cells[7].strip("` ")
        if repo_cell and Path(repo_cell).expanduser().resolve() == path:
            return project_id, cells[1].strip("` ")
        if project_policy.normalise_github_repository(github_cell) == repository:
            return project_id, cells[1].strip("` ")
    return None


def _format_row(values: Iterable[str]) -> str:
    return "| " + " | ".join(str(value) for value in values) + " |"


def _append_registry_row(
    registry_path: Path,
    *,
    project_id: str,
    platform: str,
    repo_path: Path,
    has_agents: bool,
    central_root: Path,
    github_repository: str,
) -> None:
    text = registry_path.read_text(encoding="utf-8")
    indexes, _rows = _registry_rows(text)
    lines = text.splitlines()
    insert_at = indexes[-1] + 1
    row = _format_row(
        [
            f"`{project_id}`",
            platform,
            f"`{repo_path}`",
            "Yes" if has_agents else "No; inherits this control plane",
            "Pending Phase 2 import",
            f"`{central_root}/`",
            "`origin`",
            f"`{github_repository}`",
            "`agent/*`",
            "`yes`",
        ]
    )
    lines.insert(insert_at, row)
    _atomic_write(registry_path, "\n".join(lines) + "\n")


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = 0o644
    try:
        mode = path.stat().st_mode & 0o777
    except OSError:
        pass
    fd, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except OSError:
            pass


@contextmanager
def _state_lock(state_root: str | Path, name: str, timeout: float = 30.0) -> Iterator[None]:
    directory = store.ensure_private_dir(store.state_root(state_root) / "locks")
    path = directory / f"onboarding-{name}.lock"
    handle = path.open("a+", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    try:
        deadline = time.monotonic() + max(0.1, float(timeout))
        while True:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError as exc:
                if time.monotonic() >= deadline:
                    raise OnboardError(
                        "another project onboarding is already modifying the registry"
                    ) from exc
                time.sleep(0.05)
        yield
    finally:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def _git(path: Path | None, *args: str, timeout: int = 60) -> subprocess.CompletedProcess:
    return git_remote.run_git(path, *args, timeout=timeout)


def _clone(url: str, target: Path, *, timeout: int) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(
        tempfile.mkdtemp(prefix=f".{target.name}.onboarding-", dir=str(target.parent))
    )
    try:
        env = git_remote.noninteractive_env(url)
        result = subprocess.run(
            [
                "git",
                "clone",
                "--no-recurse-submodules",
                "--",
                url,
                str(staging / "checkout"),
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=env,
        )
        if result.returncode != 0:
            kind = git_remote.classify_failure(result.stderr or "", result.returncode)
            raise OnboardError(
                f"git clone failed ({kind} failure); the owner checkout was not changed"
            )
        checkout = staging / "checkout"
        if target.exists():
            raise OnboardError(f"target path already exists: {target}")
        os.replace(checkout, target)
    except subprocess.TimeoutExpired as exc:
        raise OnboardError(
            "git clone timed out; no project was registered and no owner work was changed"
        ) from exc
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _profile_entry(
    inspection: ProjectInspection,
    commands: tuple[dict, ...],
    manual: tuple[str, ...],
    repository: str,
) -> dict:
    _pack, docs = _packs(inspection.platform)
    skills = ["skills/shared/workflow-v3-completion-contract/SKILL.md"]
    if inspection.platform == "Qortal":
        skills.insert(0, "skills/qortal/legacy-dapp-audit-repair/SKILL.md")
    return {
        "source": (
            "auto-discovered on onboarding from well-known manifests; commands were "
            "not executed during onboarding"
        ),
        "commands": list(commands),
        "manual": list(manual),
        "docs": docs,
        "skills": skills,
    }


def _write_profile(profiles_path: Path, project_id: str, entry: dict) -> None:
    if profiles_path.is_file():
        try:
            data = json.loads(profiles_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise OnboardError(
                "the central acceptance profile file is not valid JSON"
            ) from exc
        if not isinstance(data, dict):
            raise OnboardError("the central acceptance profile file must be an object")
    else:
        data = {"version": 1, "profiles": {}}
    profiles = data.get("profiles")
    if not isinstance(profiles, dict):
        raise OnboardError("the central acceptance profile file has no profiles object")
    if project_id in profiles:
        return
    profiles[project_id] = entry
    from datetime import datetime, timezone

    data["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    _atomic_write(profiles_path, json.dumps(data, indent=2) + "\n")


def _branch_and_head(path: Path) -> tuple[str, str]:
    branch = _git(path, "rev-parse", "--abbrev-ref", "HEAD")
    head = _git(path, "rev-parse", "HEAD")
    return (
        (branch.stdout or "").strip(),
        (head.stdout or "").strip(),
    )


def onboard(
    *,
    url: str,
    registry_path: str | Path,
    projects_root: str | Path = PROJECTS_ROOT,
    docs_root: str | Path = DOCS_ROOT,
    state_root: str | Path | None = None,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    apply: bool = True,
) -> OnboardedProject:
    """Validate, clone (if needed), inspect and register one GitHub project."""

    identity = parse_github_identity(url)
    registry = Path(registry_path).expanduser().resolve()
    root = Path(projects_root).expanduser().resolve()
    target = root / identity.name
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise OnboardError("the repository name escapes the projects root") from exc

    with _state_lock(state_root, "registry"):
        if not registry.is_file():
            raise OnboardError("PROJECT-REGISTRY.md is missing")
        text = registry.read_text(encoding="utf-8")
        existing = _existing_registration(text, target, identity.repository)
        if existing is not None:
            project_id, platform = existing
            _indexes, rows = _registry_rows(text)
            row = next(
                (cells for cells in rows if cells and cells[0].strip("` ") == project_id),
                [],
            )
            repo_cell = row[2].strip("` ") if len(row) > 2 else str(target)
            repo_path = Path(repo_cell).expanduser()
            if not repo_path.is_dir():
                raise OnboardError(
                    f"{identity.repository} is already registered as {project_id}, "
                    "but its checkout is missing; repair the registration manually"
                )
            inspection = inspect_project(repo_path)
            branch, head = _branch_and_head(repo_path)
            commands, manual = discover_commands(repo_path)
            return OnboardedProject(
                project_id=project_id,
                platform=platform or inspection.platform,
                repo_path=repo_path,
                repo_url=identity.url,
                github_repository=identity.repository,
                cloned=False,
                reused_registration=True,
                inspection=inspection,
                commands=commands,
                manual=manual,
                profile_source="existing registration",
                central_root=Path(row[5].strip("` ")) if len(row) > 5 else None,
                branch=branch,
                head=head,
                notes=("already registered; no duplicate row was added",),
            )

        cloned = False
        if target.exists():
            if not (target / ".git").exists():
                raise OnboardError(
                    f"target path already exists and is not a Git checkout: {target}; "
                    "no files were overwritten"
                )
            origin = _git(target, "config", "--get", "remote.origin.url")
            actual = project_policy.normalise_remote_url((origin.stdout or "").strip())
            if actual != identity.repository:
                raise OnboardError(
                    f"target path already exists for {actual or 'another repository'}; "
                    f"it will not be overwritten for {identity.repository}"
                )
        else:
            if not apply:
                inspection = ProjectInspection(platform="Generic")
                return OnboardedProject(
                    project_id=_project_id(inspection.platform, identity.name),
                    platform=inspection.platform,
                    repo_path=target,
                    repo_url=identity.url,
                    github_repository=identity.repository,
                    cloned=False,
                    reused_registration=False,
                    inspection=inspection,
                    notes=("dry run: the checkout would be cloned",),
                )
            _clone(identity.url, target, timeout=max(30, int(timeout_seconds)))
            cloned = True

        origin_check = _git(target, "config", "--get", "remote.origin.url")
        actual = project_policy.normalise_remote_url((origin_check.stdout or "").strip())
        if actual != identity.repository:
            raise OnboardError("the cloned remote does not match the requested GitHub repository")

        inspection = inspect_project(target)
        branch, head = _branch_and_head(target)
        if not head:
            raise OnboardError("the cloned repository has no commit to start from")

        project_id = _project_id(inspection.platform, identity.name)
        _indexes, rows = _registry_rows(text)
        used_ids = {cells[0].strip("` ") for cells in rows if cells}
        candidate = project_id
        counter = 2
        while candidate in used_ids:
            candidate = f"{project_id}-{counter}"
            counter += 1
        project_id = candidate

        central_root = Path(docs_root).expanduser().resolve() / identity.name
        if apply:
            central_root.mkdir(parents=True, exist_ok=True)

        commands, manual = discover_commands(target)
        profiles_path = registry.parent / CENTRAL_PROFILE
        if apply:
            try:
                _write_profile(
                    profiles_path,
                    project_id,
                    _profile_entry(inspection, commands, manual, identity.repository),
                )
                _append_registry_row(
                    registry,
                    project_id=project_id,
                    platform=inspection.platform,
                    repo_path=target,
                    has_agents=inspection.has_agents,
                    central_root=central_root,
                    github_repository=identity.repository,
                )
            except OSError as exc:
                raise OnboardError(
                    "the checkout was cloned but registration could not be written "
                    f"atomically ({exc.__class__.__name__}); repair the registry and "
                    "retry, no partial row is intended"
                ) from exc
        return OnboardedProject(
            project_id=project_id,
            platform=inspection.platform,
            repo_path=target,
            repo_url=identity.url,
            github_repository=identity.repository,
            cloned=cloned,
            reused_registration=False,
            inspection=inspection,
            commands=commands,
            manual=manual,
            profile_source=f"auto-discovered central profile ({profiles_path.name})",
            central_root=central_root,
            branch=branch,
            head=head,
        )
