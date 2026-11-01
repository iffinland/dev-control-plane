"""Job lifecycle, acceptance verification and background execution.

The worker is a detached process (`start_new_session=True`) that invokes the
existing execution guard. The guard owns the OpenCode child process group and
enforces the wall-clock limit; this module never signals a process by name and
never signals Qortium.
"""

from __future__ import annotations

import json
import os
import shlex
import signal
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

TOOLS_DIR = Path(__file__).resolve().parents[1]
CONTROL_PLANE = TOOLS_DIR.parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import opencode_guard  # noqa: E402

from . import detect, notify  # noqa: E402
from .store import (  # noqa: E402
    JOB_STATES,
    JobLocked,
    StoreError,
    append_event,
    chmod_private,
    ensure_private_dir,
    job_dir,
    job_lock,
    load_job,
    parse_timestamp,
    pid_alive,
    process_cmdline,
    read_json,
    save_job,
    state_root,
    utc_now,
    worker_is_alive,
)


DEV_SCRIPT = TOOLS_DIR / "dev.py"
GUARD_SCRIPT = TOOLS_DIR / "opencode_guard.py"
DEFAULT_WORKSPACE = Path("/home/iffi/dev-workspace")
DEFAULT_AGENT = "opencode-development"
DEFAULT_MODEL = "deepseek/deepseek-flash"
DEFAULT_LABEL = "Acceptance"
DEFAULT_ACCEPTANCE_TIMEOUT = 1800
WORKER_LOG = "worker.log"
RUN_LOG = "run.log"
REPORT = "report.md"
COMPLETION = "completion.json"
CANCEL_REQUEST = "cancel.requested.json"
DEFAULT_SESSION_POLL_SECONDS = 5.0
DEFAULT_SESSION_IDLE_SECONDS = 20.0
DEFAULT_SESSION_CONFIRM_SECONDS = 5.0
DEFAULT_CANCEL_GRACE_SECONDS = 20.0
CANCEL_SKIP_DETAIL = "verification skipped because the owner cancelled the run"


class JobError(RuntimeError):
    """A user-facing job operation failed."""


def utc_now_dt() -> datetime:
    return datetime.now(timezone.utc)


def _env_float(name: str, default: float, minimum: float, maximum: float) -> float:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return max(minimum, min(maximum, value))


def _elapsed_seconds(start: str | None, end: str | None = None) -> int | None:
    started = parse_timestamp(start)
    if started is None:
        return None
    finished = parse_timestamp(end) if end else utc_now_dt()
    if finished is None:
        finished = utc_now_dt()
    return max(0, int((finished - started).total_seconds()))


def parse_duration(value: str | int | None, default: int = opencode_guard.MAX_TIMEOUT_SECONDS) -> int:
    if value is None:
        return default
    if isinstance(value, int):
        seconds = value
    else:
        try:
            seconds = opencode_guard.parse_duration(str(value))
        except Exception as exc:  # argparse.ArgumentTypeError
            raise JobError(str(exc)) from exc
    if seconds <= 0:
        raise JobError("timeout must be greater than zero")
    if seconds > opencode_guard.MAX_TIMEOUT_SECONDS:
        raise JobError("timeout exceeds the eight-hour maximum")
    return seconds


def parse_criterion(value: str) -> dict:
    text = value.strip()
    if not text:
        raise JobError("acceptance criterion cannot be empty")
    if "::" in text:
        label, command = text.split("::", 1)
        label = label.strip() or DEFAULT_LABEL
        command = command.strip()
    else:
        label = DEFAULT_LABEL
        command = text
    if not command:
        raise JobError(f"acceptance criterion has no command: {value!r}")
    return {"kind": "command", "label": label, "command": command, "required": True}


def manual_criterion(value: str, number: int) -> dict:
    text = value.strip()
    if not text:
        raise JobError("manual acceptance criterion cannot be empty")
    return {
        "kind": "manual",
        "label": text,
        "command": None,
        "required": True,
        "id": f"AC{number}",
    }


def criteria_from_file(path: str | Path, start: int = 1) -> tuple[list[dict], int]:
    target = Path(path).expanduser()
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise JobError(f"cannot read acceptance file {target}: {exc}") from exc
    if not isinstance(data, list):
        raise JobError("acceptance file must contain a JSON array")
    criteria: list[dict] = []
    number = start
    for item in data:
        if isinstance(item, str):
            criterion = parse_criterion(item)
        elif isinstance(item, dict):
            kind = str(item.get("kind", "command"))
            label = str(item.get("label") or item.get("name") or DEFAULT_LABEL)
            if kind == "manual":
                criterion = manual_criterion(label, number)
            elif kind == "command":
                command = item.get("command")
                if not isinstance(command, str) or not command.strip():
                    raise JobError("acceptance command entries need a non-empty command")
                criterion = {
                    "kind": "command",
                    "label": label,
                    "command": command.strip(),
                    "required": bool(item.get("required", True)),
                }
                if item.get("timeout_seconds") is not None:
                    criterion["timeout_seconds"] = int(item["timeout_seconds"])
            else:
                raise JobError(f"unknown acceptance criterion kind: {kind}")
        else:
            raise JobError("acceptance entries must be strings or objects")
        criterion["id"] = f"AC{number}"
        number += 1
        criteria.append(criterion)
    return criteria, number


def build_criteria(
    commands: Iterable[str] | None = None,
    manual: Iterable[str] | None = None,
    files: Iterable[str | Path] | None = None,
) -> list[dict]:
    criteria: list[dict] = []
    number = 1
    for path in files or []:
        items, number = criteria_from_file(path, number)
        criteria.extend(items)
    for value in commands or []:
        criterion = parse_criterion(value)
        criterion["id"] = f"AC{number}"
        number += 1
        criteria.append(criterion)
    for value in manual or []:
        criteria.append(manual_criterion(value, number))
        number += 1
    if not criteria:
        raise JobError(
            "explicit acceptance criteria are required: use --criterion, "
            "--manual-criterion or --acceptance-file"
        )
    return criteria


