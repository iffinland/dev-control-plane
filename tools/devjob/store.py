"""Durable job storage for Workflow v3.

Job state lives outside the Git repository (XDG state by default) so a dirty
working tree never contains runtime status, logs or credentials. Writes are
atomic and the per-job lock prevents two workers from driving one job.
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import tempfile
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator


SCHEMA_VERSION = 3
JOB_STATES = ("RUNNING", "SUCCESS", "FAILED", "BLOCKED", "TIMEOUT")
TERMINAL_STATES = frozenset({"SUCCESS", "FAILED", "BLOCKED", "TIMEOUT"})
DEFAULT_STATE_DIR = Path.home() / ".local/state/dev-control-plane"
class StoreError(RuntimeError):
    """A job could not be loaded, saved or locked."""


class JobLocked(StoreError):
    """Another process currently owns this job."""


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def state_root(explicit: str | Path | None = None) -> Path:
    if explicit is not None:
        return Path(explicit).expanduser()
    value = os.environ.get("DEV_CONTROL_PLANE_STATE")
    if value:
        return Path(value).expanduser()
    xdg = os.environ.get("XDG_STATE_HOME")
    if xdg:
        return Path(xdg).expanduser() / "dev-control-plane"
    return DEFAULT_STATE_DIR


def jobs_root(root: str | Path | None = None) -> Path:
    return state_root(root) / "jobs"


def ensure_private_dir(path: Path) -> Path:
    """Create a runtime directory readable only by the owner."""
    path.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass
    return path


def chmod_private(path: Path) -> None:
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def job_dir(job_id: str, root: str | Path | None = None) -> Path:
    if not job_id or "/" in job_id or job_id in {".", ".."}:
        raise StoreError(f"invalid job id: {job_id!r}")
    return jobs_root(root) / job_id


def slugify(value: str, limit: int = 32) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    return (slug or "job")[:limit].strip("-") or "job"


def new_job_id(title: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{slugify(title)}-{uuid.uuid4().hex[:8]}"


def _atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def save_job(job: dict, root: str | Path | None = None) -> None:
    job["updated_at"] = utc_now()
    _atomic_json(job_dir(job["id"], root) / "job.json", job)


def load_job(job_id: str, root: str | Path | None = None) -> dict:
    path = job_dir(job_id, root) / "job.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise StoreError(f"job not found: {job_id}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise StoreError(f"could not read job {job_id}: {exc}") from exc
    if not isinstance(data, dict) or data.get("id") != job_id:
        raise StoreError(f"job file is not a valid job record: {path}")
    return data


def list_jobs(root: str | Path | None = None) -> list[dict]:
    base = jobs_root(root)
    if not base.is_dir():
        return []
    jobs: list[dict] = []
    for entry in base.iterdir():
        if not entry.is_dir():
            continue
        try:
            job = load_job(entry.name, root)
        except StoreError:
            continue
        jobs.append(job)
    jobs.sort(key=lambda item: (item.get("created_at") or "", item.get("id") or ""), reverse=True)
    return jobs


def latest_job(root: str | Path | None = None, states: Iterable[str] | None = None) -> dict | None:
    allowed = set(states) if states is not None else None
    for job in list_jobs(root):
        if allowed is None or job.get("state") in allowed:
            return job
    return None


def append_event(
    job: dict,
    event: str,
    detail: str | None = None,
    root: str | Path | None = None,
) -> None:
    payload = {"ts": utc_now(), "event": event, "detail": detail or ""}
    path = job_dir(job["id"], root) / "events.jsonl"
    ensure_private_dir(path.parent)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")
    chmod_private(path)
    job.setdefault("events", []).append(payload)
    job["events"] = job["events"][-200:]
    job["updated_at"] = payload["ts"]
    save_job(job, root)


@contextmanager
def job_lock(job_id: str, root: str | Path | None = None) -> Iterator[None]:
    path = job_dir(job_id, root) / ".worker.lock"
    ensure_private_dir(path.parent)
    handle = path.open("a+", encoding="utf-8")
    try:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise JobLocked(f"another worker owns job {job_id}") from exc
        handle.seek(0)
        handle.truncate()
        handle.write(f"pid={os.getpid()} started={utc_now()}\n")
        handle.flush()
        yield
    finally:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def pid_alive(pid: int | None) -> bool:
    if not pid or pid <= 1:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def process_cmdline(pid: int | None) -> str:
    if not pid or pid <= 1:
        return ""
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return ""
    return " ".join(part.decode("utf-8", "replace") for part in raw.rstrip(b"\0").split(b"\0"))


def worker_is_alive(job: dict) -> bool:
    pid = job.get("worker_pid")
    if not pid_alive(pid):
        return False
    cmdline = process_cmdline(pid)
    return "_worker" in cmdline and str(job.get("id", "")) in cmdline


def read_json(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def safe_text(value: object, limit: int = 4000) -> str:
    """Return text while redacting obvious credential-shaped assignments."""
    text = str(value)
    text = re.sub(
        r"(?i)((?:bot_)?token|secret|password|api[_-]?key)\s*[:=]\s*\S+",
        r"\1=<redacted>",
        text,
    )
    return text[:limit]
