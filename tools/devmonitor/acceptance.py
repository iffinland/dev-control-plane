"""Isolated P3 live Telegram acceptance harness for the Qortium Dev Monitor.

The harness exercises the *real* Telegram bot and the real monitor router while
replacing every backend that could start a development job, spend model budget
or touch a production project:

* a throw-away Git repository under a private work directory;
* a temporary project registry containing only one synthetic project;
* a temporary monitor configuration derived from a *copy* of the owner config;
* temporary monitor and Workflow v3 state directories;
* a deterministic fake ``dev`` CLI that never invokes OpenCode and never signals
  a process;
* a recording Telegram API wrapper that journals real callback labels, message
  IDs and timestamps for evidence.

The harness never edits the owner Telegram configuration, the production
registry, the live monitor state or the running Qortium node. It fails closed if
the live monitor is running, if the source configuration is not control mode, or
if any isolation invariant cannot be established.

The operator runs the live part explicitly. This module does not send a Telegram
message by itself; only an explicit ``run`` invocation starts the isolated
poller after the live monitor has been stopped through its documented path.
"""

from __future__ import annotations

import copy
import json
import os
import shutil
import sqlite3
import stat
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from devjob import store

from .config import (
    CONTROL_PLANE_ROOT,
    ConfigError,
    load_monitor_config,
    resolve_state_dir,
)
from .redact import redact_text, sanitize_control
from .service import (
    AlreadyRunning,
    MonitorService,
    MonitorShutdown,
    install_shutdown_handlers,
    monitor_running,
    restore_signal_handlers,
)

SCHEMA_VERSION = 1
KIND = "workflow-v3-p3-telegram-live-acceptance"
MARKER_FILENAME = ".p3-live-acceptance"
SYNTHETIC_PROJECT_ID = "synthetic/p3-live-acceptance"
SYNTHETIC_MARKER = "P3-TELEGRAM-LIVE-ACCEPTANCE"
SYNTHETIC_TITLE = "[SYNTHETIC] P3 Telegram live acceptance"
SYNTHETIC_REMOTE = "https://github.com/synthetic/p3-live-acceptance.git"
DEFAULT_INSTRUCTION = (
    "P3-TELEGRAM-LIVE-ACCEPTANCE: update the acceptance notes only; do not expand "
    "scope."
)
REQUIRED_BUTTONS = ("Queue instruction", "Cancel job")
CANCEL_CONFIRM_LABEL = "Confirm: Cancel running job"
RESUME_CONFIRM_LABEL = "Confirm: Resume job"
EVIDENCE_FILENAME = "telegram-evidence.json"
JOURNAL_FILENAME = "telegram-journal.jsonl"
REPORT_FILENAME = "report.json"


