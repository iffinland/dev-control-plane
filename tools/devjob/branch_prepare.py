"""Safe automatic development-branch preparation for Workflow v3 jobs.

A new job must not start on ``main``/``master``/``trunk`` or on any other branch
that the project delivery policy does not authorize. Before OpenCode receives
the task, the startup path inspects the real checkout, verifies the configured
GitHub remote non-interactively, and either:

* keeps the current branch when it already matches the project's ``agent/*``
  policy (the clean-development-branch path used by existing jobs);
* creates one deterministic job-scoped branch under ``agent/`` from the current
  commit when the checkout is protected or otherwise unauthorized.

It never resets, cleans, stashes, force-checks-out, rewrites history or silently
moves unrelated work. Ambiguity fails closed with an actionable message and no
branch mutation. Resume/restart returns to the branch recorded by the job when
that is safe. A repository-scoped file lock serializes CLI and Telegram
startups, because both surfaces go through the same ``dev start`` path.
"""

from __future__ import annotations

import fcntl
import hashlib
import os
import re
import subprocess
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from . import contract, project_policy, store

DEFAULT_LOCK_TIMEOUT = 10.0
REMOTE_TIMEOUT_SECONDS = 60
TARGET_BRANCH_LIMIT = 200
SAFE_BRANCH_PART_RE = re.compile(r"[^A-Za-z0-9._-]+")


class BranchPreparationError(ValueError):
    """A safe development branch could not be prepared."""


@dataclass(frozen=True)
class RepoState:
    branch: str | None
    head: str
    detached: bool
    dirty_paths: tuple[str, ...]
    worktree_branches: tuple[tuple[Path, str], ...]


@dataclass(frozen=True)
class RemoteState:
    remote: str
    remote_url: str
    github_repository: str
    heads: dict[str, str]


@dataclass(frozen=True)
class PreparedBranch:
    branch: str
    base_sha: str
    original_branch: str | None
    created: bool
    switched: bool
    reused: bool
    remote: str
    remote_sha: str | None
    apply: bool = True

    def snapshot(self) -> dict:
        return {
            "branch": self.branch,
            "base_sha": self.base_sha,
            "original_branch": self.original_branch,
            "created": self.created,
            "switched": self.switched,
            "reused": self.reused,
            "remote": self.remote,
            "remote_sha": self.remote_sha,
            "apply": self.apply,
        }


def _git_env(repo: Path, remote_url: str) -> dict[str, str]:
    env = os.environ.copy()
    # Never prompt on a terminal or GUI. Existing credential helpers, SSH agent
    # keys and host-key verification remain in use; no remote URL is changed.
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GCM_INTERACTIVE"] = "Never"
    if remote_url.startswith("ssh://") or re.match(r"^[^/@]+@[^/:]+:", remote_url):
        ssh_command = env.get("GIT_SSH_COMMAND")
        if not ssh_command:
            configured = _git_text(repo, "config", "--get", "core.sshCommand")
            if not configured:
                env["GIT_SSH_COMMAND"] = "ssh -oBatchMode=yes"
    return env


def _git(
    repo: Path,
    *args: str,
    env: dict[str, str] | None = None,
    timeout: int = 20,
) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(["git", *args], 1, "", str(exc))


def _git_text(repo: Path, *args: str) -> str:
    result = _git(repo, *args)
    if result.returncode != 0:
        return ""
    return (result.stdout or "").strip()


def _dirty_paths(repo: Path) -> tuple[str, ...]:
    result = _git(repo, "status", "--porcelain=v1", "-z", "--no-renames")
    if result.returncode != 0:
        return ()
    return tuple(contract.parse_dirty_paths(result.stdout or ""))


def _worktree_branches(repo: Path) -> tuple[tuple[Path, str], ...]:
    result = _git(repo, "worktree", "list", "--porcelain")
    if result.returncode != 0:
        return ()
    entries: list[tuple[Path, str]] = []
    path: Path | None = None
    for line in (result.stdout or "").splitlines():
        if line.startswith("worktree "):
            path = Path(line[len("worktree ") :])
        elif line.startswith("branch ") and path is not None:
            branch = line[len("branch ") :].strip()
            if branch.startswith("refs/heads/"):
                branch = branch[len("refs/heads/") :]
            entries.append((path, branch))
            path = None
    return tuple(entries)


