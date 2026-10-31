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
from pathlib import Path

state = Path(os.environ["DEV_CONTROL_PLANE_STATE"])
jobs_file = state / "fake_jobs.json"
jobs = json.loads(jobs_file.read_text(encoding="utf-8")) if jobs_file.is_file() else {}
args = sys.argv[1:]
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


def make_job(
    job_id: str = "20261031T120000Z-demo-job-abcd1234",
    *,
    state: str = "RUNNING",
    title: str = "Demo job",
) -> dict:
    return {
        "id": job_id,
        "title": title,
        "state": state,
        "repo": "/home/iffi/dev-workspace/projects/Demo",
        "branch": "main",
        "started_at": "2026-10-31T12:00:00Z",
        "ended_at": None if state == "RUNNING" else "2026-10-31T12:10:00Z",
        "elapsed_seconds": 600,
        "attempt_elapsed_seconds": 300,
        "timeout_seconds": 28800,
        "attempt_number": 1,
        "attempt_started_at": "2026-10-31T12:00:00Z",
        "attempt_ended_at": None if state == "RUNNING" else "2026-10-31T12:05:00Z",
        "worker_pid": 1234,
        "guard_pid": 1235,
        "child_pid": 1236,
        "worker_alive": state == "RUNNING",
        "session_id": "ses_abcdefghijklmnopqrstuvwxyz",
        "blocker": "",
        "pending_criteria": ["AC1"],
        "issues": [{"severity": "HIGH", "kind": "test", "message": "sample issue"}],
        "resume_count": 0,
        "notifications": [],
    }