def git_snapshot(repo: Path) -> dict:
    def git(*args: str) -> str:
        try:
            result = subprocess.run(
                ["git", "-C", str(repo), *args],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return ""
        return result.stdout.strip() if result.returncode == 0 else ""

    return {
        "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
        "head": git("rev-parse", "HEAD"),
        "dirty": bool(git("status", "--porcelain")),
        "status": git("status", "--porcelain")[:4000],
        "diffstat": git("diff", "--stat")[:4000],
        "captured_at": utc_now(),
    }


def _guard_command(
    job: dict,
    timeout_seconds: int,
    *,
    proc_root: str | Path = "/proc",
    workspace: str | Path = DEFAULT_WORKSPACE,
) -> list[str]:
    base = [
        sys.executable,
        str(GUARD_SCRIPT),
        "run",
        "--timeout",
        f"{timeout_seconds}s",
        "--workspace",
        str(workspace),
        "--proc-root",
        str(proc_root),
        "--lock-file",
        str(state_root() / "guard.lock"),
        "--log",
        str(job_dir(job["id"]) / RUN_LOG),
        "--pid-file",
        str(job_dir(job["id"]) / "child.pid.json"),
        "--completion-file",
        str(job_dir(job["id"]) / COMPLETION),
        "--session-title",
        f"{job['title']} [job {job['id']}]",
        "--session-poll-seconds",
        f"{_env_float('DEV_SESSION_POLL_SECONDS', DEFAULT_SESSION_POLL_SECONDS, 0.0, 300.0):g}",
        "--session-idle-seconds",
        f"{_env_float('DEV_SESSION_IDLE_SECONDS', DEFAULT_SESSION_IDLE_SECONDS, 0.0, 3600.0):g}",
        "--session-confirm-seconds",
        f"{_env_float('DEV_SESSION_CONFIRM_SECONDS', DEFAULT_SESSION_CONFIRM_SECONDS, 0.0, 300.0):g}",
    ]
    if job.get("session_id") and not job.get("force_new_session"):
        base.extend(["--session-id", str(job["session_id"])])
    base.append("--")
    title = f"{job['title']} [job {job['id']}]"
    opencode = [
        "opencode",
        "run",
        "--agent",
        str(job.get("agent") or DEFAULT_AGENT),
        "--model",
        str(job.get("model") or DEFAULT_MODEL),
        "--title",
        title,
    ]
    if job.get("session_id") and not job.get("force_new_session"):
        opencode.extend(["--session", str(job["session_id"])])
    prompt = job.get("resume_prompt") if job.get("is_resume") else job.get("prompt")
    opencode.append(str(prompt or job.get("prompt") or ""))
    return base + opencode


def preflight(proc_root: str | Path = "/proc", workspace: str | Path = DEFAULT_WORKSPACE) -> dict:
    command = [
        sys.executable,
        str(GUARD_SCRIPT),
        "check",
        "--json",
        "--workspace",
        str(workspace),
        "--proc-root",
        str(proc_root),
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=60, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise JobError(f"guard preflight could not run: {exc}") from exc
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        payload = {"status": "REFUSE", "refusals": [result.stderr.strip() or "guard preflight failed"]}
    payload["exit_code"] = result.returncode
    return payload


def _new_job(
    *,
    title: str,
    prompt: str,
    repo: Path,
    branch: str | None,
    criteria: list[dict],
    timeout_seconds: int,
    agent: str,
    model: str,
    workspace: Path,
    notifications_enabled: bool,
    preflight_payload: dict,
) -> dict:
    from .store import new_job_id

    now = utc_now()
    job_id = new_job_id(title)
    directory = ensure_private_dir(job_dir(job_id))
    return {
        "schema_version": 3,
        "id": job_id,
        "title": title,
        "prompt": prompt,
        "repo": str(repo),
        "branch": branch,
        "agent": agent,
        "model": model,
        "workspace": str(workspace),
        "state": "RUNNING",
        "created_at": now,
        "started_at": None,
        "ended_at": None,
        "updated_at": now,
        "duration_seconds": None,
        "attempt_duration_seconds": None,
        "total_attempt_seconds": None,
        "timeout_seconds": timeout_seconds,
        "worker_pid": None,
        "guard_pid": None,
        "child_pid": None,
        "child_pgid": None,
        "exit_code": None,
        "completion": None,
        "session_id": None,
        "is_resume": False,
        "force_new_session": False,
        "resume_prompt": None,
        "resume_count": 0,
        "attempts": [],
        "acceptance_criteria": criteria,
        "verification": {},
        "detected_issues": [],
        "blocker": None,
        "git": git_snapshot(repo),
        "log_path": str(directory / RUN_LOG),
        "worker_log_path": str(directory / WORKER_LOG),
        "report_path": str(directory / REPORT),
        "events_path": str(directory / "events.jsonl"),
        "notifications_enabled": notifications_enabled,
        "notifications": [],
        "preflight": preflight_payload,
        "events": [],
    }


def _criteria_state(criteria: list[dict], verification: dict) -> tuple[bool, bool, list[str]]:
    all_verified = True
    pending_manual = False
    failures: list[str] = []
    for criterion in criteria:
        if not criterion.get("required", True):
            continue
        result = verification.get(criterion["id"], {})
        verified = bool(result.get("verified"))
        if criterion.get("kind") == "manual" and not verified:
            pending_manual = True
        if not verified:
            all_verified = False
            failures.append(criterion["id"])
    return all_verified, pending_manual, failures


def evaluate_state(
    job: dict,
    guard_exit_code: int,
    issues: list[dict],
    verification: dict,
) -> tuple[str, str | None]:
    criteria = job.get("acceptance_criteria") or []
    all_verified, pending_manual, _failures = _criteria_state(criteria, verification)
    blocked = any(item.get("severity") == "blocked" for item in issues)
    failed = any(item.get("severity") == "failed" for item in issues)

    if guard_exit_code == opencode_guard.EXIT_TIMEOUT:
        return "TIMEOUT", "the execution guard reached the wall-clock limit"
    if guard_exit_code == opencode_guard.EXIT_REFUSE:
        return "BLOCKED", "the execution guard refused to start or continue"
    if blocked:
        return "BLOCKED", "a blocking condition was detected"
    if not criteria:
        return "BLOCKED", "no explicit acceptance criteria were recorded"
    if pending_manual:
        return "BLOCKED", "manual acceptance criteria are still pending owner verification"
    if failed:
        return "FAILED", "a failure condition was detected"
    if not all_verified:
        return "FAILED", "one or more required acceptance criteria did not verify"
    if guard_exit_code != 0:
        return "FAILED", f"the guarded command exited with code {guard_exit_code}"
    return "SUCCESS", None


def _run_criterion(criterion: dict, job: dict) -> dict:
    criterion_id = criterion["id"]
    if criterion.get("kind") == "manual":
        return {
            "criterion_id": criterion_id,
            "kind": "manual",
            "verified": bool(criterion.get("verified")),
            "at": utc_now(),
            "detail": criterion.get("note") or "manual owner acceptance",
        }
    command = str(criterion.get("command") or "")
    timeout = int(criterion.get("timeout_seconds") or DEFAULT_ACCEPTANCE_TIMEOUT)
    log_path = job_dir(job["id"]) / f"acceptance-{criterion_id}.log"
    started = time.monotonic()
    try:
        result = subprocess.run(
            command,
            cwd=job.get("repo") or None,
            shell=True,
            executable="/bin/bash",
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=os.environ.copy(),
        )
        output = (result.stdout or "") + (result.stderr or "")
        exit_code = result.returncode
        timed_out = False
    except subprocess.TimeoutExpired as exc:
        output = (exc.stdout or "") + (exc.stderr or "")
        if isinstance(output, bytes):
            output = output.decode("utf-8", "replace")
        exit_code = None
        timed_out = True
    except OSError as exc:
        output = f"{exc.__class__.__name__}: {exc}"
        exit_code = None
        timed_out = False
    duration = round(time.monotonic() - started, 3)
    try:
        log_path.write_text(output[-20000:], encoding="utf-8")
        chmod_private(log_path)
    except OSError:
        pass
    verified = exit_code == 0 and not timed_out
    return {
        "criterion_id": criterion_id,
        "kind": "command",
        "command": command,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "duration_seconds": duration,
        "verified": verified,
        "at": utc_now(),
        "log_path": str(log_path),
        "output_tail": output[-1200:],
    }


def verify_criteria(
    job: dict,
    skip_commands: bool = False,
    *,
    skip_detail: str = "verification skipped because the run timed out or was refused",
) -> dict:
    verification: dict = dict(job.get("verification") or {})
    for criterion in job.get("acceptance_criteria") or []:
        if criterion.get("kind") == "manual":
            verification[criterion["id"]] = _run_criterion(criterion, job)
            continue
        if skip_commands:
            verification[criterion["id"]] = {
                "criterion_id": criterion["id"],
                "kind": "command",
                "command": criterion.get("command"),
                "verified": False,
                "skipped": True,
                "detail": skip_detail,
                "at": utc_now(),
            }
            continue
        verification[criterion["id"]] = _run_criterion(criterion, job)
    return verification


def _timestamp_ms(value: object) -> int | None:
    if not value:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        return int(datetime.fromisoformat(text).timestamp() * 1000)
    except (TypeError, ValueError, OverflowError):
        return None


def _discover_session(job: dict) -> str | None:
    try:
        result = subprocess.run(
            ["opencode", "session", "list", "--format", "json", "--max-count", "50"],
            cwd=job.get("repo") or None,
            capture_output=True,
            text=True,
            timeout=25,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0 or not result.stdout.strip():
        return None
    try:
        sessions = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    if isinstance(sessions, dict):
        sessions = sessions.get("sessions") or sessions.get("data") or []
    if not isinstance(sessions, list):
        return None
    title = f"{job['title']} [job {job['id']}]"
    for item in sessions:
        if not isinstance(item, dict):
            continue
        item_title = str(item.get("title") or "")
        if item_title == title or job["id"] in item_title:
            return str(item.get("id") or item.get("sessionID") or "") or None
    return None


def _read_child_pid(job: dict) -> dict | None:
    payload = read_json(job_dir(job["id"]) / "child.pid.json")
    if not payload:
        return None
    if payload.get("pid"):
        job["child_pid"] = int(payload["pid"])
    if payload.get("pgid"):
        job["child_pgid"] = int(payload["pgid"])
    return payload


def _append_attempt(job: dict, attempt: dict) -> None:
    attempts = job.setdefault("attempts", [])
    attempts.append(attempt)
    job["attempts"] = attempts[-50:]


def _finish(
    job: dict,
    *,
    guard_exit_code: int,
    issues: list[dict],
    verification: dict,
    session_id: str | None,
    reason_override: str | None = None,
    cancelled: bool = False,
) -> str:
    if cancelled:
        state = "CANCELLED"
        blocker = reason_override or "cancelled by owner request"
        job["cancelled_at"] = utc_now()
    else:
        state, blocker = evaluate_state(job, guard_exit_code, issues, verification)
        if reason_override:
            blocker = reason_override
    job["state"] = state
    job["blocker"] = blocker
    job["exit_code"] = guard_exit_code
    job["detected_issues"] = issues
    job["verification"] = verification
    if session_id:
        job["session_id"] = session_id
    job["ended_at"] = utc_now()
    job["duration_seconds"] = _elapsed_seconds(job.get("started_at"), job["ended_at"])
    attempts = job.get("attempts") or []
    attempt_total = 0
    for attempt in attempts:
        duration = attempt.get("duration_seconds")
        if duration is None and attempt.get("started_at"):
            duration = _elapsed_seconds(attempt.get("started_at"), attempt.get("ended_at"))
            attempt["duration_seconds"] = duration
        if isinstance(duration, int):
            attempt_total += duration
    job["total_attempt_seconds"] = attempt_total if attempts else None
    job["attempt_duration_seconds"] = (
        attempts[-1].get("duration_seconds") if attempts else None
    )
    job["is_resume"] = False
    job["resume_prompt"] = None
    job["force_new_session"] = False
    append_event(job, "finished", f"state={state} exit={guard_exit_code}")
    write_report(job)
    if job.get("notifications_enabled") is False:
        job.setdefault("notifications", []).append(
            {"at": utc_now(), "state": state, "sent": False, "reason": "disabled for job"}
        )
    else:
        try:
            notify.notify_job(job)
        except Exception as exc:  # noqa: BLE001 - notification must not break the job
            job.setdefault("notifications", []).append(
                {
                    "at": utc_now(),
                    "state": state,
                    "sent": False,
                    "reason": f"notification error: {exc.__class__.__name__}",
                }
            )
    save_job(job)
    return state


def cancel_request_path(job_id: str) -> Path:
    return job_dir(job_id) / CANCEL_REQUEST


def read_cancel_request(job: dict) -> dict | None:
    """Read the durable cancel marker without following symlinks."""

    path = cancel_request_path(str(job.get("id") or ""))
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except (FileNotFoundError, OSError):
        return None
    try:
        raw = os.read(descriptor, 16384)
    finally:
        os.close(descriptor)
    try:
        payload = json.loads(raw.decode("utf-8", "replace"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _current_attempt_number(job: dict) -> int:
    attempts = job.get("attempts") or []
    if attempts and isinstance(attempts[-1], dict):
        try:
            return int(attempts[-1].get("number") or len(attempts))
        except (TypeError, ValueError):
            return len(attempts)
    return len(attempts) if isinstance(attempts, list) else 0


def cancel_request_matches(job: dict, marker: dict | None = None) -> bool:
    """A cancel marker applies only to the attempt it was requested for."""

    marker = marker if marker is not None else read_cancel_request(job)
    if not marker:
        return False
    if str(marker.get("job_id") or "") != str(job.get("id") or ""):
        return False
    try:
        requested_attempt = int(marker.get("attempt_number"))
    except (TypeError, ValueError):
        return False
    return requested_attempt == _current_attempt_number(job)


def _write_cancel_request(job: dict, guard_pid: int) -> dict:
    marker = {
        "job_id": str(job.get("id") or ""),
        "attempt_number": _current_attempt_number(job),
        "guard_pid": int(guard_pid),
        "worker_pid": job.get("worker_pid"),
        "requested_at": utc_now(),
    }
    path = cancel_request_path(marker["job_id"])
    ensure_private_dir(path.parent)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(marker, handle, indent=2, sort_keys=True)
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
    return marker


def _remove_cancel_request(job: dict) -> None:
    try:
        cancel_request_path(str(job.get("id") or "")).unlink()
    except FileNotFoundError:
        pass


def _process_looks_like_qortium(pid: int) -> bool:
    cmdline = process_cmdline(pid).lower()
    if not cmdline:
        return False
    return any(
        marker in cmdline
        for marker in (
            "qortium.jar",
            "/qortium-data",
            "/qortium-preview",
            "/qortium/qortium",
        )
    )


def _verify_guard_identity(job: dict, guard_pid: int) -> None:
    """Refuse to signal anything that is not this job's Workflow v3 guard."""

    try:
        pid = int(guard_pid)
    except (TypeError, ValueError) as exc:
        raise JobError("the recorded guard PID is not an integer") from exc
    if pid <= 1:
        raise JobError("refusing to signal an unsafe guard PID")
    if pid == os.getpid() or pid == os.getpgrp():
        raise JobError("refusing to signal the cancelling process group")
    if _process_looks_like_qortium(pid):
        raise JobError("refusing to signal a detected Qortium process")
    cmdline = process_cmdline(pid)
    if not cmdline:
        raise JobError("the recorded guard process is not running")
    if "opencode_guard.py" not in cmdline:
        raise JobError("the recorded PID is not the Workflow v3 execution guard")
    if " run" not in f" {cmdline}":
        raise JobError("the recorded guard is not running a job")
    job_id = str(job.get("id") or "")
    log_path = str(job_dir(job_id) / RUN_LOG)
    session_title = f"{job.get('title')} [job {job_id}]"
    if not (
        job_id in cmdline
        or log_path in cmdline
        or session_title in cmdline
    ):
        raise JobError("the guard identity does not match this job")


def _cancelled_verification(job: dict, verification: dict) -> dict:
    result = dict(verification or {})
    for criterion in job.get("acceptance_criteria") or []:
        existing = result.get(criterion["id"]) or {}
        if existing.get("verified"):
            continue
        result[criterion["id"]] = {
            "criterion_id": criterion["id"],
            "kind": criterion.get("kind"),
            "command": criterion.get("command"),
            "verified": False,
            "skipped": True,
            "detail": CANCEL_SKIP_DETAIL,
            "at": utc_now(),
        }
    return result


def _finalize_cancelled(job: dict, marker: dict, reason: str) -> dict:
    """Finalize a cancelled attempt when the worker could not do it itself."""

    issues = list(job.get("detected_issues") or [])
    verification = _cancelled_verification(job, job.get("verification") or {})
    exit_code = job.get("exit_code")
    if exit_code is None:
        exit_code = 128 + int(signal.SIGTERM)
    _finish(
        job,
        guard_exit_code=int(exit_code),
        issues=issues,
        verification=verification,
        session_id=job.get("session_id"),
        reason_override=reason,
        cancelled=True,
    )
    append_event(
        job,
        "cancel_finalized",
        f"attempt={marker.get('attempt_number')} guard_pid={marker.get('guard_pid')}",
    )
    return job


def cancel_job(
    job_id: str,
    *,
    grace_seconds: float | None = None,
    sleep=time.sleep,
) -> dict:
    """Cancel one RUNNING job by signalling its verified guard only.

    The command never signals by name, never escalates beyond SIGTERM and never
    touches the working tree or OpenCode session. Cancellation is resumable.
    """

    job = load_job(job_id)
    if str(job.get("state")) != "RUNNING":
        raise JobError(
            f"job {job_id} is {job.get('state')}; only a RUNNING job can be cancelled"
        )
    if not worker_is_alive(job):
        changed = reconcile_job(job)
        job = load_job(job_id)
        detail = (
            "worker was already gone; the job was reconciled without sending a signal"
            if changed
            else "worker is not running; no signal was sent"
        )
        return {"cancel_status": "reconciled", "detail": detail, "job": job}

    guard_pid = job.get("guard_pid")
    if not guard_pid:
        raise JobError("no verified guard PID is recorded for this job")
    _verify_guard_identity(job, int(guard_pid))

    marker = _write_cancel_request(job, int(guard_pid))
    append_event(
        job,
        "cancel_requested",
        f"attempt={marker['attempt_number']} guard_pid={marker['guard_pid']}",
    )
    try:
        os.kill(int(guard_pid), signal.SIGTERM)
    except ProcessLookupError:
        # The guard exited between identity verification and the signal. The
        # worker is allowed to reconcile or observe the marker normally.
        pass
    except OSError as exc:
        _remove_cancel_request(job)
        append_event(job, "cancel_failed", f"signal failed: {exc.__class__.__name__}")
        raise JobError("could not signal the verified guard process") from exc

    grace = (
        DEFAULT_CANCEL_GRACE_SECONDS
        if grace_seconds is None
        else max(1.0, float(grace_seconds))
    )
    deadline = time.monotonic() + grace
    while True:
        job = load_job(job_id)
        if str(job.get("state")) != "RUNNING":
            break
        if not worker_is_alive(job):
            # Give the worker a short moment to persist its own final state.
            sleep(0.1)
            job = load_job(job_id)
            if str(job.get("state")) != "RUNNING":
                break
            job = _finalize_cancelled(
                job,
                marker,
                "cancelled by owner request; worker finalized after cancellation",
            )
            return {
                "cancel_status": "cancelled",
                "detail": "the worker disappeared; the job was finalized as CANCELLED",
                "job": job,
            }
        if time.monotonic() >= deadline:
            break
        sleep(0.1)

    job = load_job(job_id)
    state = str(job.get("state"))
    if state == "CANCELLED":
        # Durable evidence: the report must exist even if an external worker
        # finalized from the marker without writing it.
        write_report(job)
        save_job(job)
        return {
            "cancel_status": "cancelled",
            "detail": "the guard and its child process group were stopped; the job is CANCELLED",
            "job": job,
        }
    if state == "RUNNING":
        return {
            "cancel_status": "pending",
            "detail": (
                "cancel requested; the guard is still alive after the grace period. "
                "No escalation was attempted."
            ),
            "job": job,
        }
    if (
        cancel_request_matches(job, marker)
        and not worker_is_alive(job)
        and job.get("exit_code") == 128 + int(signal.SIGTERM)
    ):
        job = _finalize_cancelled(
            job,
            marker,
            "cancelled by owner request; the worker reported a terminated guard",
        )
        return {
            "cancel_status": "cancelled",
            "detail": "the worker exited after the signal; the job was finalized as CANCELLED",
            "job": job,
        }
    return {
        "cancel_status": "finished",
        "detail": f"the job finished as {state} before cancellation completed",
        "job": job,
    }


def run_worker(job_id: str) -> int:
    job = load_job(job_id)
    try:
        with job_lock(job_id):
            job = load_job(job_id)
            directory = ensure_private_dir(job_dir(job_id))
            now = utc_now()
            job["worker_pid"] = os.getpid()
            if not job.get("started_at"):
                job["started_at"] = now
            job["state"] = "RUNNING"
            job["ended_at"] = None
            job["blocker"] = None
            job["detected_issues"] = []
            job["exit_code"] = None
            job["completion"] = None
            attempt_number = len(job.get("attempts") or []) + 1
            attempt = {
                "number": attempt_number,
                "started_at": now,
                "ended_at": None,
                "duration_seconds": None,
                "timeout_seconds": job.get("timeout_seconds"),
                "session_id": job.get("session_id"),
                "is_resume": bool(job.get("is_resume")),
                "worker_pid": os.getpid(),
                "completion": None,
            }
            # Persist the attempt at start so `dev status` can report the
            # current attempt separately from total job elapsed time.
            _append_attempt(job, attempt)
            try:
                (directory / COMPLETION).unlink()
            except FileNotFoundError:
                pass
            append_event(
                job,
                "attempt_started",
                f"attempt={attempt_number} resume={bool(job.get('is_resume'))}",
            )
            save_job(job)

            guard_command = _guard_command(
                job,
                int(job.get("timeout_seconds") or opencode_guard.MAX_TIMEOUT_SECONDS),
                proc_root=job.get("proc_root") or "/proc",
                workspace=job.get("workspace") or str(DEFAULT_WORKSPACE),
            )
            append_event(job, "guard_command", " ".join(shlex.quote(part) for part in guard_command))
            save_job(job)

            run_log = directory / RUN_LOG
            run_log.touch(exist_ok=True)
            chmod_private(run_log)
            try:
                run_log_start = run_log.stat().st_size
            except OSError:
                run_log_start = 0
            worker_log = directory / WORKER_LOG
            worker_log.touch(exist_ok=True)
            chmod_private(worker_log)

            guard_exit_code = 1
            try:
                guard_process = subprocess.Popen(
                    guard_command,
                    cwd=job.get("repo") or None,
                    stdin=subprocess.DEVNULL,
                    stdout=sys.stdout,
                    stderr=subprocess.STDOUT,
                )
            except OSError as exc:
                issue = detect.Issue(
                    "worker_error",
                    "failed",
                    f"could not start the execution guard: {exc.__class__.__name__}",
                    0,
                    str(exc)[:300],
                )
                verification = verify_criteria(job, skip_commands=True)
                _finish(
                    job,
                    guard_exit_code=1,
                    issues=[issue.asdict()],
                    verification=verification,
                    session_id=job.get("session_id"),
                )
                return 1

            job["guard_pid"] = guard_process.pid
            save_job(job)
            guard_exit_code = int(guard_process.wait())
            cancel_marker = read_cancel_request(job)
            cancelled = cancel_request_matches(job, cancel_marker)
            if cancelled:
                append_event(
                    job,
                    "cancel_observed",
                    f"attempt={attempt_number} guard_exit={guard_exit_code}",
                )
                attempt["cancelled"] = True
            child = _read_child_pid(job)
            job["child_pid"] = (child or {}).get("pid") or job.get("child_pid")
            job["child_pgid"] = (child or {}).get("pgid") or job.get("child_pgid")
            completion = read_json(directory / COMPLETION)
            if completion:
                job["completion"] = completion
                attempt["completion"] = completion
                completion_session = completion.get("session_id")
                if completion_session:
                    # The guard's structured evidence identifies the session that
                    # actually completed this attempt.
                    job["session_id"] = str(completion_session)
                append_event(
                    job,
                    "session_completion",
                    f"message={completion.get('message_id')} action={completion.get('action')}",
                )
            save_job(job)

            session_id = job.get("session_id") or _discover_session(job)
            attempt_started_ms = _timestamp_ms(attempt.get("started_at"))
            issues: list[dict] | None = None
            if not cancelled:
                if session_id:
                    structured = detect.scan_session(
                        session_id,
                        cwd=job.get("repo"),
                        since_ms=attempt_started_ms,
                    )
                    if structured is not None:
                        issues = [issue.asdict() for issue in structured]
                if issues is None:
                    issues = [
                        issue.asdict()
                        for issue in detect.scan_log(
                            directory / RUN_LOG, start_offset=run_log_start
                        )
                    ]
            else:
                issues = []
            skip_commands = cancelled or guard_exit_code in (
                opencode_guard.EXIT_TIMEOUT,
                opencode_guard.EXIT_REFUSE,
            )
            verification = verify_criteria(
                job,
                skip_commands=skip_commands,
                skip_detail=(
                    CANCEL_SKIP_DETAIL
                    if cancelled
                    else "verification skipped because the run timed out or was refused"
                ),
            )
            if not cancelled:
                _, pending_manual, missing = _criteria_state(
                    job.get("acceptance_criteria") or [], verification
                )
                if missing and not pending_manual and not skip_commands:
                    issues.append(
                        detect.Issue(
                            "incomplete_implementation",
                            "failed",
                            f"required acceptance criteria did not verify: {', '.join(missing)}",
                            0,
                            "",
                        ).asdict()
                    )
            attempt["ended_at"] = utc_now()
            attempt["duration_seconds"] = _elapsed_seconds(
                attempt.get("started_at"), attempt.get("ended_at")
            )
            attempt["guard_exit_code"] = guard_exit_code
            attempt["detected_issues"] = len(issues)
            attempt["session_id"] = session_id
            state = _finish(
                job,
                guard_exit_code=guard_exit_code,
                issues=issues,
                verification=verification,
                session_id=session_id,
                cancelled=cancelled,
            )
            append_event(job, "attempt_finished", f"attempt={attempt_number} state={state}")
            return 0 if state == "SUCCESS" else 1
    except JobLocked as exc:
        append_event(job, "worker_lock_conflict", str(exc))
        return 2
    except (StoreError, OSError, ValueError) as exc:
        try:
            job = load_job(job_id)
            job["state"] = "FAILED"
            job["blocker"] = f"worker error: {exc.__class__.__name__}"
            job["ended_at"] = utc_now()
            append_event(job, "worker_error", job["blocker"])
            write_report(job)
            save_job(job)
        except Exception:  # noqa: BLE001 - last-resort state write
            pass
        print(f"dev worker: {exc}", file=sys.stderr)
        return 1


def create_job(
    *,
    title: str,
    prompt: str,
    repo: str | Path,
    branch: str | None,
    criteria: list[dict],
    timeout_seconds: int,
    agent: str = DEFAULT_AGENT,
    model: str = DEFAULT_MODEL,
    workspace: str | Path = DEFAULT_WORKSPACE,
    proc_root: str | Path = "/proc",
    notifications_enabled: bool = True,
) -> dict:
    repo_path = Path(repo).expanduser().resolve()
    if not repo_path.is_dir():
        raise JobError(f"repository path does not exist: {repo_path}")
    if not prompt.strip():
        raise JobError("prompt cannot be empty")
    payload = preflight(proc_root=proc_root, workspace=workspace)
    job = _new_job(
        title=title,
        prompt=prompt,
        repo=repo_path,
        branch=branch,
        criteria=criteria,
        timeout_seconds=timeout_seconds,
        agent=agent,
        model=model,
        workspace=Path(workspace).expanduser(),
        notifications_enabled=notifications_enabled,
        preflight_payload=payload,
    )
    job["proc_root"] = str(proc_root)
    if payload.get("status") == "REFUSE" or payload.get("exit_code") == opencode_guard.EXIT_REFUSE:
        job["state"] = "BLOCKED"
        job["blocker"] = "guard preflight refused: " + "; ".join(payload.get("refusals") or ["unknown"])
        job["ended_at"] = utc_now()
        job["detected_issues"] = [
            detect.Issue(
                "guard_refusal",
                "blocked",
                job["blocker"],
                0,
                "",
            ).asdict()
        ]
        save_job(job)
        append_event(job, "blocked_preflight", job["blocker"])
        write_report(job)
        try:
            notify.notify_job(job)
        except Exception:  # noqa: BLE001
            pass
        save_job(job)
        return job

    save_job(job)
    append_event(job, "created", f"repo={repo_path}")
    spawn_worker(job)
    return load_job(job["id"])


def spawn_worker(job: dict) -> int:
    directory = ensure_private_dir(job_dir(job["id"]))
    worker_log = directory / WORKER_LOG
    command = [sys.executable, str(DEV_SCRIPT), "_worker", "--job-id", job["id"]]
    env = os.environ.copy()
    env["DEV_CONTROL_PLANE_STATE"] = str(state_root())
    with worker_log.open("ab", buffering=0) as handle:
        chmod_private(worker_log)
        try:
            process = subprocess.Popen(
                command,
                cwd=job.get("repo") or None,
                stdin=subprocess.DEVNULL,
                stdout=handle,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                close_fds=True,
                env=env,
            )
        except OSError as exc:
            job["state"] = "FAILED"
            job["blocker"] = f"could not start background worker: {exc.__class__.__name__}"
            job["ended_at"] = utc_now()
            append_event(job, "worker_start_failed", job["blocker"])
            write_report(job)
            save_job(job)
            raise JobError(job["blocker"]) from exc
    job["worker_pid"] = process.pid
    job["worker_started_at"] = utc_now()
    job["state"] = "RUNNING"
    save_job(job)
    append_event(job, "worker_started", f"pid={process.pid}")
    return process.pid


def resume_job(
    job_id: str,
    *,
    timeout_seconds: int | None = None,
    prompt: str | None = None,
    new_session: bool = False,
    force: bool = False,
) -> dict:
    job = load_job(job_id)
    if job.get("state") == "RUNNING" and worker_is_alive(job):
        raise JobError(f"job {job_id} is already RUNNING (worker pid {job.get('worker_pid')})")
    if job.get("state") == "SUCCESS" and not force:
        raise JobError(f"job {job_id} already succeeded; use --force to run another attempt")
    session_id = job.get("session_id") or _discover_session(job)
    if session_id:
        job["session_id"] = session_id
    if not session_id and not new_session and job.get("attempts"):
        raise JobError(
            "the OpenCode session id is unknown; refusing to attach to a random session. "
            "Use --new-session to continue in the same working tree with a new session."
        )
    if job.get("state") == "RUNNING":
        job["state"] = "FAILED"
        job["blocker"] = "previous worker is gone; resuming"
        job["ended_at"] = utc_now()
        append_event(job, "reconciled_stale", job["blocker"])
    job["timeout_seconds"] = (
        parse_duration(timeout_seconds) if timeout_seconds is not None else int(job.get("timeout_seconds") or opencode_guard.MAX_TIMEOUT_SECONDS)
    )
    job["is_resume"] = True
    job["force_new_session"] = bool(new_session)
    if new_session:
        # Do not carry an old session id into detection when starting fresh.
        job["session_id"] = None
    job["resume_prompt"] = (
        prompt
        or "Continue the existing authorized task. Preserve the working tree and "
        "all completed work. Follow the task acceptance criteria and finish with "
        "verifiable evidence."
    )
    job["resume_count"] = int(job.get("resume_count") or 0) + 1
    job["state"] = "RUNNING"
    job["ended_at"] = None
    job["blocker"] = None
    job["cancelled_at"] = None
    append_event(job, "resume_requested", f"resume_count={job['resume_count']}")
    save_job(job)
    spawn_worker(job)
    return load_job(job_id)


def reconcile_job(job: dict) -> bool:
    if job.get("state") != "RUNNING":
        return False
    if worker_is_alive(job):
        return False
    marker = read_cancel_request(job)
    if cancel_request_matches(job, marker):
        job["state"] = "CANCELLED"
        job["blocker"] = "cancelled by owner request; worker finalized after cancellation"
        job["cancelled_at"] = utc_now()
        job["ended_at"] = job["cancelled_at"]
        job["verification"] = _cancelled_verification(
            job, job.get("verification") or {}
        )
        attempts = job.get("attempts") or []
        if attempts and isinstance(attempts[-1], dict):
            attempt = attempts[-1]
            attempt["cancelled"] = True
            if not attempt.get("ended_at"):
                attempt["ended_at"] = job["ended_at"]
                attempt["duration_seconds"] = _elapsed_seconds(
                    attempt.get("started_at"), job["ended_at"]
                )
        append_event(job, "reconciled_cancelled", job["blocker"])
    else:
        job["state"] = "FAILED"
        job["blocker"] = "background worker is no longer running; resume the job to continue"
        job["ended_at"] = utc_now()
        issue = detect.Issue("worker_lost", "failed", job["blocker"], 0, "").asdict()
        job.setdefault("detected_issues", []).append(issue)
        append_event(job, "reconciled_stale", job["blocker"])
    write_report(job)
    save_job(job)
    try:
        notify.notify_job(job)
    except Exception:  # noqa: BLE001
        pass
    save_job(job)
    return True


def accept_job(
    job_id: str,
    criterion_ids: Iterable[str] | None = None,
    all_manual: bool = False,
    note: str | None = None,
) -> dict:
    job = load_job(job_id)
    selected = set(criterion_ids or [])
    changed: list[str] = []
    for criterion in job.get("acceptance_criteria") or []:
        if criterion.get("kind") != "manual":
            continue
        if not all_manual and criterion["id"] not in selected:
            continue
        criterion["verified"] = True
        criterion["verified_at"] = utc_now()
        criterion["note"] = note or "accepted by owner"
        job.setdefault("verification", {})[criterion["id"]] = {
            "criterion_id": criterion["id"],
            "kind": "manual",
            "verified": True,
            "at": criterion["verified_at"],
            "detail": criterion["note"],
        }
        changed.append(criterion["id"])
    if not changed:
        raise JobError("no manual acceptance criteria were selected")
    append_event(job, "manual_acceptance", ", ".join(changed))
    guard_exit = int(job.get("exit_code") if job.get("exit_code") is not None else 1)
    issues = list(job.get("detected_issues") or [])
    state, blocker = evaluate_state(job, guard_exit, issues, job.get("verification") or {})
    job["state"] = state
    job["blocker"] = blocker
    if state == "SUCCESS":
        job["ended_at"] = utc_now()
    write_report(job)
    save_job(job)
    if state == "SUCCESS":
        try:
            notify.notify_job(job)
        except Exception:  # noqa: BLE001
            pass
        save_job(job)
    return job


def _attempt_info(job: dict) -> dict:
    attempts = job.get("attempts") or []
    current = attempts[-1] if attempts else None
    if not current:
        return {
            "attempt_number": 0,
            "attempt_started_at": None,
            "attempt_ended_at": None,
            "attempt_elapsed_seconds": None,
            "total_attempt_seconds": None,
        }
    started = current.get("started_at")
    ended = current.get("ended_at")
    attempt_elapsed = current.get("duration_seconds")
    running = job.get("state") == "RUNNING" and ended is None
    if attempt_elapsed is None:
        if ended:
            attempt_elapsed = _elapsed_seconds(started, ended)
        elif running:
            attempt_elapsed = _elapsed_seconds(started)
    total = 0
    for attempt in attempts:
        duration = attempt.get("duration_seconds")
        if duration is None:
            if attempt is current and running:
                duration = attempt_elapsed
            elif attempt.get("ended_at"):
                duration = _elapsed_seconds(attempt.get("started_at"), attempt.get("ended_at"))
        if isinstance(duration, int):
            total += duration
    return {
        "attempt_number": int(current.get("number") or len(attempts)),
        "attempt_started_at": started,
        "attempt_ended_at": ended,
        "attempt_elapsed_seconds": attempt_elapsed,
        "total_attempt_seconds": total,
    }


def status_payload(job: dict) -> dict:
    alive = worker_is_alive(job)
    started = job.get("started_at")
    ended = job.get("ended_at")
    if started:
        if job.get("state") == "RUNNING" or not ended:
            elapsed = _elapsed_seconds(started)
        else:
            elapsed = _elapsed_seconds(started, ended)
    else:
        elapsed = None
    attempt_info = _attempt_info(job)
    attempt_duration = job.get("attempt_duration_seconds")
    if attempt_duration is None:
        attempt_duration = attempt_info["attempt_elapsed_seconds"]
    criteria = job.get("acceptance_criteria") or []
    verification = job.get("verification") or {}
    pending = [
        criterion["id"]
        for criterion in criteria
        if criterion.get("required", True) and not (verification.get(criterion["id"]) or {}).get("verified")
    ]
    return {
        "id": job.get("id"),
        "title": job.get("title"),
        "state": job.get("state"),
        "repo": job.get("repo"),
        "branch": job.get("branch"),
        "started_at": started,
        "ended_at": job.get("ended_at"),
        "duration_seconds": job.get("duration_seconds"),
        "elapsed_seconds": elapsed,
        "attempt_duration_seconds": attempt_duration,
        "total_attempt_seconds": attempt_info["total_attempt_seconds"],
        "attempt_number": attempt_info["attempt_number"],
        "attempt_started_at": attempt_info["attempt_started_at"],
        "attempt_ended_at": attempt_info["attempt_ended_at"],
        "attempt_elapsed_seconds": attempt_info["attempt_elapsed_seconds"],
        "completion": job.get("completion"),
        "timeout_seconds": job.get("timeout_seconds"),
        "worker_pid": job.get("worker_pid"),
        "guard_pid": job.get("guard_pid"),
        "child_pid": job.get("child_pid"),
        "worker_alive": alive,
        "exit_code": job.get("exit_code"),
        "session_id": job.get("session_id"),
        "blocker": job.get("blocker"),
        "cancelled_at": job.get("cancelled_at"),
        "pending_criteria": pending,
        "issues": job.get("detected_issues") or [],
        "log_path": job.get("log_path"),
        "worker_log_path": job.get("worker_log_path"),
        "report_path": job.get("report_path"),
        "notifications": job.get("notifications") or [],
        "resume_count": job.get("resume_count"),
        "attempts": len(job.get("attempts") or []),
    }


def _format_seconds(value: int | None) -> str:
    if value is None:
        return "-"
    hours, remainder = divmod(max(0, int(value)), 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}h{minutes:02d}m{seconds:02d}s"
    if minutes:
        return f"{minutes}m{seconds:02d}s"
    return f"{seconds}s"


def _format_ms(value: object) -> str:
    try:
        number = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "-"
    try:
        return datetime.fromtimestamp(number / 1000, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (OverflowError, OSError, ValueError):
        return "-"


def render_status(job: dict) -> str:
    payload = status_payload(job)
    lines = [
        f"Job:      {payload['id']}",
        f"Title:    {payload['title']}",
        f"State:    {payload['state']}" + ("" if payload["state"] == "RUNNING" else ""),
        f"Repo:     {payload['repo']} ({payload['branch'] or 'detached'})",
        f"Started:  {payload['started_at'] or '-'}",
        f"Ended:    {payload['ended_at'] or '-'}",
        f"Elapsed:  total {_format_seconds(payload['elapsed_seconds'])} / "
        f"attempt {_format_seconds(payload['attempt_elapsed_seconds'])} / "
        f"timeout {_format_seconds(payload['timeout_seconds'])}",
        f"Attempt:  #{payload['attempt_number']} {payload['attempt_started_at'] or '-'} -> "
        f"{payload['attempt_ended_at'] or '-'}",
        f"PIDs:     worker={payload['worker_pid'] or '-'} guard={payload['guard_pid'] or '-'} child={payload['child_pid'] or '-'} alive={payload['worker_alive']}",
        f"Exit:     {payload['exit_code'] if payload['exit_code'] is not None else '-'}",
        f"Session:  {payload['session_id'] or '-'}",
    ]
    if payload["blocker"]:
        lines.append(f"Blocker:  {payload['blocker']}")
    if payload["pending_criteria"]:
        lines.append(f"Pending:  {', '.join(payload['pending_criteria'])}")
    if payload["issues"]:
        lines.append("Issues:")
        for issue in payload["issues"][:10]:
            suffix = " (recovered)" if issue.get("recovered") else ""
            lines.append(
                f"  - [{issue.get('severity')}] {issue.get('kind')}: "
                f"{issue.get('message')}{suffix}"
            )
    lines.append(f"Log:      {payload['log_path']}")
    lines.append(f"Report:   {payload['report_path']}")
    return "\n".join(lines)


def render_report(job: dict) -> str:
    payload = status_payload(job)
    criteria = job.get("acceptance_criteria") or []
    verification = job.get("verification") or {}
    lines = [
        f"# Dev job report: {job.get('title')}",
        "",
        f"- Job ID: `{job.get('id')}`",
        f"- State: **{job.get('state')}**",
        f"- Repository: `{job.get('repo')}`",
        f"- Branch: `{job.get('branch') or '(detached)'}`",
        f"- Agent profile: `{job.get('agent')}`",
        f"- Model: `{job.get('model')}`",
        f"- Started: {job.get('started_at') or '-'}",
        f"- Ended: {job.get('ended_at') or '-'}",
        f"- Duration (total job): {_format_seconds(payload['duration_seconds'])}",
        f"- Attempt: #{payload['attempt_number']} "
        f"{payload['attempt_started_at'] or '-'} -> {payload['attempt_ended_at'] or '-'}",
        f"- Duration (current/last attempt): {_format_seconds(payload['attempt_duration_seconds'])}",
        f"- Timeout per attempt: {_format_seconds(job.get('timeout_seconds'))}",
        f"- Guard exit code: {job.get('exit_code') if job.get('exit_code') is not None else '-'}",
        f"- Worker PID: {job.get('worker_pid') or '-'}",
        f"- Guard PID: {job.get('guard_pid') or '-'}",
        f"- OpenCode child PID/PGID: {job.get('child_pid') or '-'} / {job.get('child_pgid') or '-'}",
        f"- OpenCode session: `{job.get('session_id') or 'unknown'}`",
        f"- Resume count: {job.get('resume_count') or 0}",
        f"- Log: `{job.get('log_path')}`",
        f"- Worker log: `{job.get('worker_log_path')}`",
        "",
    ]
    if job.get("blocker"):
        lines.extend([f"**Blocker:** {job['blocker']}", ""])
    completion = job.get("completion")
    if isinstance(completion, dict) and completion:
        lines.extend(
            [
                "## Session completion evidence",
                "",
                f"- Session: `{completion.get('session_id') or job.get('session_id') or 'unknown'}`",
                f"- Final assistant message: `{completion.get('message_id') or '-'}` "
                f"(finish={completion.get('finish') or '-'})",
                f"- Finished at: {_format_ms(completion.get('finished_at_ms'))}",
                f"- Active tool calls at confirmation: {completion.get('active_tool_calls', 0)}",
                f"- Guard action: {completion.get('action') or '-'}",
                f"- Idle before stop: {completion.get('idle_seconds', '-')}s",
                "",
                "Session completion only means the agent turn ended without active tool calls.",
                "It is not acceptance; the criteria below are authoritative.",
                "",
            ]
        )
    lines.extend(["## Acceptance criteria", ""])
    if not criteria:
        lines.append("No acceptance criteria were recorded. This job cannot succeed.")
    for criterion in criteria:
        result = verification.get(criterion["id"], {})
        status = "PASS" if result.get("verified") else ("PENDING" if criterion.get("kind") == "manual" else "FAIL")
        lines.append(f"- [{status}] `{criterion['id']}` {criterion.get('label')}")
        if criterion.get("command"):
            lines.append(f"  - command: `{criterion['command']}`")
        if result.get("exit_code") is not None:
            lines.append(f"  - exit: {result['exit_code']}")
        if result.get("skipped"):
            lines.append("  - skipped by the harness")
        if result.get("detail"):
            lines.append(f"  - detail: {result['detail']}")
    lines.extend(["", "## Detected issues", ""])
    issues = job.get("detected_issues") or []
    if not issues:
        lines.append("None detected.")
    for issue in issues:
        lines.append(
            f"- `{issue.get('kind')}` ({issue.get('severity')}): {issue.get('message')}"
        )
        if issue.get("excerpt"):
            lines.append(f"  - `{issue['excerpt']}`")
        if issue.get("recovered"):
            lines.append(f"  - recovered: {issue.get('recovery') or 'later successful work'}")
    lines.extend(["", "## Git snapshot", ""])
    snapshot = job.get("git") or {}
    if snapshot:
        lines.append(f"- Branch: `{snapshot.get('branch') or '-'}`")
        lines.append(f"- HEAD: `{snapshot.get('head') or '-'}`")
        lines.append(f"- Dirty: {snapshot.get('dirty')}")
        if snapshot.get("diffstat"):
            lines.extend(["", "```text", str(snapshot["diffstat"]), "```"])
    else:
        lines.append("No Git snapshot available.")
    lines.extend(["", "## Notifications", ""])
    notifications = job.get("notifications") or []
    if not notifications:
        lines.append("None recorded.")
    for item in notifications:
        lines.append(
            f"- {item.get('at')} state={item.get('state')} sent={item.get('sent')} reason={item.get('reason')}"
        )
    lines.extend(
        [
            "",
            "## Acceptance rule",
            "",
            "OpenCode exit code 0 alone is never success. This report is authoritative only",
            "when every required acceptance criterion is verified, no blocking/failure",
            "detector fired and the guarded process did not time out.",
            "",
        ]
    )
    return "\n".join(lines)


def write_report(job: dict) -> Path:
    path = job_dir(job["id"]) / REPORT
    ensure_private_dir(path.parent)
    path.write_text(render_report(job), encoding="utf-8")
    chmod_private(path)
    job["report_path"] = str(path)
    return path