def inspect(repo: str | Path) -> RepoState:
    path = Path(repo).expanduser().resolve()
    if _git(path, "rev-parse", "--git-dir").returncode != 0:
        raise BranchPreparationError(f"repository is not a Git checkout: {path}")
    head = _git_text(path, "rev-parse", "HEAD")
    if not head:
        raise BranchPreparationError("repository has no commit to start from")
    branch = _git_text(path, "rev-parse", "--abbrev-ref", "HEAD")
    detached = not branch or branch == "HEAD"
    return RepoState(
        branch=None if detached else branch,
        head=head,
        detached=detached,
        dirty_paths=_dirty_paths(path),
        worktree_branches=_worktree_branches(path),
    )


def branch_name(project_id: str, job_id: str) -> str:
    """Return a deterministic job-scoped branch under ``agent/``."""

    project = SAFE_BRANCH_PART_RE.sub("-", str(project_id or "project")).strip("-.") or "project"
    job = SAFE_BRANCH_PART_RE.sub("-", str(job_id or "job")).strip("-.") or "job"
    if len(project) > 80:
        project = project[:80].rstrip("-.")
    name = f"agent/{project}/{job}"
    if len(name) > TARGET_BRANCH_LIMIT:
        digest = hashlib.sha256(name.encode("utf-8")).hexdigest()[:12]
        name = f"agent/{project[:60].rstrip('-')}/{digest}"
    return name


def _valid_new_branch_name(repo: Path, name: str) -> None:
    result = _git(repo, "check-ref-format", "--branch", name)
    if result.returncode != 0:
        raise BranchPreparationError(f"invalid development branch name: {name!r}")


def _branch_exists(repo: Path, name: str) -> bool:
    return _git(repo, "show-ref", "--verify", "--quiet", f"refs/heads/{name}").returncode == 0


def _checked_out_elsewhere(repo: Path, state: RepoState, name: str) -> Path | None:
    current = repo.resolve()
    for worktree, branch in state.worktree_branches:
        if branch != name:
            continue
        try:
            resolved = worktree.expanduser().resolve()
        except OSError:
            resolved = worktree.expanduser().absolute()
        if resolved != current:
            return resolved
    return None


def _object_exists(repo: Path, sha: str) -> bool:
    return _git(repo, "cat-file", "-e", f"{sha}^{{commit}}").returncode == 0


def _is_ancestor(repo: Path, older: str, newer: str) -> bool:
    return _git(repo, "merge-base", "--is-ancestor", older, newer).returncode == 0


def _synchronization_problem(
    repo: Path,
    state: RepoState,
    remote: RemoteState,
) -> str | None:
    """Reject an ambiguous branch source with local-only history.

    Creating a job branch from a commit is only safe when that commit is already
    published (or is an ancestor of the published branch tip). Otherwise the new
    branch would silently absorb unknown local work, including a historical
    commit such as the wordpress-to-qortal ``main`` commit.
    """

    if not state.branch:
        return "detached HEAD has no branch to derive a development branch from"
    remote_sha = remote.heads.get(state.branch)
    if not remote_sha:
        return (
            f"current branch {state.branch!r} has no matching branch on remote "
            f"{remote.remote!r}; cannot prove local commits are already published"
        )
    if remote_sha == state.head:
        return None
    if not _object_exists(repo, remote_sha):
        return (
            f"current branch {state.branch!r} differs from remote "
            f"{remote.remote}/{state.branch} and the remote commit is not available "
            "locally; fetch and synchronize the branch before starting a job"
        )
    if _is_ancestor(repo, state.head, remote_sha):
        # The local checkout is behind but contains no unpublished commits.
        return None
    if _is_ancestor(repo, remote_sha, state.head):
        count = _git_text(repo, "rev-list", "--count", f"{remote_sha}..HEAD")
        return (
            f"current branch {state.branch!r} has {count or 'one or more'} unpushed "
            f"commit(s) relative to {remote.remote}/{state.branch}; push them or "
            "start from a synchronized commit before creating a job branch"
        )
    return (
        f"current branch {state.branch!r} has diverged from "
        f"{remote.remote}/{state.branch}; reconcile it before starting a job"
    )


