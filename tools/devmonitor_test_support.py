"""Shared isolated fixtures for Qortium Dev Monitor tests."""

from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from devmonitor.api import TelegramApi  # noqa: E402
from devmonitor.config import MonitorConfig, load_monitor_config  # noqa: E402

USER_ID = 1001
CHAT_ID = 2002
OTHER_USER = 3003
OTHER_CHAT = 4004
BOT_TOKEN = str(123456789) + ":" + ("A" * 30)


def make_config(
    root: Path,
    *,
    mode: str = "read_only",
    user_ids: list[int] | None = None,
    chat_ids: list[int] | None = None,
    docs_roots: list[Path] | None = None,
    repo_roots: list[Path] | None = None,
    allow_binary: bool = False,
    file_mode: int = 0o600,
    monitor_extra: dict | None = None,
) -> MonitorConfig:
    monitor = {
        "mode": mode,
        "authorized_user_ids": user_ids if user_ids is not None else [USER_ID],
        "allowed_chat_ids": chat_ids if chat_ids is not None else [CHAT_ID],
        "require_private_chat": True,
        "poll_timeout_seconds": 1,
        "status_refresh_seconds": 30,
        "max_inline_chars": 3500,
        "max_text_download_bytes": 65536,
        "max_binary_download_bytes": 65536,
        "allow_binary_downloads": allow_binary,
        "allowed_repo_roots": [str(path) for path in (repo_roots or [root / "projects"])],
        "docs_roots": [str(path) for path in (docs_roots or [])],
        "agent_allowlist": ["opencode-development"],
        "model_allowlist": ["deepseek/deepseek-flash"],
    }
    if monitor_extra:
        monitor.update(monitor_extra)
    data = {
        "enabled": False,
        "bot_token": BOT_TOKEN,
        "chat_id": str(CHAT_ID),
        "events": ["SUCCESS", "FAILED", "BLOCKED", "TIMEOUT"],
        "timeout_seconds": 1,
        "monitor": monitor,
    }
    config_path = root / "telegram.json"
    config_path.write_text(json.dumps(data), encoding="utf-8")
    os.chmod(config_path, file_mode)
    return load_monitor_config(
        config_path,
        environ={},
        state_dir=root / "monitor",
        require_secure=True,
    )


def message_update(
    update_id: int,
    text: str,
    *,
    user_id: int = USER_ID,
    chat_id: int = CHAT_ID,
    chat_type: str = "private",
    is_bot: bool = False,
) -> dict:
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "from": {"id": user_id, "is_bot": is_bot, "username": "owner"},
            "chat": {"id": chat_id, "type": chat_type},
            "text": text,
        },
    }


def callback_update(
    update_id: int,
    data: str,
    *,
    user_id: int = USER_ID,
    chat_id: int = CHAT_ID,
    chat_type: str = "private",
    message_id: int = 500,
) -> dict:
    return {
        "update_id": update_id,
        "callback_query": {
            "id": f"cb-{update_id}",
            "from": {"id": user_id, "is_bot": False},
            "message": {
                "message_id": message_id,
                "chat": {"id": chat_id, "type": chat_type},
                "text": "previous",
            },
            "data": data,
        },
    }


class FakeApi:
    """In-memory Telegram API used by router, service and check tests."""

    def __init__(self, updates: list[list[dict]] | None = None) -> None:
        self.updates = list(updates or [])
        self.sent: list[dict] = []
        self.edited: list[dict] = []
        self.answered: list[dict] = []
        self.documents: list[dict] = []
        self.me = {"id": 1, "is_bot": True, "username": "qdm_test_bot"}
        self.webhook = {"url": ""}
        self.get_updates_calls: list[dict] = []
        self.faults: list[BaseException] = []
        self._message_id = 1000

    def get_updates(self, offset: int, timeout: float, limit: int = 100) -> list[dict]:
        self.get_updates_calls.append({"offset": offset, "timeout": timeout, "limit": limit})
        if self.faults:
            raise self.faults.pop(0)
        return self.updates.pop(0) if self.updates else []

    def get_me(self) -> dict:
        return dict(self.me)

    def get_webhook_info(self) -> dict:
        return dict(self.webhook)

    def _next_id(self) -> int:
        self._message_id += 1
        return self._message_id

    def send_message(self, chat_id: int, text: str, reply_markup: dict | None = None) -> dict:
        message_id = self._next_id()
        self.sent.append(
            {"chat_id": chat_id, "text": text, "markup": reply_markup, "message_id": message_id}
        )
        return {"message_id": message_id}

    def edit_message_text(
        self, chat_id: int, message_id: int, text: str, reply_markup: dict | None = None
    ) -> dict:
        self.edited.append(
            {"chat_id": chat_id, "message_id": message_id, "text": text, "markup": reply_markup}
        )
        return {"message_id": message_id}

    def answer_callback_query(self, callback_query_id: str, text: str | None = None) -> bool:
        self.answered.append({"id": callback_query_id, "text": text})
        return True

    def send_document(
        self,
        chat_id: int,
        filename: str,
        data: bytes,
        caption: str | None = None,
        *,
        mime_type: str = "text/plain",
    ) -> dict:
        self.documents.append(
            {
                "chat_id": chat_id,
                "filename": filename,
                "data": data,
                "caption": caption,
                "mime_type": mime_type,
            }
        )
        return {"message_id": self._next_id()}