class AcceptanceError(RuntimeError):
    """The acceptance harness refused or could not prove a safe outcome."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _read_json(path: str | Path) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise AcceptanceError(f"cannot read {Path(path).name}: {exc.__class__.__name__}") from exc
    except json.JSONDecodeError as exc:
        raise AcceptanceError(f"{Path(path).name} is not valid JSON") from exc


def _write_json(path: str | Path, payload: object, *, mode: int = 0o600) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        os.chmod(temporary, mode)
        os.replace(temporary, target)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _write_text(path: str | Path, text: str, *, mode: int = 0o600) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(text, encoding="utf-8")
        os.chmod(temporary, mode)
        os.replace(temporary, target)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _sha256_file(path: str | Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _ensure_secure_file(path: Path) -> None:
    try:
        info = path.stat()
    except OSError as exc:
        raise AcceptanceError(
            f"source config cannot be inspected: {exc.__class__.__name__}"
        ) from exc
    if not stat.S_ISREG(info.st_mode):
        raise AcceptanceError("source config must be a regular file")
    if stat.S_IMODE(info.st_mode) & (stat.S_IRWXG | stat.S_IRWXO):
        raise AcceptanceError(
            "source config is group/world accessible; set mode 0600 before running"
        )


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except (OSError, ValueError):
        return False


def _git_env() -> dict[str, str]:
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", "/tmp"),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_AUTHOR_NAME": "P3 Live Acceptance",
        "GIT_AUTHOR_EMAIL": "p3-live-acceptance@example.invalid",
        "GIT_COMMITTER_NAME": "P3 Live Acceptance",
        "GIT_COMMITTER_EMAIL": "p3-live-acceptance@example.invalid",
        "LC_ALL": "C",
    }
    return env


def _run_git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
            shell=False,
            env=_git_env(),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AcceptanceError(
            f"git could not run: {exc.__class__.__name__}"
        ) from exc


def _init_git_repo(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=False)
    result = _run_git(repo, "init")
    if result.returncode != 0:
        raise AcceptanceError("temporary Git repository could not be initialised")
    for key, value in (
        ("user.name", "P3 Live Acceptance"),
        ("user.email", "p3-live-acceptance@example.invalid"),
    ):
        configured = _run_git(repo, "config", key, value)
        if configured.returncode != 0:
            raise AcceptanceError("temporary Git identity could not be configured")
    _write_text(
        repo / "README.md",
        "# Synthetic P3 live acceptance repository\n\n"
        f"This repository is a temporary fixture for the {SYNTHETIC_MARKER}\n"
        "Telegram acceptance harness. It is not a development project and must be\n"
        "deleted by the harness cleanup command.\n",
        mode=0o600,
    )
    result = _run_git(repo, "symbolic-ref", "HEAD", "refs/heads/main")
    if result.returncode != 0:
        raise AcceptanceError("temporary Git branch could not be set")
    for args in (("add", "README.md"), ("commit", "-m", "synthetic acceptance fixture")):
        completed = _run_git(repo, *args)
        if completed.returncode != 0:
            raise AcceptanceError("temporary Git commit could not be created")
    remote = _run_git(repo, "remote", "add", "origin", SYNTHETIC_REMOTE)
    if remote.returncode != 0:
        raise AcceptanceError("temporary Git remote could not be configured")


def _registry_text(repo: Path, docs: Path) -> str:
    return (
        "# Synthetic P3 acceptance project registry\n\n"
        "This file is generated inside the isolated acceptance work directory. It is\n"
        "not the production registry and is deleted by the harness cleanup command.\n\n"
        "## Registered projects\n\n"
        "| ID | Platform | Verified local path | Project-level `AGENTS.md` | Canonical context | Central report root | Git remote | GitHub repository | Development branch pattern | Automatic push |\n"
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
        f"| `{SYNTHETIC_PROJECT_ID}` | Synthetic | `{repo}` | No; synthetic fixture | None | `{docs}/` | "
        f"`origin` | `synthetic/p3-live-acceptance` | `agent/*` | `no` |\n"
    )


def _fake_job(job_id: str, repo: Path) -> dict:
    stamp = _utc_now()
    return {
        "id": job_id,
        "title": SYNTHETIC_TITLE,
        "state": "RUNNING",
        "repo": str(repo),
        "branch": "main",
        "started_at": stamp,
        "ended_at": None,
        "elapsed_seconds": 0,
        "attempt_elapsed_seconds": 0,
        "timeout_seconds": 3600,
        "attempt_number": 1,
        "attempt_started_at": stamp,
        "attempt_ended_at": None,
        "worker_pid": 0,
        "guard_pid": 0,
        "child_pid": 0,
        "worker_alive": True,
        "session_id": "ses_p3_live_acceptance_synthetic",
        "blocker": "",
        "pending_criteria": ["SYNTHETIC"],
        "issues": [],
        "resume_count": 0,
        "attempts": [{"number": 1}],
        "acceptance_criteria": [
            {
                "id": "SYNTHETIC",
                "kind": "manual",
                "label": "Synthetic acceptance fixture; never a development success",
                "required": False,
            }
        ],
        "notifications_enabled": False,
        "notifications": [],
        "prompt": (
            "Synthetic P3 Telegram acceptance fixture. It never starts OpenCode, "
            "never spends model budget and must never be reported as a development "
            "success."
        ),
        "agent": "synthetic-fake-worker",
        "model": "none",
        "synthetic": True,
        "synthetic_marker": SYNTHETIC_MARKER,
    }


def _job_dir(job_state: Path, job_id: str) -> Path:
    return job_state / "jobs" / job_id


def _read_job(job_state: Path, job_id: str) -> dict:
    path = _job_dir(job_state, job_id) / "job.json"
    payload = _read_json(path)
    if not isinstance(payload, dict) or payload.get("id") != job_id:
        raise AcceptanceError("synthetic job record is malformed")
    return payload


def _list_job_records(job_state: Path) -> list[dict]:
    jobs_root = job_state / "jobs"
    if not jobs_root.is_dir():
        return []
    records: list[dict] = []
    for directory in sorted(jobs_root.iterdir()):
        if not directory.is_dir():
            continue
        path = directory / "job.json"
        if not path.is_file():
            continue
        payload = _read_json(path)
        if isinstance(payload, dict):
            records.append(payload)
    return records


def _read_events(job_state: Path, job_id: str) -> list[dict]:
    path = _job_dir(job_state, job_id) / "events.jsonl"
    if not path.is_file():
        return []
    events: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            events.append(payload)
    return events


def _read_invocations(job_state: Path) -> list[dict]:
    path = job_state / "fake_invocations.jsonl"
    if not path.is_file():
        return []
    records: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            records.append(payload)
    return records


def _open_monitor_db(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise AcceptanceError("monitor state database is missing")
    try:
        return sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        raise AcceptanceError(
            f"monitor state database cannot be opened: {exc.__class__.__name__}"
        ) from exc


def _owner_messages(path: Path, job_id: str) -> list[dict]:
    connection = _open_monitor_db(path)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            "SELECT message_id, body, delivery_state, delivered_attempt, "
            "last_error_redacted FROM owner_messages WHERE job_id = ? "
            "ORDER BY created_at",
            (job_id,),
        ).fetchall()
    except sqlite3.Error as exc:
        raise AcceptanceError(
            f"owner message state cannot be read: {exc.__class__.__name__}"
        ) from exc
    finally:
        connection.close()
    return [dict(row) for row in rows]


def _read_journal(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    entries: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            entries.append(payload)
    return entries


def _button_labels(markup: object) -> list[str]:
    labels: list[str] = []
    if not isinstance(markup, dict):
        return labels
    for row in markup.get("inline_keyboard") or []:
        if not isinstance(row, list):
            continue
        for item in row:
            if isinstance(item, dict) and item.get("text"):
                labels.append(str(item["text"]))
    return labels


def _button_map(markup: object) -> dict[str, str]:
    mapping: dict[str, str] = {}
    if not isinstance(markup, dict):
        return mapping
    for row in markup.get("inline_keyboard") or []:
        if not isinstance(row, list):
            continue
        for item in row:
            if isinstance(item, dict) and item.get("callback_data") and item.get("text"):
                mapping[str(item["callback_data"])] = str(item["text"])
    return mapping


class RecordingTelegramApi:
    """Thin journaling wrapper around the real or fake Telegram API.

    The wrapper records the observed button labels, Telegram message IDs,
    update IDs and sanitized text. It never records the bot token or the raw
    callback payload; callback labels are resolved from the keyboard that the
    monitor previously sent, which makes the evidence precise without copying
    opaque nonces into a report.
    """

    def __init__(
        self,
        api: object,
        journal_path: str | Path,
        *,
        secrets: Sequence[str] = (),
        instruction_token: str = SYNTHETIC_MARKER,
    ) -> None:
        self._api = api
        self.journal_path = Path(journal_path)
        self.secrets = tuple(secrets)
        self.instruction_token = instruction_token
        self._labels: dict[str, str] = {}

    def _record(self, payload: dict[str, Any]) -> None:
        record = {"ts": _utc_now(), **payload}
        line = json.dumps(record, sort_keys=True) + "\n"
        descriptor = os.open(
            self.journal_path,
            os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW | os.O_CLOEXEC,
            0o600,
        )
        try:
            os.write(descriptor, line.encode("utf-8"))
        finally:
            os.close(descriptor)

    def _safe_text(self, text: object, limit: int = 500) -> str:
        cleaned = sanitize_control("" if text is None else str(text))
        return redact_text(cleaned, self.secrets, limit)

    def _remember(self, markup: object) -> list[str]:
        mapping = _button_map(markup)
        self._labels.update(mapping)
        return _button_labels(markup)

    def get_updates(self, offset: int, timeout: float, limit: int = 100) -> list[dict]:
        updates = self._api.get_updates(offset, timeout, limit)
        for update in updates or []:
            self._record_update(update)
        return updates

    def _record_update(self, update: object) -> None:
        if not isinstance(update, dict):
            return
        callback = update.get("callback_query")
        if isinstance(callback, dict):
            data = str(callback.get("data") or "")
            message = callback.get("message") if isinstance(callback.get("message"), dict) else {}
            self._record(
                {
                    "kind": "callback",
                    "update_id": update.get("update_id"),
                    "callback_query_id": callback.get("id"),
                    "message_id": message.get("message_id"),
                    "label": self._labels.get(data, ""),
                    "head": data.split(":", 1)[0],
                }
            )
            return
        message = update.get("message")
        if isinstance(message, dict):
            text = str(message.get("text") or "")
            self._record(
                {
                    "kind": "message",
                    "update_id": update.get("update_id"),
                    "message_id": message.get("message_id"),
                    "is_command": text.strip().startswith("/"),
                    "contains_instruction_token": self.instruction_token in text,
                    "text": self._safe_text(text),
                }
            )

    def send_message(self, chat_id: int, text: str, reply_markup: dict | None = None) -> dict:
        result = self._api.send_message(chat_id, text, reply_markup)
        labels = self._remember(reply_markup)
        self._record(
            {
                "kind": "outbound",
                "method": "send_message",
                "message_id": result.get("message_id") if isinstance(result, dict) else None,
                "button_labels": labels,
                "text": self._safe_text(text),
            }
        )
        return result

    def edit_message_text(
        self, chat_id: int, message_id: int, text: str, reply_markup: dict | None = None
    ) -> dict:
        result = self._api.edit_message_text(chat_id, message_id, text, reply_markup)
        labels = self._remember(reply_markup)
        self._record(
            {
                "kind": "outbound",
                "method": "edit_message_text",
                "message_id": message_id,
                "button_labels": labels,
                "text": self._safe_text(text),
            }
        )
        return result

    def answer_callback_query(self, callback_query_id: str, text: str | None = None) -> bool:
        result = self._api.answer_callback_query(callback_query_id, text)
        self._record(
            {
                "kind": "callback_ack",
                "callback_query_id": callback_query_id,
                "text": self._safe_text(text, 120),
            }
        )
        return result

    def __getattr__(self, name: str) -> Any:
        return getattr(self._api, name)


FAKE_DEV_TEMPLATE = r'''#!/usr/bin/env python3
"""Deterministic fake Workflow v3 CLI for the isolated P3 acceptance harness.