def probe_remote(repo: Path, policy: project_policy.DeliveryPolicy) -> RemoteState:
    """Verify remote identity and non-interactive access before any branch move."""

    if not policy.valid:
        raise BranchPreparationError(
            f"project {policy.project_id} has no valid delivery policy: {policy.error}"
        )
    remote = str(policy.remote or "")
    if not remote:
        raise BranchPreparationError("the project delivery policy has no Git remote")
    expected = project_policy.normalise_github_repository(policy.github_repository)
    if expected is None:
        raise BranchPreparationError(
            "the project delivery policy has no valid GitHub repository"
        )
    url = _git_text(repo, "config", "--get", f"remote.{remote}.url")
    if not url:
        raise BranchPreparationError(f"git remote {remote!r} is not configured")
    actual = project_policy.normalise_remote_url(url)
    if actual is None:
        raise BranchPreparationError(
            f"remote {remote!r} does not point at a GitHub repository"
        )
    if actual != expected:
        raise BranchPreparationError(
            f"remote {remote!r} points at {actual}, expected {expected}; "
            "the project remote was not changed"
        )

    env = _git_env(repo, url)
    result = _git(
        repo,
        "ls-remote",
        "--heads",
        remote,
        env=env,
        timeout=REMOTE_TIMEOUT_SECONDS,
    )
    if result.returncode != 0:
        # Never echo the raw URL or Git stderr: both can contain credentials.
        raise BranchPreparationError(
            "GitHub delivery is unavailable: non-interactive authentication or "
            f"transport for remote {remote!r} failed. Configure valid HTTPS "
            "credentials or an existing SSH key/agent, then retry. The job was "
            "not started and no branch was changed."
        )
    heads: dict[str, str] = {}
    for line in (result.stdout or "").splitlines():
        fields = line.split()
        if len(fields) >= 2 and fields[1].startswith("refs/heads/"):
            heads[fields[1][len("refs/heads/") :]] = fields[0]
    return RemoteState(
        remote=remote,
        remote_url=url,
        github_repository=expected,
        heads=heads,
    )


def policy_from_contract(
    snapshot: object,
    repo: str | Path,
) -> project_policy.DeliveryPolicy:
    """Reconstruct the job's recorded delivery policy for resume/restart."""

    if not isinstance(snapshot, dict):
        raise BranchPreparationError(
            "the job has no recorded delivery policy; refusing to guess a branch"
        )
    project_id = str(snapshot.get("project_id") or "unknown")
    remote = str(snapshot.get("remote") or "")
    repository = project_policy.normalise_github_repository(
        snapshot.get("github_repository")
    )
    pattern = str(snapshot.get("branch_pattern") or "")
    automatic_push = bool(snapshot.get("automatic_push"))
    errors: list[str] = []
    if not remote:
        errors.append("missing remote")
    if repository is None:
        errors.append("invalid GitHub repository")
    if not project_policy.BRANCH_PATTERN_RE.match(pattern):
        errors.append("invalid agent/* branch pattern")
    if errors:
        raise BranchPreparationError(
            f"recorded delivery policy for {project_id} is invalid: "
            + ", ".join(errors)
        )
    return project_policy.DeliveryPolicy(
        project_id=project_id,
        repo_path=Path(repo).expanduser(),
        remote=remote,
        github_repository=repository,
        branch_pattern=pattern,
        automatic_push=automatic_push,
        remote_url=str(snapshot.get("remote_url") or "") or None,
        valid=True,
    )


def _active_job(repo: Path, exclude_job_id: str | None) -> dict | None:
    target = repo.resolve()
    for job in store.list_jobs():
        if str(job.get("state")) != "RUNNING":
            continue
        if exclude_job_id and str(job.get("id")) == exclude_job_id:
            continue
        try:
            job_repo = Path(str(job.get("repo") or "")).expanduser().resolve()
        except OSError:
            continue
        if job_repo != target:
            continue
        if store.worker_is_alive(job):
            return job
    return None


def _repo_key(repo: Path) -> str:
    try:
        text = str(repo.resolve())
    except OSError:
        text = str(repo.absolute())
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]