class FakeTransport:
    def __init__(self, responses: list[tuple[int, str]] | None = None) -> None:
        self.responses = list(responses or [])
        self.calls: list[dict] = []

    def __call__(self, url: str, payload: dict, timeout: float) -> tuple[int, str]:
        self.calls.append({"url": url, "payload": payload, "timeout": timeout})
        if not self.responses:
            return 200, json.dumps({"ok": True, "result": {}})
        return self.responses.pop(0)


def api_with_transport(transport) -> TelegramApi:
    return TelegramApi(BOT_TOKEN, transport=transport)


FAKE_DEV = r'''#!/usr/bin/env python3
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

state = Path(os.environ["DEV_CONTROL_PLANE_STATE"])
state.mkdir(parents=True, exist_ok=True)
jobs_file = state / "fake_jobs.json"
jobs = json.loads(jobs_file.read_text(encoding="utf-8")) if jobs_file.is_file() else {}
args = sys.argv[1:]


def save():
    jobs_file.write_text(json.dumps(jobs, indent=2, sort_keys=True), encoding="utf-8")


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_job_files(job):
    directory = state / "jobs" / job["id"]
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "job.json").write_text(json.dumps(job, indent=2, sort_keys=True), encoding="utf-8")
    return directory


def append_event(job, event, detail=""):
    directory = write_job_files(job)
    payload = {"ts": now(), "event": event, "detail": detail}
    with (directory / "events.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def record(args, stdin_text=""):
    path = state / "fake_invocations.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"args": args, "stdin": stdin_text}) + "\n")


def option(name, default=None):
    return args[args.index(name) + 1] if name in args else default


def options(name):
    values = []
    for index, item in enumerate(args):
        if item == name and index + 1 < len(args):
            values.append(args[index + 1])
    return values


def slug(value):
    out = "".join(ch.lower() if ch.isalnum() else "-" for ch in value)
    while "--" in out:
        out = out.replace("--", "-")
    return out.strip("-")[:32] or "job"


if args[:1] == ["status"]:
    if "--all" in args:
        print(json.dumps(list(jobs.values())))
    else:
        job_id = args[1]
        print(json.dumps(jobs[job_id]))
elif args[:1] == ["report"]:
    job_id = args[1]
    job = jobs[job_id]
    report_path = state / "jobs" / job_id / "report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("# Report\n\nGenerated by the fake dev CLI.\n", encoding="utf-8")
    print(json.dumps({"job": job, "report_path": str(report_path)}))
elif args[:1] == ["start"]:
    prompt = sys.stdin.read()
    record(args, prompt)
    number = len([item for item in jobs.values() if item.get("fake_origin") == "start"]) + 1
    job_id = "20261031T130000Z-fake-job-%08d" % number
    state_file = state / "fake_start_state"
    desired = state_file.read_text(encoding="utf-8").strip() if state_file.is_file() else "RUNNING"
    title = option("--title", "Fake job")
    job = {
        "id": job_id,
        "title": title,
        "state": desired,
        "repo": option("--repo", str(state / "repo")),
        "branch": option("--branch"),
        "started_at": now(),
        "ended_at": None if desired == "RUNNING" else now(),
        "elapsed_seconds": 0,
        "attempt_elapsed_seconds": 0,
        "timeout_seconds": 28800,
        "attempt_number": 0 if desired != "RUNNING" else 1,
        "attempt_started_at": now() if desired == "RUNNING" else None,
        "attempt_ended_at": None,
        "worker_pid": 4242 if desired == "RUNNING" else None,
        "guard_pid": 4243 if desired == "RUNNING" else None,
        "child_pid": 4244 if desired == "RUNNING" else None,
        "worker_alive": desired == "RUNNING",
        "session_id": None,
        "blocker": "" if desired == "RUNNING" else "guard preflight refused: fake refusal",
        "pending_criteria": [],
        "issues": [],
        "resume_count": 0,
        "notifications": [],
        "notifications_enabled": False,
        "attempts": [],
        "acceptance_criteria": [],
        "fake_origin": "start",
        "prompt": prompt,
        "agent": option("--agent"),
        "model": option("--model"),
        "criteria": options("--criterion"),
        "manual_criteria": options("--manual-criterion"),
        "no_notify": "--no-notify" in args,
    }
    jobs[job_id] = job
    save()
    write_job_files(job)
    if desired == "RUNNING":
        append_event(job, "worker_started", "pid=4242")
        append_event(job, "attempt_started", "attempt=1 resume=False")
    else:
        append_event(job, "blocked_preflight", job["blocker"])
    print(json.dumps(job))
    sys.exit(0 if desired == "RUNNING" else 20)
elif args[:1] == ["resume"]:
    stdin_text = sys.stdin.read() if "--prompt-file" in args else ""
    record(args, stdin_text)
    job_id = args[1]
    job = jobs[job_id]
    job["state"] = "RUNNING"
    job["ended_at"] = None
    job["blocker"] = None
    job["worker_alive"] = True
    job["worker_pid"] = 5252
    job["guard_pid"] = 5253
    job["resume_count"] = int(job.get("resume_count") or 0) + 1
    job["attempt_number"] = int(job.get("attempt_number") or 0) + 1
    job["attempts"] = list(job.get("attempts") or []) + [{"number": job["attempt_number"]}]
    if "--new-session" in args:
        job["session_id"] = "ses_new_" + job_id[-8:]
    job["is_resume"] = True
    save()
    write_job_files(job)
    append_event(job, "resume_requested", "resume_count=%d" % job["resume_count"])
    append_event(job, "attempt_started", "attempt=%d resume=True" % job["attempt_number"])
    print(json.dumps(job))
elif args[:1] == ["cancel"]:
    record(args)
    job_id = args[1]
    job = jobs.get(job_id)
    if not job:
        print("fake dev: job not found", file=sys.stderr)
        sys.exit(2)
    if job.get("state") != "RUNNING" or not job.get("worker_alive"):
        print("fake dev: only a RUNNING job can be cancelled", file=sys.stderr)
        sys.exit(2)
    job["state"] = "CANCELLED"
    job["blocker"] = "cancelled by owner request"
    job["worker_alive"] = False
    job["ended_at"] = now()
    if job.get("attempts"):
        job["attempts"][-1]["ended_at"] = now()
    save()
    write_job_files(job)
    append_event(job, "cancel_requested", "attempt=1 guard_pid=%s" % job.get("guard_pid"))
    append_event(job, "cancel_observed", "attempt=1")
    append_event(job, "finished", "state=CANCELLED exit=143")
    payload = {
        "cancel_status": "cancelled",
        "detail": "fake verified cancellation",
        "job": job,
    }
    print(json.dumps(payload))
else:
    print("fake dev: unsupported command", file=sys.stderr)
    sys.exit(2)
'''