It reads and writes only DEV_CONTROL_PLANE_STATE. It never starts OpenCode,
never contacts Telegram, never creates a real job and never signals a process.
Synthetic jobs are forced to RUNNING or CANCELLED; this CLI has no SUCCESS path.
"""

import json
import os
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

SYNTHETIC_MARKER = "P3-TELEGRAM-LIVE-ACCEPTANCE"


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def state_root():
    value = os.environ.get("DEV_CONTROL_PLANE_STATE")
    if not value:
        print("fake dev: DEV_CONTROL_PLANE_STATE is required", file=sys.stderr)
        sys.exit(2)
    return Path(value)


def jobs_path():
    return state_root() / "fake_jobs.json"


def load_jobs():
    path = jobs_path()
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix="." + path.name + ".", suffix=".tmp", dir=str(path.parent)
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


def save_jobs(jobs):
    atomic_json(jobs_path(), jobs)


def job_dir(job_id):
    return state_root() / "jobs" / job_id


def write_job(job):
    directory = job_dir(job["id"])
    directory.mkdir(parents=True, exist_ok=True)
    os.chmod(directory, 0o700)
    atomic_json(directory / "job.json", job)
    return directory


def append_event(job, event, detail=""):
    directory = write_job(job)
    payload = {"ts": now(), "event": event, "detail": detail}
    with (directory / "events.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")
    os.chmod(directory / "events.jsonl", 0o600)


def record(args, stdin_text=""):
    path = state_root() / "fake_invocations.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps({"args": args, "stdin": stdin_text, "ts": now()},
                       sort_keys=True) + "\n"
        )
    os.chmod(path, 0o600)


def option(name, default=None):
    args = sys.argv[1:]
    return args[args.index(name) + 1] if name in args else default


def synthetic(job):
    return bool(job.get("synthetic")) and job.get("synthetic_marker") == SYNTHETIC_MARKER


def require_job(jobs, job_id):
    job = jobs.get(job_id)
    if job is None:
        print("fake dev: job not found", file=sys.stderr)
        sys.exit(2)
    if not synthetic(job):
        print("fake dev: refusing a non-synthetic job", file=sys.stderr)
        sys.exit(2)
    return job


def main():
    args = sys.argv[1:]
    jobs = load_jobs()
    if args[:1] == ["status"]:
        if "--all" in args:
            print(json.dumps(list(jobs.values())))
        else:
            job_id = args[1]
            print(json.dumps(require_job(jobs, job_id)))
        return 0
    if args[:1] == ["cancel"]:
        record(args)
        job = require_job(jobs, args[1])
        if job.get("state") != "RUNNING" or not job.get("worker_alive"):
            print("fake dev: only a RUNNING synthetic job can be cancelled",
                  file=sys.stderr)
            return 2
        job["state"] = "CANCELLED"
        job["blocker"] = "synthetic acceptance cancellation"
        job["worker_alive"] = False
        job["ended_at"] = now()
        job["attempt_ended_at"] = now()
        if job.get("attempts"):
            job["attempts"][-1]["ended_at"] = now()
        jobs[job["id"]] = job
        save_jobs(jobs)
        write_job(job)
        append_event(job, "cancel_requested", "synthetic acceptance; no process signalled")
        append_event(job, "cancel_observed", "attempt=1")
        append_event(job, "finished", "state=CANCELLED exit=0")
        print(json.dumps({
            "cancel_status": "cancelled",
            "detail": "synthetic acceptance cancellation; no process signalled",
            "job": job,
        }, sort_keys=True))
        return 0
    if args[:1] == ["resume"]:
        job_id = args[1]
        stdin_text = sys.stdin.read() if "--prompt-file" in args else ""
        record(args, stdin_text)
        job = require_job(jobs, job_id)
        job["state"] = "RUNNING"
        job["ended_at"] = None
        job["attempt_ended_at"] = None
        job["blocker"] = ""
        job["worker_alive"] = True
        job["resume_count"] = int(job.get("resume_count") or 0) + 1
        job["attempt_number"] = int(job.get("attempt_number") or 0) + 1
        job["attempt_started_at"] = now()
        job["attempts"] = list(job.get("attempts") or []) + [
            {"number": job["attempt_number"]}
        ]
        jobs[job["id"]] = job
        save_jobs(jobs)
        write_job(job)
        append_event(job, "resume_requested",
                     "resume_count=%d" % job["resume_count"])
        append_event(job, "attempt_started",
                     "attempt=%d resume=True" % job["attempt_number"])
        print(json.dumps(job, sort_keys=True))
        return 0
    if args[:1] == ["report"]:
        job = require_job(jobs, args[1])
        directory = write_job(job)
        report = directory / "report.md"
        report.write_text(
            "# Synthetic P3 acceptance report\n\n"
            "This is a synthetic fixture. It is never a development success.\n",
            encoding="utf-8",
        )
        os.chmod(report, 0o600)
        print(json.dumps({"job": job, "report_path": str(report)}, sort_keys=True))
        return 0
    if args[:1] == ["start"]:
        print("fake dev: start is disabled in the acceptance harness", file=sys.stderr)
        return 2
    print("fake dev: unsupported command", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
'''


@dataclass
class LiveAcceptanceHarness:
    root: Path
    manifest: dict
    monitor_running_func: Any = monitor_running

    # ---- preparation ---------------------------------------------------------
    @classmethod
    def prepare(
        cls,
        root: str | Path,
        *,
        source_config: str | Path,
        live_state_dir: str | Path | None = None,
        instruction: str = DEFAULT_INSTRUCTION,
        monitor_running_func: Any = monitor_running,
    ) -> "LiveAcceptanceHarness":
        target = Path(root).expanduser()
        if target.exists() and any(target.iterdir()):
            raise AcceptanceError("acceptance work directory must be empty")
        resolved = target.resolve()
        for forbidden in (store.state_root().resolve(), CONTROL_PLANE_ROOT.resolve()):
            if _is_within(resolved, forbidden):
                raise AcceptanceError(
                    "acceptance work directory must stay outside production state "
                    "and the control-plane checkout"
                )

        config_path = Path(source_config).expanduser()
        try:
            config_path = config_path.resolve(strict=True)
        except OSError as exc:
            raise AcceptanceError(
                f"source config does not exist: {exc.__class__.__name__}"
            ) from exc
        _ensure_secure_file(config_path)
        data = _read_json(config_path)
        if not isinstance(data, dict):
            raise AcceptanceError("source config must be a JSON object")
        monitor = data.get("monitor")
        if not isinstance(monitor, dict):
            raise AcceptanceError("source config is missing the monitor object")
        if str(monitor.get("mode", "read_only")) != "control":
            raise AcceptanceError(
                "source monitor mode must be 'control' for queue/cancel acceptance"
            )
        if monitor.get("queue_owner_messages") is False:
            raise AcceptanceError(
                "source monitor has queue_owner_messages disabled"
            )
        token = data.get("bot_token") or os.environ.get("DEV_TELEGRAM_BOT_TOKEN")
        if not isinstance(token, str) or not token.strip():
            raise AcceptanceError("source config has no bot token")
        registry_value = monitor.get("registry_path")
        source_registry = Path(
            registry_value or (CONTROL_PLANE_ROOT / "PROJECT-REGISTRY.md")
        ).expanduser()
        try:
            source_registry = source_registry.resolve(strict=True)
        except OSError as exc:
            raise AcceptanceError(
                f"source project registry does not exist: {exc.__class__.__name__}"
            ) from exc

        live_state = Path(
            live_state_dir if live_state_dir is not None else resolve_state_dir(None)
        ).expanduser().resolve()
        if monitor_running_func(live_state):
            raise AcceptanceError(
                "the production monitor is running; stop it through its documented "
                "path before preparing a live acceptance fixture"
            )

        target.mkdir(parents=True, exist_ok=True)
        os.chmod(target, 0o700)
        projects = target / "projects"
        repo = projects / "p3-live-acceptance"
        docs = target / "docs"
        job_state = target / "job-state"
        monitor_state = target / "monitor"
        evidence_dir = target / "evidence"
        for directory in (projects, docs, job_state, monitor_state, evidence_dir):
            directory.mkdir(parents=True, exist_ok=False)
            os.chmod(directory, 0o700)
        _init_git_repo(repo)

        registry_path = target / "PROJECT-REGISTRY.md"
        _write_text(registry_path, _registry_text(repo, docs))

        temp_config = copy.deepcopy(data)
        temp_config["bot_token"] = token.strip()
        temp_monitor = temp_config.setdefault("monitor", {})
        temp_monitor["mode"] = "control"
        temp_monitor["registry_path"] = str(registry_path)
        temp_monitor["allowed_repo_roots"] = [str(projects)]
        temp_monitor["docs_roots"] = [str(docs)]
        temp_monitor["poll_timeout_seconds"] = 1
        temp_monitor["lifecycle_poll_seconds"] = 1
        temp_monitor["terminal_grace_seconds"] = 0
        config_target = target / "telegram.json"
        _write_json(config_target, temp_config, mode=0o600)

        try:
            checked = load_monitor_config(
                config_target,
                environ={},
                state_dir=monitor_state,
                require_secure=True,
            )
        except ConfigError as exc:
            raise AcceptanceError(f"temporary monitor config is invalid: {exc}") from exc
        if not checked.control_enabled:
            raise AcceptanceError("temporary monitor config is not in control mode")
        if not checked.queue_owner_messages:
            raise AcceptanceError("temporary monitor config has queuing disabled")
        if checked.state_dir.resolve() != monitor_state.resolve():
            raise AcceptanceError("temporary monitor state isolation failed")

        fake_dev = target / "fake_dev.py"
        _write_text(fake_dev, FAKE_DEV_TEMPLATE, mode=0o700)

        job_id = f"{_utc_stamp()}-p3-live-acceptance-{uuid.uuid4().hex[:8]}"
        job = _fake_job(job_id, repo)
        _write_json(job_state / "fake_jobs.json", {job_id: job}, mode=0o600)
        write_job = _job_dir(job_state, job_id)
        write_job.mkdir(parents=True, exist_ok=False)
        os.chmod(write_job, 0o700)
        _write_json(write_job / "job.json", job, mode=0o600)
        with (write_job / "events.jsonl").open("w", encoding="utf-8") as handle:
            for event, detail in (
                ("worker_started", "pid=0 synthetic"),
                ("attempt_started", "attempt=1 resume=False"),
            ):
                handle.write(
                    json.dumps(
                        {"ts": _utc_now(), "event": event, "detail": detail},
                        sort_keys=True,
                    )
                    + "\n"
                )
        os.chmod(write_job / "events.jsonl", 0o600)

        journal = evidence_dir / JOURNAL_FILENAME
        _write_text(journal, "", mode=0o600)
        evidence_path = evidence_dir / EVIDENCE_FILENAME
        _write_json(
            evidence_path,
            {
                "schema": SCHEMA_VERSION,
                "job_id": job_id,
                "synthetic_marker": SYNTHETIC_MARKER,
                "operator": "UNRECORDED",
                "started_at_utc": "UNRECORDED",
                "finished_at_utc": "UNRECORDED",
                "no_success_observed": "UNRECORDED",
                "production_untouched": "UNRECORDED",
                "qortium_unchanged": "UNRECORDED",
                "notes": "",
            },
            mode=0o600,
        )
        _write_text(
            evidence_dir / "TELEGRAM-EVIDENCE.md",
            _evidence_instructions(job_id, instruction),
            mode=0o600,
        )

        manifest = {
            "schema": SCHEMA_VERSION,
            "kind": KIND,
            "synthetic": True,
            "synthetic_marker": SYNTHETIC_MARKER,
            "created_at": _utc_now(),
            "job_id": job_id,
            "project_id": SYNTHETIC_PROJECT_ID,
            "instruction": instruction,
            "instruction_token": SYNTHETIC_MARKER,
            "paths": {
                "root": str(target),
                "repo": str(repo),
                "docs": str(docs),
                "registry": str(registry_path),
                "config": str(config_target),
                "job_state": str(job_state),
                "monitor_state": str(monitor_state),
                "fake_dev": str(fake_dev),
                "evidence": str(evidence_dir),
                "journal": str(journal),
                "telegram_evidence": str(evidence_path),
                "report": str(evidence_dir / REPORT_FILENAME),
            },
            "source": {
                "config": str(config_path),
                "config_sha256": _sha256_file(config_path),
                "registry": str(source_registry),
                "registry_sha256": _sha256_file(source_registry),
                "live_state_dir": str(live_state),
            },
            "isolation": {
                "production_config_modified": False,
                "production_registry_modified": False,
                "production_job_state_used": False,
                "live_monitor_was_running": False,
            },
        }
        _write_json(target / "manifest.json", manifest, mode=0o600)
        _write_text(
            target / MARKER_FILENAME,
            KIND + "\n" + SYNTHETIC_MARKER + "\n",
            mode=0o600,
        )
        return cls(target.resolve(), manifest, monitor_running_func)

    @classmethod
    def load(
        cls, root: str | Path, *, monitor_running_func: Any = monitor_running
    ) -> "LiveAcceptanceHarness":
        target = Path(root).expanduser().resolve()
        marker = target / MARKER_FILENAME
        if not marker.is_file():
            raise AcceptanceError("not an acceptance work directory: marker missing")
        manifest = _read_json(target / "manifest.json")
        if not isinstance(manifest, dict) or manifest.get("kind") != KIND:
            raise AcceptanceError("acceptance manifest is malformed")
        return cls(target, manifest, monitor_running_func)

    # ---- shared checks -------------------------------------------------------
    @property
    def job_state(self) -> Path:
        return Path(self.manifest["paths"]["job_state"])

    @property
    def monitor_state(self) -> Path:
        return Path(self.manifest["paths"]["monitor_state"])

    @property
    def job_id(self) -> str:
        return str(self.manifest["job_id"])

    def _check_source_unchanged(self) -> None:
        source = self.manifest.get("source") or {}
        config_path = Path(str(source.get("config") or ""))
        registry_path = Path(str(source.get("registry") or ""))
        if not config_path.is_file():
            raise AcceptanceError("source config disappeared during acceptance")
        if _sha256_file(config_path) != source.get("config_sha256"):
            raise AcceptanceError(
                "source Telegram config changed during acceptance; re-prepare"
            )
        if not registry_path.is_file():
            raise AcceptanceError("source project registry disappeared during acceptance")
        if _sha256_file(registry_path) != source.get("registry_sha256"):
            raise AcceptanceError(
                "production project registry changed during acceptance; re-prepare"
            )

    def _check_live_monitor_free(self) -> None:
        if self.monitor_running_func(self.monitor_state):
            raise AcceptanceError(
                "the isolated acceptance monitor is already running for this work dir"
            )
        live_state = Path(str((self.manifest.get("source") or {}).get("live_state_dir") or ""))
        if live_state and self.monitor_running_func(live_state):
            raise AcceptanceError(
                "the production monitor is running; stop it before starting the "
                "isolated acceptance poller"
            )

    # ---- live run ------------------------------------------------------------
    def _load_config(self):
        paths = self.manifest["paths"]
        previous_state = os.environ.get("DEV_CONTROL_PLANE_STATE")
        previous_token = os.environ.pop("DEV_TELEGRAM_BOT_TOKEN", None)
        previous_chat = os.environ.pop("DEV_TELEGRAM_CHAT_ID", None)
        os.environ["DEV_CONTROL_PLANE_STATE"] = paths["job_state"]
        try:
            config = load_monitor_config(
                paths["config"],
                environ=None,
                state_dir=paths["monitor_state"],
                require_secure=True,
            )
        except ConfigError as exc:
            raise AcceptanceError(f"acceptance monitor config is invalid: {exc}") from exc
        finally:
            if previous_state is None:
                os.environ.pop("DEV_CONTROL_PLANE_STATE", None)
            else:
                os.environ["DEV_CONTROL_PLANE_STATE"] = previous_state
            if previous_token is not None:
                os.environ["DEV_TELEGRAM_BOT_TOKEN"] = previous_token
            if previous_chat is not None:
                os.environ["DEV_TELEGRAM_CHAT_ID"] = previous_chat
        if not config.control_enabled:
            raise AcceptanceError("acceptance monitor config is not in control mode")
        if not config.queue_owner_messages:
            raise AcceptanceError("acceptance monitor config has queuing disabled")
        if config.state_dir.resolve() != self.monitor_state.resolve():
            raise AcceptanceError("acceptance monitor state isolation failed")
        if Path(config.job_state_root).resolve() != self.job_state.resolve():
            raise AcceptanceError("acceptance job state isolation failed")
        return config

    def _live_monitor_offset(self) -> int:
        """Read the production monitor's next-update offset without writing it."""

        live_state = Path(str((self.manifest.get("source") or {}).get("live_state_dir") or ""))
        database = live_state / "monitor.db"
        if not database.is_file():
            raise AcceptanceError(
                "production monitor state is missing; cannot prove a safe Telegram "
                "update offset for the isolated poller"
            )
        connection = _open_monitor_db(database)
        connection.row_factory = sqlite3.Row
        try:
            row = connection.execute(
                "SELECT value FROM meta WHERE key = 'update_offset'"
            ).fetchone()
        except sqlite3.Error as exc:
            raise AcceptanceError(
                f"production monitor offset cannot be read: {exc.__class__.__name__}"
            ) from exc
        finally:
            connection.close()
        try:
            return max(0, int((row or {})["value"]))
        except (TypeError, ValueError, KeyError, IndexError):
            return 0

    def _build_service(self, config, *, api=None, timings=None):
        from dev_monitor import _build_components
        from .jobs import JobFacade
        jobs = JobFacade(config.job_state_root, dev_script=self.manifest["paths"]["fake_dev"])
        if api is None:
            from .api import TelegramApi

            api = TelegramApi(
                config.bot_token,
                base_url=config.api_base,
                timeout_seconds=config.request_timeout_seconds,
                document_timeout_seconds=config.document_timeout_seconds,
            )
        recording = RecordingTelegramApi(
            api,
            self.manifest["paths"]["journal"],
            secrets=config.secrets,
            instruction_token=self.manifest["instruction_token"],
        )
        state, recording, _registry, _documents, _jobs, router, resolved_timings = (
            _build_components(config, timings=timings, api=recording, jobs=jobs)
        )
        service = MonitorService(
            config,
            recording,
            state,
            router,
            lifecycle=getattr(router, "lifecycle", None),
            log=lambda message: print(f"acceptance: {message}", file=sys.stderr),
            timings=resolved_timings,
        )
        return service, state, config, recording, router, jobs

    def run(
        self,
        *,
        timeout_seconds: float = 900.0,
        expect_resume: bool = False,
        confirm_live: bool = False,
        api=None,
        sleep=time.sleep,
    ) -> dict:
        self._check_source_unchanged()
        self._check_live_monitor_free()
        config = self._load_config()
        if api is None:
            if not confirm_live:
                raise AcceptanceError(
                    "refusing to start a live Telegram poller without "
                    "--confirm-live-telegram"
                )
            from .api import TelegramApi

            api = TelegramApi(
                config.bot_token,
                base_url=config.api_base,
                timeout_seconds=config.request_timeout_seconds,
                document_timeout_seconds=config.document_timeout_seconds,
            )
            try:
                me = api.get_me()
                webhook = api.get_webhook_info()
            except Exception as exc:  # noqa: BLE001
                raise AcceptanceError(
                    f"Telegram preflight failed: {exc.__class__.__name__}"
                ) from exc
            if not isinstance(me, dict) or me.get("is_bot") is not True:
                raise AcceptanceError("Telegram preflight did not identify a bot")
            if str((webhook or {}).get("url") or ""):
                raise AcceptanceError(
                    "a Telegram webhook is configured; clear it explicitly before "
                    "long polling"
                )
            live_offset = self._live_monitor_offset()
            try:
                pending = api.get_updates(live_offset, 0.0, 100)
            except Exception as exc:  # noqa: BLE001
                raise AcceptanceError(
                    f"Telegram pending-update check failed: {exc.__class__.__name__}"
                ) from exc
            if pending:
                raise AcceptanceError(
                    "pending Telegram updates exist; let the production monitor drain "
                    "them before stopping, then retry. No update was processed."
                )
        else:
            live_offset = None
        service, state, _config, _api, _router, _jobs = self._build_service(
            config, api=api
        )
        if live_offset is not None:
            state.set_offset(live_offset)
        previous = install_shutdown_handlers(service) if api is None else {}
        deadline = time.monotonic() + max(30.0, float(timeout_seconds))
        observed = "RUNNING"
        try:
            while True:
                if time.monotonic() > deadline:
                    raise AcceptanceError(
                        "timed out before the synthetic job was cancelled; no success "
                        "is claimed"
                    )
                try:
                    service.run(max_iterations=1)
                except (MonitorShutdown, KeyboardInterrupt):
                    break
                except AlreadyRunning as exc:
                    raise AcceptanceError(str(exc)) from exc
                except Exception as exc:  # noqa: BLE001 - fail closed, no success
                    from .api import TelegramError

                    if isinstance(exc, TelegramError):
                        raise AcceptanceError(
                            f"Telegram polling failed: {exc.__class__.__name__}"
                        ) from exc
                    raise
                observed = str(
                    _read_job(self.job_state, self.job_id).get("state") or "UNKNOWN"
                )
                if observed == "CANCELLED":
                    if not expect_resume or _has_delivered_message(
                        self.monitor_state / "monitor.db",
                        self.job_id,
                        self.manifest["instruction_token"],
                    ):
                        break
                sleep(0.1)
        finally:
            if previous:
                restore_signal_handlers(previous)
            state.close()
        print(
            "acceptance: isolated poller stopped; "
            f"synthetic job state={observed}",
            file=sys.stderr,
        )
        return {"job_id": self.job_id, "observed_state": observed}

    # ---- verification --------------------------------------------------------
    def verify(
        self, evidence_path: str | Path | None = None, *, write_report: bool = True
    ) -> dict:
        self._check_source_unchanged()
        source = self.manifest.get("source") or {}
        evidence_target = Path(
            evidence_path or self.manifest["paths"]["telegram_evidence"]
        )
        evidence = _read_json(evidence_target)
        if not isinstance(evidence, dict):
            raise AcceptanceError("Telegram evidence must be a JSON object")
        _validate_evidence(evidence, self.manifest)

        records = _list_job_records(self.job_state)
        for record in records:
            if not (record.get("synthetic") is True and record.get("synthetic_marker") == SYNTHETIC_MARKER):
                raise AcceptanceError("non-synthetic job found in acceptance state")

        job = _read_job(self.job_state, self.job_id)
        if job.get("synthetic") is not True:
            raise AcceptanceError("synthetic job marker is missing")
        state = str(job.get("state") or "UNKNOWN")
        if state in {"SUCCESS", "FAILED", "BLOCKED", "TIMEOUT"}:
            raise AcceptanceError(
                f"synthetic job reached {state}; the harness must never report a "
                "development success or failure"
            )
        if state != "CANCELLED":
            raise AcceptanceError(
                f"synthetic job final state is {state}, expected CANCELLED"
            )

        events = _read_events(self.job_state, self.job_id)
        event_names = [str(item.get("event") or "") for item in events]
        for required in ("cancel_requested", "cancel_observed"):
            if required not in event_names:
                raise AcceptanceError(f"missing cancellation event: {required}")
        if not any(
            item.get("event") == "finished" and "state=CANCELLED" in str(item.get("detail") or "")
            for item in events
        ):
            raise AcceptanceError("missing finished state=CANCELLED event")

        invocations = _read_invocations(self.job_state)
        cancel_calls = [
            item
            for item in invocations
            if (item.get("args") or [])[:2] == ["cancel", self.job_id]
        ]
        if not cancel_calls:
            raise AcceptanceError("fake dev cancel was not invoked for the synthetic job")

        messages = _owner_messages(self.monitor_state / "monitor.db", self.job_id)
        token = self.manifest["instruction_token"]
        matching = [item for item in messages if token in str(item.get("body") or "")]
        if not matching:
            raise AcceptanceError(
                f"no queued owner instruction contains {token}"
            )
        delivery_states = {str(item.get("delivery_state") or "") for item in matching}
        if delivery_states - {"queued", "delivered"}:
            raise AcceptanceError("owner instruction has an unexpected delivery state")
        delivered = any(item.get("delivery_state") == "delivered" for item in matching)
        if delivered:
            resume_calls = [
                item
                for item in invocations
                if (item.get("args") or [])[:2] == ["resume", self.job_id]
            ]
            if not resume_calls:
                raise AcceptanceError("owner instruction marked delivered without a resume")
            if not any(token in str(item.get("stdin") or "") for item in resume_calls):
                raise AcceptanceError("resume prompt did not contain the owner instruction")
            for item in matching:
                if item.get("delivery_state") == "delivered" and int(
                    item.get("delivered_attempt") or 0
                ) < 2:
                    raise AcceptanceError("delivered instruction has no resumed attempt")

        journal = _read_journal(Path(self.manifest["paths"]["journal"]))
        journal_report = _analyse_journal(journal, token)
        if journal_report["missing"]:
            raise AcceptanceError(
                "Telegram evidence is incomplete: "
                + ", ".join(journal_report["missing"])
            )
        if delivered and not journal_report["resume"]["all_present"]:
            raise AcceptanceError(
                "resume delivery evidence is incomplete: "
                + ", ".join(journal_report["resume"]["missing"])
            )

        report = {
            "ok": True,
            "kind": KIND,
            "synthetic": True,
            "job_id": self.job_id,
            "final_state": state,
            "instruction_state": "delivered" if delivered else "queued",
            "source": {
                "config": source.get("config"),
                "config_sha256": source.get("config_sha256"),
                "registry": source.get("registry"),
                "registry_sha256": source.get("registry_sha256"),
            },
            "telegram": journal_report,
            "checks": {
                "synthetic_only": True,
                "no_success_or_failure": True,
                "cancel_events": True,
                "owner_instruction_present": True,
                "source_config_unchanged": True,
                "production_registry_unchanged": True,
                "operator_attestations": True,
            },
            "verified_at": _utc_now(),
        }
        if write_report:
            _write_json(self.manifest["paths"]["report"], report, mode=0o600)
            _write_text(
                Path(self.manifest["paths"]["evidence"]) / "REPORT.md",
                _report_markdown(report),
                mode=0o600,
            )
        return report

    # ---- status and cleanup --------------------------------------------------
    def status(self) -> dict:
        job = _read_job(self.job_state, self.job_id)
        try:
            messages = _owner_messages(self.monitor_state / "monitor.db", self.job_id)
        except AcceptanceError:
            messages = []
        journal = _read_journal(Path(self.manifest["paths"]["journal"]))
        return {
            "kind": KIND,
            "synthetic": True,
            "job_id": self.job_id,
            "state": job.get("state"),
            "owner_messages": [
                {
                    "delivery_state": item.get("delivery_state"),
                    "delivered_attempt": item.get("delivered_attempt"),
                    "contains_token": self.manifest["instruction_token"]
                    in str(item.get("body") or ""),
                }
                for item in messages
            ],
            "journal_entries": len(journal),
            "monitor_running": bool(self.monitor_running_func(self.monitor_state)),
            "report": self.manifest["paths"]["report"],
        }

    def cleanup(self) -> None:
        if self.monitor_running_func(self.monitor_state):
            raise AcceptanceError(
                "the isolated acceptance monitor is still running; request a stop "
                "through the monitor stop flag before cleanup"
            )
        marker = self.root / MARKER_FILENAME
        if not marker.is_file():
            raise AcceptanceError("refusing to remove a directory without the harness marker")
        shutil.rmtree(self.root)