@contextmanager
def repo_lock(
    repo: str | Path,
    *,
    state_root: str | Path | None = None,
    timeout: float = DEFAULT_LOCK_TIMEOUT,
) -> Iterator[None]:
    """Serialize branch preparation and job admission for one repository."""

    path = Path(repo).expanduser()
    root = store.state_root(state_root)
    directory = store.ensure_private_dir(root / "locks")
    lock_path = directory / f"repo-{_repo_key(path)}.lock"
    handle = lock_path.open("a+", encoding="utf-8")
    try:
        try:
            os.chmod(lock_path, 0o600)
        except OSError:
            pass
        deadline = time.monotonic() + max(0.1, float(timeout))
        while True:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError as exc:
                if time.monotonic() >= deadline:
                    raise BranchPreparationError(
                        "another Workflow v3 startup is already preparing this "
                        "repository; no branch was changed"
                    ) from exc
                time.sleep(0.05)
        yield
    finally:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def prepare(
    repo: str | Path,
    policy: project_policy.DeliveryPolicy,
    *,
    job_id: str,
    requested_branch: str | None = None,
    existing_branch: str | None = None,
    resume: bool = False,
    exclude_job_id: str | None = None,
    allow_protected_branch: bool = False,
    apply: bool = True,
    lock: bool = True,
    lock_timeout: float = DEFAULT_LOCK_TIMEOUT,
    state_root: str | Path | None = None,
) -> PreparedBranch:
    """Return the branch a job must use, creating/switching only when safe."""

    path = Path(repo).expanduser().resolve()
    if lock:
        with repo_lock(path, state_root=state_root, timeout=lock_timeout):
            return _prepare_locked(
                path,
                policy,
                job_id=job_id,
                requested_branch=requested_branch,
                existing_branch=existing_branch,
                resume=resume,
                exclude_job_id=exclude_job_id,
                allow_protected_branch=allow_protected_branch,
                apply=apply,
            )
    return _prepare_locked(
        path,
        policy,
        job_id=job_id,
        requested_branch=requested_branch,
        existing_branch=existing_branch,
        resume=resume,
        exclude_job_id=exclude_job_id,
        allow_protected_branch=allow_protected_branch,
        apply=apply,
    )


