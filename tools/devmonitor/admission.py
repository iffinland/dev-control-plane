"""Per-project admission and global execution-guard awareness.

Two serialization layers are deliberately separate:

* the existing Workflow v3 execution guard allows one heavyweight OpenCode run
  across all projects;
* the monitor allows one active monitor-managed job per registered project.

The project lock is held only for the check-and-invoke critical section. The
durable source of truth is the existing job store scan; the file lock prevents
two near-simultaneous Telegram handlers from racing. The global guard remains
authoritative.
"""

from __future__ import annotations

import errno
import fcntl
import hashlib
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable, Iterator

from devjob import store

from .projects import Registry, RegistryError, ValidatedProject
from .timings import TimingRecorder, default_recorder


class AdmissionError(RuntimeError):
    """A job cannot be admitted safely."""


class ProjectBusy(AdmissionError):
    def __init__(self, job: dict) -> None:
        self.job = job
        super().__init__(
            f"project already has an active job: {job.get('title') or job.get('id')}"
        )


class GlobalGuardBusy(AdmissionError):
    def __init__(self, job: dict | None = None) -> None:
        self.job = job
        if job:
            super().__init__(
                "the global execution guard is busy with "
                f"{job.get('title') or job.get('id')}"
            )
        else:
            super().__init__("the global execution guard lock is currently held")


class AdmissionLockTimeout(AdmissionError):
    """Another handler held the same project admission lock too long."""


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class AdmissionManager:
    def __init__(
        self,
        state_dir: str | Path,
        jobs,
        registry: Registry,
        *,
        lock_timeout: float = 5.0,
        sleep=time.sleep,
        clock=time.monotonic,
        timings: TimingRecorder | None = None,
    ) -> None:
        self.state_dir = Path(state_dir).expanduser()
        self.jobs = jobs
        self.registry = registry
        self.lock_timeout = max(0.1, float(lock_timeout))
        self.sleep = sleep
        self.clock = clock
        self.timings = timings or default_recorder()

    # ---- project keys ------------------------------------------------------------
    def projects(self) -> list[ValidatedProject]:
        try:
            return list(self.registry.load())
        except RegistryError:
            return []

    def project_key_for_repo(self, repo: str | Path, projects: Iterable[ValidatedProject] | None = None) -> str:
        candidate = Path(repo).expanduser()
        try:
            repo_real = candidate.resolve(strict=True)
        except OSError:
            repo_real = candidate.resolve()
        for project in projects if projects is not None else self.projects():
            if project.repo_real is not None and project.repo_real == repo_real:
                return project.project_id
        return "repo:" + _sha256(str(repo_real))

    def project_key_for_job(self, job: dict, projects: Iterable[ValidatedProject] | None = None) -> str:
        # A job records the project it was admitted for. That survives an
        # isolated linked worktree, whose path intentionally differs from the
        # registered owner checkout.
        recorded = str(job.get("project_id") or "")
        if recorded:
            for project in projects if projects is not None else self.projects():
                if project.project_id == recorded:
                    return recorded
        return self.project_key_for_repo(job.get("repo") or "", projects)

    # ---- active job and guard scan ----------------------------------------------
    def active_jobs(self) -> list[dict]:
        active: list[dict] = []
        for job in self.jobs.list_jobs():
            if str(job.get("state")) != "RUNNING":
                continue
            if job.get("worker_alive") is True:
                active.append(job)
        return active

    @property
    def guard_lock_path(self) -> Path:
        return Path(self.jobs.state_root) / "guard.lock"

    def guard_lock_held(self) -> bool:
        """Read-only check of the existing execution guard lock."""

        path = self.guard_lock_path
        if not path.exists():
            return False
        try:
            fd = os.open(path, os.O_RDONLY)
        except OSError:
            # Cannot prove it is free; fail closed for mutation admission.
            return True
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as exc:
                if exc.errno in {errno.EACCES, errno.EAGAIN}:
                    return True
                return True
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            except OSError:
                pass
            return False
        finally:
            os.close(fd)

    def check_project(
        self,
        key: str,
        *,
        exclude_job_id: str | None = None,
        enforce_global: bool = True,
    ) -> None:
        projects = self.projects()
        active = self.active_jobs()
        for job in active:
            if exclude_job_id and str(job.get("id")) == exclude_job_id:
                continue
            if self.project_key_for_job(job, projects) == key:
                raise ProjectBusy(job)
        if enforce_global:
            for job in active:
                if exclude_job_id and str(job.get("id")) == exclude_job_id:
                    continue
                raise GlobalGuardBusy(job)
            if self.guard_lock_held():
                raise GlobalGuardBusy(None)

    # ---- project file lock -------------------------------------------------------
    def lock_path(self, key: str) -> Path:
        directory = self.state_dir / "locks"
        directory.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(directory, 0o700)
        except OSError:
            pass
        return directory / f"project-{_sha256(key)[:32]}.lock"

    @contextmanager
    def reserve(self, key: str) -> Iterator[None]:
        path = self.lock_path(key)
        handle = path.open("a+", encoding="utf-8")
        try:
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
            deadline = self.clock() + self.lock_timeout
            while True:
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError as exc:
                    if self.clock() >= deadline:
                        raise AdmissionLockTimeout(
                            "the project admission lock is held by another action"
                        ) from exc
                    self.sleep(0.05)
            with self.timings.measure("admission:check_and_invoke"):
                yield
        finally:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            finally:
                handle.close()
