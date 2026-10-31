"""Facade over the existing Workflow v3 CLI and job store.

``dev status --json`` and ``dev report --json`` remain the authoritative read
surfaces. Logs, reports, job records and event cursors are derived from the
validated job directory and named artifacts, never from arbitrary absolute paths
in ``job.json``. P2 adds only the fixed-shape ``dev start`` and ``dev resume``
subprocess calls; cancellation and manual acceptance remain absent.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Sequence

from devjob import store

from .redact import redact_text, sanitize_control
from .timings import TimingRecorder, default_recorder

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DEV = PACKAGE_ROOT / "dev.py"
MAX_LOG_BYTES = 64 * 1024
MAX_LOG_LINES = 100
MAX_REPORT_BYTES = 256 * 1024
MAX_JOB_RECORD_BYTES = 2 * 1024 * 1024
MAX_EVENT_BYTES = 256 * 1024
JOB_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,200}$")


class JobError(RuntimeError):
    """A Workflow v3 read failed or returned unusable output."""


@dataclass(frozen=True)
class LogText:
    job_id: str
    kind: str
    text: str
    bytes_read: int
    truncated: bool


@dataclass(frozen=True)
class ReportText:
    job_id: str
    text: str
    bytes_read: int
    truncated: bool


@dataclass(frozen=True)
class EventBatch:
    job_id: str
    inode: int
    offset: int
    last_event_hash: str
    events: tuple[dict, ...] = field(default_factory=tuple)
    reset: bool = False
    skipped_existing: bool = False


def validate_job_id(job_id: str) -> str:
    if not isinstance(job_id, str) or not JOB_ID_RE.match(job_id) or job_id in {".", ".."}:
        raise JobError("invalid job id")
    return job_id


class JobFacade:
    def __init__(
        self,
        state_root: str | Path | None = None,
        *,
        dev_script: str | Path | None = None,
        python: str | None = None,
        timeout_seconds: float = 30.0,
        mutation_timeout_seconds: float = 120.0,
        env: Mapping[str, str] | None = None,
        timings: TimingRecorder | None = None,
    ) -> None:
        self.state_root = Path(state_root).expanduser() if state_root else store.state_root()
        self.dev_script = Path(dev_script).expanduser() if dev_script else DEFAULT_DEV
        self.python = python or sys.executable
        self.timeout_seconds = timeout_seconds
        self.mutation_timeout_seconds = max(timeout_seconds, mutation_timeout_seconds)
        self.environ = dict(os.environ if env is None else env)
        self.environ["DEV_CONTROL_PLANE_STATE"] = str(self.state_root)
        self.timings = timings or default_recorder()

    # ---- subprocess boundary -----------------------------------------------------
    def _run(
        self,
        args: list[str],
        *,
        input_text: str | None = None,
        allow_nonzero: bool = False,
        timeout_seconds: float | None = None,
    ) -> subprocess.CompletedProcess[str]:
        command = [self.python, str(self.dev_script)] + args
        label = f"cli:dev_{args[0] if args else 'unknown'}"
        with self.timings.measure(label):
            try:
                completed = subprocess.run(
                    command,
                    input=input_text,
                    text=True,
                    capture_output=True,
                    timeout=timeout_seconds or self.timeout_seconds,
                    check=False,
                    shell=False,
                    env=self.environ,
                )
            except subprocess.TimeoutExpired as exc:
                raise JobError("Workflow v3 CLI timed out") from exc
            except OSError as exc:
                raise JobError(f"Workflow v3 CLI could not start: {exc.__class__.__name__}") from exc
            if completed.returncode != 0 and not allow_nonzero:
                detail = (completed.stderr or completed.stdout or "").strip()
                detail = redact_text(detail, limit=500)
                raise JobError(detail or f"Workflow v3 CLI exited {completed.returncode}")
            return completed

    def _json(self, args: list[str]) -> object:
        output = self._run(args).stdout
        try:
            return json.loads(output)
        except json.JSONDecodeError as exc:
            raise JobError("Workflow v3 CLI returned invalid JSON") from exc

    def _json_result(self, args: list[str], *, input_text: str | None = None) -> dict:
        completed = self._run(
            args,
            input_text=input_text,
            allow_nonzero=True,
            timeout_seconds=self.mutation_timeout_seconds,
        )
        payload: object = None
        if completed.stdout.strip():
            try:
                payload = json.loads(completed.stdout)
            except json.JSONDecodeError:
                payload = None
        if completed.returncode != 0 and payload is None:
            detail = (completed.stderr or completed.stdout or "").strip()
            raise JobError(redact_text(detail, limit=500) or f"Workflow v3 CLI exited {completed.returncode}")
        if not isinstance(payload, dict) or not payload.get("id"):
            raise JobError("Workflow v3 CLI returned an unexpected job payload")
        return payload

    # ---- read surfaces -----------------------------------------------------------
    def list_jobs(self) -> list[dict]:
        payload = self._json(["status", "--all", "--json"])
        if isinstance(payload, dict):
            payload = [payload]
        if not isinstance(payload, list):
            raise JobError("Workflow v3 status returned an unexpected shape")
        jobs = [item for item in payload if isinstance(item, dict) and item.get("id")]
        jobs.sort(key=_job_sort_key)
        return jobs

    def job_status(self, job_id: str) -> dict:
        job_id = validate_job_id(job_id)
        payload = self._json(["status", job_id, "--json"])
        if not isinstance(payload, dict) or payload.get("id") != job_id:
            raise JobError("Workflow v3 status returned an unexpected job")
        return payload

    def job_dir(self, job_id: str) -> Path:
        job_id = validate_job_id(job_id)
        try:
            path = store.job_dir(job_id, self.state_root)
        except store.StoreError as exc:
            raise JobError(str(exc)) from exc
        if not path.is_dir():
            raise JobError("job directory is not available")
        return path

    def job_log(
        self,
        job_id: str,
        kind: str = "run",
        *,
        secrets: tuple[str, ...] | list[str] = (),
        max_bytes: int = MAX_LOG_BYTES,
        max_lines: int = MAX_LOG_LINES,
    ) -> LogText:
        if kind not in {"run", "worker"}:
            raise JobError("log kind must be run or worker")
        directory = self.job_dir(job_id)
        filename = "run.log" if kind == "run" else "worker.log"
        path = directory / filename
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        except FileNotFoundError as exc:
            raise JobError(f"{filename} does not exist yet") from exc
        except OSError as exc:
            raise JobError(f"{filename} is not readable: {exc.__class__.__name__}") from exc
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode):
                raise JobError(f"{filename} is not a regular file")
            size = int(info.st_size)
            offset = max(0, size - int(max_bytes))
            os.lseek(fd, offset, os.SEEK_SET)
            chunks: list[bytes] = []
            remaining = min(size, int(max_bytes))
            while remaining > 0:
                chunk = os.read(fd, min(65536, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            data = b"".join(chunks)
        finally:
            os.close(fd)
        text = data.decode("utf-8", "replace")
        lines = text.splitlines()
        if len(lines) > max_lines:
            lines = lines[-max_lines:]
            truncated = True
        else:
            truncated = offset > 0
        cleaned = sanitize_control("\n".join(lines))
        return LogText(
            job_id=job_id,
            kind=kind,
            text=redact_text(cleaned, secrets, None),
            bytes_read=len(data),
            truncated=truncated,
        )

    def job_report(
        self,
        job_id: str,
        *,
        secrets: tuple[str, ...] | list[str] = (),
        max_bytes: int = MAX_REPORT_BYTES,
    ) -> ReportText:
        directory = self.job_dir(job_id)
        path = directory / "report.md"
        if not path.is_file():
            # The documented Workflow v3 report surface writes report.md.
            self._json(["report", job_id, "--json"])
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        except FileNotFoundError as exc:
            raise JobError("report.md is not available") from exc
        except OSError as exc:
            raise JobError(f"report.md is not readable: {exc.__class__.__name__}") from exc
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode):
                raise JobError("report.md is not a regular file")
            size = int(info.st_size)
            read_size = min(size, int(max_bytes))
            chunks: list[bytes] = []
            remaining = read_size
            while remaining > 0:
                chunk = os.read(fd, min(65536, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            data = b"".join(chunks)
        finally:
            os.close(fd)
        text = data.decode("utf-8", "replace")
        return ReportText(
            job_id=job_id,
            text=redact_text(text, secrets, None),
            bytes_read=len(data),
            truncated=size > int(max_bytes),
        )

    def job_record(self, job_id: str) -> dict:
        """Read the durable job record for fields not exposed by ``status``.

        The path is derived from the validated job directory, opened with
        ``O_NOFOLLOW`` and bounded in size. It is never trusted from ``job.json``.
        """

        directory = self.job_dir(job_id)
        path = directory / "job.json"
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        except FileNotFoundError as exc:
            raise JobError("job record is not available") from exc
        except OSError as exc:
            raise JobError(f"job record is not readable: {exc.__class__.__name__}") from exc
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode):
                raise JobError("job record is not a regular file")
            if int(info.st_size) > MAX_JOB_RECORD_BYTES:
                raise JobError("job record is larger than the configured limit")
            data = os.read(fd, MAX_JOB_RECORD_BYTES + 1)
        finally:
            os.close(fd)
        try:
            payload = json.loads(data.decode("utf-8", "replace"))
        except json.JSONDecodeError as exc:
            raise JobError("job record is not valid JSON") from exc
        if not isinstance(payload, dict) or payload.get("id") != job_id:
            raise JobError("job record does not match the requested job")
        return payload

    def job_events(
        self,
        job_id: str,
        *,
        inode: int = 0,
        offset: int = 0,
        start_at_end: bool = False,
        max_bytes: int = MAX_EVENT_BYTES,
    ) -> EventBatch:
        """Read new lifecycle events from the validated job directory.

        The caller persists ``(inode, offset, last_event_hash)``. A changed inode
        or a shrunk file resets the cursor. Only complete JSONL lines are consumed;
        a partially written trailing line is left for the next poll.
        """

        directory = self.job_dir(job_id)
        path = directory / "events.jsonl"
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        except FileNotFoundError:
            return EventBatch(job_id=job_id, inode=0, offset=0, last_event_hash="")
        except OSError as exc:
            raise JobError(f"events file is not readable: {exc.__class__.__name__}") from exc
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode):
                raise JobError("events file is not a regular file")
            size = int(info.st_size)
            if start_at_end and not inode and offset == 0:
                return EventBatch(
                    job_id=job_id,
                    inode=int(info.st_ino),
                    offset=size,
                    last_event_hash="",
                    skipped_existing=True,
                )
            reset = False
            if inode != int(info.st_ino) or size < int(offset):
                offset = 0
                reset = True
            offset = max(0, int(offset))
            read_start = offset
            if size - read_start > int(max_bytes):
                read_start = size - int(max_bytes)
                reset = True
            os.lseek(fd, read_start, os.SEEK_SET)
            remaining = size - read_start
            chunks: list[bytes] = []
            while remaining > 0:
                chunk = os.read(fd, min(65536, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            data = b"".join(chunks)
        finally:
            os.close(fd)

        end = data.rfind(b"\n")
        if end < 0:
            # No complete line yet. Keep the cursor at the original position.
            return EventBatch(
                job_id=job_id,
                inode=int(info.st_ino),
                offset=offset,
                last_event_hash="",
                reset=reset,
            )
        consumed = data[: end + 1]
        events: list[dict] = []
        last_hash = ""
        for raw in consumed.splitlines():
            if not raw.strip():
                continue
            last_hash = hashlib.sha1(raw).hexdigest()
            try:
                item = json.loads(raw.decode("utf-8", "replace"))
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                events.append(item)
        return EventBatch(
            job_id=job_id,
            inode=int(info.st_ino),
            offset=read_start + len(consumed),
            last_event_hash=last_hash,
            events=tuple(events),
            reset=reset,
        )

    # ---- mutating CLI surfaces (P2 control) --------------------------------------
    def start_job(
        self,
        *,
        repo: str | Path,
        title: str,
        prompt: str,
        command_criteria: Sequence[tuple[str, str]],
        manual_criteria: Sequence[str],
        timeout_seconds: int,
        agent: str,
        model: str,
        branch: str | None = None,
    ) -> dict:
        if not command_criteria and not manual_criteria:
            raise JobError("at least one acceptance criterion is required")
        if not prompt.strip():
            raise JobError("prompt is required")
        args = [
            "start",
            "--repo",
            str(repo),
            "--title",
            title,
            "--prompt-file",
            "-",
        ]
        if branch:
            args.extend(["--branch", branch])
        for label, command in command_criteria:
            args.extend(["--criterion", f"{label}::{command}"])
        for manual in manual_criteria:
            args.extend(["--manual-criterion", manual])
        args.extend(
            [
                "--timeout",
                f"{int(timeout_seconds)}s",
                "--agent",
                agent,
                "--model",
                model,
                "--no-notify",
                "--json",
            ]
        )
        return self._json_result(args, input_text=prompt)

    def resume_job(
        self,
        job_id: str,
        *,
        prompt: str | None = None,
        timeout_seconds: int | None = None,
        new_session: bool = False,
        force: bool = False,
    ) -> dict:
        job_id = validate_job_id(job_id)
        args = ["resume", job_id, "--json"]
        if timeout_seconds is not None:
            args.extend(["--timeout", f"{int(timeout_seconds)}s"])
        if prompt:
            args.extend(["--prompt", prompt])
        if new_session:
            args.append("--new-session")
        if force:
            args.append("--force")
        return self._json_result(args)


def _job_sort_key(job: dict) -> tuple[int, float, str]:
    state = str(job.get("state") or "")
    active = 0 if state == "RUNNING" else 1
    stamp = _timestamp(job.get("started_at") or job.get("attempt_started_at"))
    return (active, -stamp, str(job.get("id") or ""))


def _timestamp(value: object) -> float:
    from datetime import datetime, timezone

    if not isinstance(value, str) or not value:
        return 0.0
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        ).timestamp()
    except ValueError:
        return 0.0