def _prepare_locked(
    repo: Path,
    policy: project_policy.DeliveryPolicy,
    *,
    job_id: str,
    requested_branch: str | None,
    existing_branch: str | None,
    resume: bool,
    exclude_job_id: str | None,
    allow_protected_branch: bool,
    apply: bool,
) -> PreparedBranch:
    state = inspect(repo)
    other = _active_job(repo, exclude_job_id)
    if other is not None:
        raise BranchPreparationError(
            f"another active job is already using this repository: "
            f"{other.get('title') or other.get('id')} ({other.get('id')}); "
            "wait for it to finish or use the existing job instead"
        )
    remote = probe_remote(repo, policy)

    if resume:
        target = (existing_branch or "").strip()
        if not target:
            raise BranchPreparationError(
                "the job has no recorded development branch; refusing to guess one"
            )
        if target in project_policy.PROTECTED_BRANCHES:
            raise BranchPreparationError(
                f"recorded branch {target!r} is protected and cannot be resumed automatically"
            )
        if state.branch == target:
            # Resuming on the recorded branch is unambiguous; preserve any
            # unfinished working-tree work exactly where it is.
            return PreparedBranch(
                branch=target,
                base_sha=state.head,
                original_branch=state.branch,
                created=False,
                switched=False,
                reused=True,
                remote=remote.remote,
                remote_sha=remote.heads.get(target),
                apply=apply,
            )
        if state.dirty_paths:
            raise BranchPreparationError(
                "the working tree has uncommitted changes, so it is ambiguous "
                f"whether they belong to {target!r}; commit or move them before resume"
            )
        if not _branch_exists(repo, target):
            raise BranchPreparationError(
                f"the job recorded branch {target!r}, but it no longer exists; "
                "restore it or start a new job from a synchronized branch"
            )
        other_worktree = _checked_out_elsewhere(repo, state, target)
        if other_worktree is not None:
            raise BranchPreparationError(
                f"recorded branch {target!r} is checked out in another worktree "
                f"({other_worktree}); resume it there or remove that worktree"
            )
        if apply:
            result = _git(repo, "switch", target)
            if result.returncode != 0:
                raise BranchPreparationError(
                    f"could not switch back to recorded branch {target!r} safely; "
                    "no force-checkout was attempted"
                )
        head = _git_text(repo, "rev-parse", "HEAD") or state.head
        return PreparedBranch(
            branch=target,
            base_sha=head,
            original_branch=state.branch,
            created=False,
            switched=True,
            reused=False,
            remote=remote.remote,
            remote_sha=remote.heads.get(target),
            apply=apply,
        )

    if allow_protected_branch and state.branch in project_policy.PROTECTED_BRANCHES:
        return PreparedBranch(
            branch=state.branch,
            base_sha=state.head,
            original_branch=state.branch,
            created=False,
            switched=False,
            reused=True,
            remote=remote.remote,
            remote_sha=remote.heads.get(state.branch),
            apply=apply,
        )

    if requested_branch:
        target = requested_branch.strip()
        if target in project_policy.PROTECTED_BRANCHES:
            raise BranchPreparationError(
                f"requested branch {target!r} is protected; automatic delivery "
                "requires an agent/* development branch"
            )
        if not policy.matches_branch(target):
            raise BranchPreparationError(
                f"requested branch {target!r} is outside the project development "
                f"pattern {policy.branch_pattern or '(none)'}"
            )
        _valid_new_branch_name(repo, target)
        if state.branch == target:
            return PreparedBranch(
                branch=target,
                base_sha=state.head,
                original_branch=state.branch,
                created=False,
                switched=False,
                reused=True,
                remote=remote.remote,
                remote_sha=remote.heads.get(target),
                apply=apply,
            )
        if _branch_exists(repo, target):
            raise BranchPreparationError(
                f"requested branch {target!r} already exists and is not the current "
                "checkout; refusing to reuse an unrelated development branch"
            )
    elif state.branch and policy.matches_branch(state.branch):
        # The checkout is already on a policy-approved development branch. Keep
        # it: this is the clean development-branch path and remains idempotent.
        return PreparedBranch(
            branch=state.branch,
            base_sha=state.head,
            original_branch=state.branch,
            created=False,
            switched=False,
            reused=True,
            remote=remote.remote,
            remote_sha=remote.heads.get(state.branch),
            apply=apply,
        )
    else:
        if state.detached or not state.branch:
            raise BranchPreparationError(
                "the checkout is on a detached HEAD; create or check out a named "
                "synchronized branch before starting a job"
            )
        target = branch_name(policy.project_id, job_id)
        _valid_new_branch_name(repo, target)
        if _branch_exists(repo, target):
            raise BranchPreparationError(
                f"job-scoped branch {target!r} already exists but is not the current "
                "checkout; refusing to reuse unrelated work"
            )

    if state.detached or not state.branch:
        raise BranchPreparationError(
            "the checkout is on a detached HEAD; create or check out a named "
            "synchronized branch before starting a job"
        )
    if state.dirty_paths:
        preview = ", ".join(state.dirty_paths[:5])
        if len(state.dirty_paths) > 5:
            preview += ", ..."
        raise BranchPreparationError(
            "the working tree has uncommitted changes ("
            f"{preview}), so creating or switching development branches is "
            "ambiguous. Commit, move or clean up only your own changes before "
            "starting the job; nothing was reset, stashed or discarded."
        )
    problem = _synchronization_problem(repo, state, remote)
    if problem:
        raise BranchPreparationError(problem)
    if state.branch == target:
        # Defensive: the target was already the checked-out branch. Keep it only
        # if it matches policy, which was checked above.
        return PreparedBranch(
            branch=target,
            base_sha=state.head,
            original_branch=state.branch,
            created=False,
            switched=False,
            reused=True,
            remote=remote.remote,
            remote_sha=remote.heads.get(target),
            apply=apply,
        )
    if apply:
        result = _git(repo, "switch", "-c", target)
        if result.returncode != 0:
            raise BranchPreparationError(
                f"could not create development branch {target!r} safely; the "
                "checkout was left unchanged and no force operation was attempted"
            )
        branch = _git_text(repo, "rev-parse", "--abbrev-ref", "HEAD")
        if branch != target:
            raise BranchPreparationError(
                f"development branch {target!r} was not checked out after creation"
            )
    head = _git_text(repo, "rev-parse", "HEAD") or state.head
    return PreparedBranch(
        branch=target,
        base_sha=head,
        original_branch=state.branch,
        created=True,
        switched=True,
        reused=False,
        remote=remote.remote,
        remote_sha=remote.heads.get(target),
        apply=apply,
    )
