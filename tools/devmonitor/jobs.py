"""Read-only facade over the existing Workflow v3 CLI and job store.

Cluster Phase 1 uses ``dev status --json`` and ``dev report --json`` as the
authoritative surfaces. Logs and reports are derived from the validated job
directory and named artifacts, never from arbitrary absolute paths in
``job.json``. No job is created, resumed, accepted or cancelled here.
"""

from __future__ import annotations

import json
import os
import re
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from devjob import store

from .redact import redact_text, sanitize_control
from .timings import TimingRecorder, default_recorder

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DEV = PACKAGE_ROOT / "dev.py"
MAX_LOG_BYTES = 64 * 1024
MAX_LOG_LINES = 100
MAX_REPORT_BYTES = 256 * 1024
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
        env: Mapping[str, str] | None = None,
        timings: TimingRecorder | None = None,
    ) -> None:
        self.state_root = Path(state_root).expanduser() if state_root else store.state_root()
        self.dev_script = Path(dev_script).expanduser() if dev_script else DEFAULT_DEV
        self.python = python or sys.executable
        self.timeout_seconds = timeout_seconds
        self.environ = dict(os.environ if env is None else env)
        self.environ["DEV_CONTROL_PLANE_STATE"] = str(self.state_root)
        self.timings = timings or default_recorder()

    # ---- subprocess boundary -----------------------------------------------------
    def _run(self, args: list[str], *, input_text: str | None = None) -> str:
        command = [self.python, str(self.dev_script)] + args
        label = f"cli:dev_{args[0] if args else 'unknown'}"
        with self.timings.measure(label):
            try:
                completed = subprocess.run(
                    command,
                    input=input_text,
                    text=True,
                    capture_output=True,
                    timeout=self.timeout_seconds,
                    check=False,
                    shell=False,
                    env=self.environ,
                )
            except subprocess.TimeoutExpired as exc:
                raise JobError("Workflow v3 CLI timed out") from exc
            except OSError as exc:
                raise JobError(f"Workflow v3 CLI could not start: {exc.__class__.__name__}") from exc
            if completed.returncode != 0:
                detail = (completed.stderr or completed.stdout or "").strip()
                detail = redact_text(detail, limit=500)
                raise JobError(detail or f"Workflow v3 CLI exited {completed.returncode}")
            return completed.stdout

    def _json(self, args: list[str]) -> object:
        output = self._run(args)
        try:
            return json.loads(output)
        except json.JSONDecodeError as exc:
            raise JobError("Workflow v3 CLI returned invalid JSON") from exc

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