def _has_delivered_message(database: Path, job_id: str, token: str) -> bool:
    try:
        messages = _owner_messages(database, job_id)
    except AcceptanceError:
        return False
    return any(
        item.get("delivery_state") == "delivered"
        and token in str(item.get("body") or "")
        for item in messages
    )


def _parse_utc(value: object) -> bool:
    if not isinstance(value, str) or value in {"", "UNRECORDED"}:
        return False
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
        return True
    except ValueError:
        return False


def _validate_evidence(evidence: dict, manifest: dict) -> None:
    if evidence.get("job_id") != manifest["job_id"]:
        raise AcceptanceError("Telegram evidence belongs to another job")
    if evidence.get("synthetic_marker") != SYNTHETIC_MARKER:
        raise AcceptanceError("Telegram evidence synthetic marker is missing")
    operator = evidence.get("operator")
    if not isinstance(operator, str) or not operator.strip() or operator == "UNRECORDED":
        raise AcceptanceError("Telegram evidence must record the operator")
    lowered_operator = operator.strip().lower()
    if any(
        token in lowered_operator
        for token in ("unrecorded", "not recorded", "todo", "tbd", "pending")
    ):
        raise AcceptanceError("Telegram evidence operator is still a placeholder")
    for field_name in ("started_at_utc", "finished_at_utc"):
        if not _parse_utc(evidence.get(field_name)):
            raise AcceptanceError(
                f"Telegram evidence {field_name} must be a UTC timestamp"
            )
    for field_name in (
        "no_success_observed",
        "production_untouched",
        "qortium_unchanged",
    ):
        value = evidence.get(field_name)
        if value is not True:
            raise AcceptanceError(
                f"Telegram evidence must attest {field_name}=true"
            )