def install_fake_dev(root: Path) -> Path:
    path = root / "fake_dev.py"
    path.write_text(FAKE_DEV, encoding="utf-8")
    return path


def write_fake_jobs(state_root: Path, jobs: list[dict]) -> None:
    state_root.mkdir(parents=True, exist_ok=True)
    (state_root / "fake_jobs.json").write_text(json.dumps({job["id"]: job for job in jobs}), encoding="utf-8")
    for job in jobs:
        directory = state_root / "jobs" / job["id"]
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "job.json").write_text(
            json.dumps(job, indent=2, sort_keys=True), encoding="utf-8"
        )


def make_job(
    job_id: str = "20261031T120000Z-demo-job-abcd1234",
    *,
    state: str = "RUNNING",
    title: str = "Demo job",
    repo: str = "/home/iffi/dev-workspace/projects/Demo",
    notifications_enabled: bool = True,
    notifications: list[dict] | None = None,
    session_id: str | None = "ses_abcdefghijklmnopqrstuvwxyz",
    attempts: int = 1,
    ended_at: str | None = None,
) -> dict:
    return {
        "id": job_id,
        "title": title,
        "state": state,
        "repo": repo,
        "branch": "main",
        "started_at": "2026-10-31T12:00:00Z",
        "ended_at": ended_at if ended_at is not None else (None if state == "RUNNING" else "2026-10-31T12:10:00Z"),
        "elapsed_seconds": 600,
        "attempt_elapsed_seconds": 300,
        "timeout_seconds": 28800,
        "attempt_number": max(1, attempts),
        "attempt_started_at": "2026-10-31T12:00:00Z",
        "attempt_ended_at": None if state == "RUNNING" else "2026-10-31T12:05:00Z",
        "worker_pid": 1234,
        "guard_pid": 1235,
        "child_pid": 1236,
        "worker_alive": state == "RUNNING",
        "session_id": session_id,
        "blocker": "",
        "pending_criteria": ["AC1"],
        "issues": [{"severity": "HIGH", "kind": "test", "message": "sample issue"}],
        "resume_count": 0,
        "attempts": [{"number": index + 1} for index in range(max(1, attempts))],
        "acceptance_criteria": [],
        "notifications": list(notifications or []),
        "notifications_enabled": notifications_enabled,
    }