def _analyse_journal(entries: Sequence[dict], token: str) -> dict:
    outbound_texts: list[str] = []
    buttons: set[str] = set()
    callbacks: list[str] = []
    messages: list[str] = []
    for entry in entries:
        kind = entry.get("kind")
        if kind == "outbound":
            outbound_texts.append(str(entry.get("text") or ""))
            for label in entry.get("button_labels") or []:
                buttons.add(str(label))
        elif kind == "callback":
            callbacks.append(str(entry.get("label") or ""))
        elif kind == "message":
            messages.append(str(entry.get("text") or ""))

    def saw_text(fragment: str) -> bool:
        return any(fragment in text for text in outbound_texts)

    required = {
        "job_view_buttons": REQUIRED_BUTTONS[0] in buttons and REQUIRED_BUTTONS[1] in buttons,
        "queue_button": REQUIRED_BUTTONS[0] in callbacks,
        "instruction_text": any(token in text for text in messages),
        "queue_confirmation": saw_text("Queued for the next resume:")
        or saw_text("Instruction queued"),
        "cancel_button": REQUIRED_BUTTONS[1] in callbacks,
        "cancel_preview": saw_text("Cancel this running job?"),
        "cancel_confirm": CANCEL_CONFIRM_LABEL in callbacks,
        "cancel_result": saw_text("Cancel result: cancelled"),
    }
    missing = [name for name, passed in required.items() if not passed]

    resume_required = {
        "resume_button": "Resume" in callbacks,
        "resume_confirm_preview": "Confirm resume" in callbacks,
        "resume_confirmation": saw_text("Confirm resume"),
        "resume_final_confirm": RESUME_CONFIRM_LABEL in callbacks,
        "resume_delivered": saw_text("Queued instructions included: 1")
        or saw_text("Job resumed"),
    }
    resume_missing = [name for name, passed in resume_required.items() if not passed]
    return {
        "outbound_messages": len(outbound_texts),
        "message_updates": len(messages),
        "callback_updates": len(callbacks),
        "buttons": sorted(buttons),
        "callbacks": callbacks,
        "required": required,
        "missing": missing,
        "resume": {
            "required": resume_required,
            "missing": resume_missing,
            "all_present": not resume_missing,
        },
        "message_ids": [
            entry.get("message_id")
            for entry in entries
            if entry.get("kind") == "outbound" and entry.get("message_id")
        ],
        "update_ids": [
            entry.get("update_id")
            for entry in entries
            if entry.get("kind") in {"callback", "message"}
            and entry.get("update_id") is not None
        ],
    }


def _evidence_instructions(job_id: str, instruction: str) -> str:
    return f"""# Telegram interaction evidence (synthetic)

This file belongs to the isolated acceptance harness. Fill `telegram-evidence.json`
after the real Telegram interactions. Do not paste the bot token, chat ID or any
production job data.

- Job ID: `{job_id}`
- Synthetic marker: `{SYNTHETIC_MARKER}`
- Suggested instruction text: `{instruction}`

Record these actual button interactions in Telegram. The harness also journals
the observed labels, message IDs, update IDs and timestamps automatically.

| ID | Action | Expected observation |
| --- | --- | --- |
| E1 | Send `/jobs` and open the synthetic job | Title starts with `[SYNTHETIC]`; no production job appears |
| E2 | Open the job view | Buttons `Queue instruction` and `Cancel job` are present |
| E3 | Press `Queue instruction` and send the instruction with the marker token | Reply says `Instruction queued` / `Queued for the next resume: 1`; it is not live delivery |
| E4 | Send `/messages <job>` | The instruction is shown as `[queued]` for the next resume |
| E5 | Open the job and press `Cancel job` | Preview says `Cancel this running job?` and shows the synthetic job only |
| E6 | Press `Confirm: Cancel running job` | Reply says `Cancel result: cancelled`; state becomes `CANCELLED` |
| E7 | Optional: press `Resume`, then `Confirm resume`, then `Confirm: Resume job` | Preview lists the queued instruction; after resume it is delivered at attempt #2; cancel the synthetic job again before stopping |

In `telegram-evidence.json` set:

- `operator`: your name or registered role;
- `started_at_utc` and `finished_at_utc`: UTC timestamps in
  `YYYY-MM-DDTHH:MM:SSZ` form;
- `no_success_observed`, `production_untouched`, `qortium_unchanged`: `true`
  only after you actually verified them.

The harness rejects any remaining `UNRECORDED` value and any non-`CANCELLED`
synthetic job state.
"""


def _report_markdown(report: Mapping[str, Any]) -> str:
    telegram = report.get("telegram") or {}
    lines = [
        "# P3 Telegram live acceptance report (synthetic)",
        "",
        f"- Job ID: `{report.get('job_id')}`",
        f"- Synthetic: `{report.get('synthetic')}`",
        f"- Final state: `{report.get('final_state')}`",
        f"- Instruction delivery: `{report.get('instruction_state')}`",
        f"- Verified at: `{report.get('verified_at')}`",
        "",
        "This report proves an isolated harness flow. It is never evidence of a",
        "real development success.",
        "",
        "## Telegram evidence observed by the journal",
        "",
        f"- Outbound messages: {telegram.get('outbound_messages')}",
        f"- Message updates: {telegram.get('message_updates')}",
        f"- Callback updates: {telegram.get('callback_updates')}",
        f"- Buttons: {', '.join(telegram.get('buttons') or [])}",
        f"- Callbacks: {', '.join(telegram.get('callbacks') or [])}",
        f"- Message IDs: {', '.join(str(item) for item in telegram.get('message_ids') or [])}",
        f"- Update IDs: {', '.join(str(item) for item in telegram.get('update_ids') or [])}",
        "",
        "## Checks",
        "",
    ]
    for name, passed in (report.get("checks") or {}).items():
        lines.append(f"- {name}: `{passed}`")
    lines.append("")
    return "\n".join(lines)
