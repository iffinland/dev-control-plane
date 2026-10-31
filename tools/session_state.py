"""Structured OpenCode session evidence shared by the guard and job engine.

OpenCode 1.19.5 can leave the ``opencode run`` process alive after a resumed
session has already produced its final assistant message. Process exit alone is
therefore not a reliable completion signal. This module reads the same
structured session export used by run detection and exposes a small, pure
completion check plus the subprocess helpers needed to obtain it.

Everything here is standard library only. Exports are parsed from an anonymous
temporary file because OpenCode 1.19.5 truncates large exports written to a
pipe. Nothing is written to a job directory or repository.

Completion is *not* acceptance. It only means the agent turn finished and no
tool call is active; the caller still has to verify the explicit acceptance
criteria before treating a job as successful.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Iterable

MAX_SESSION_BYTES = 32 * 1024 * 1024
SESSION_EXPORT_TIMEOUT = 30
SESSION_LIST_TIMEOUT = 20
ACTIVE_STATUSES = frozenset({"pending", "running", "awaiting", "in_progress"})


def _as_dict(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def _as_list(value: object) -> list:
    return value if isinstance(value, list) else []


def _int_timestamp(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def message_created_ms(message: object) -> int | None:
    info = _as_dict(_as_dict(message).get("info"))
    return _int_timestamp(_as_dict(info.get("time")).get("created"))


def message_completed_ms(message: object) -> int | None:
    info = _as_dict(_as_dict(message).get("info"))
    return _int_timestamp(_as_dict(info.get("time")).get("completed"))


def session_updated_ms(payload: object) -> int | None:
    """Return the session update timestamp from an export payload, if present."""
    info = _as_dict(_as_dict(payload).get("info"))
    updated = _int_timestamp(_as_dict(info.get("time")).get("updated"))
    if updated is not None:
        return updated
    latest: int | None = None
    for message in _as_list(_as_dict(payload).get("messages")):
        for value in (message_created_ms(message), message_completed_ms(message)):
            if value is not None and (latest is None or value > latest):
                latest = value
    return latest


def session_updated_from_list(sessions: object, session_id: str) -> int | None:
    for item in _as_list(sessions):
        item = _as_dict(item)
        if str(item.get("id") or item.get("sessionID") or "") != session_id:
            continue
        for key in ("updated", "updated_at", "updatedMs"):
            value = _int_timestamp(item.get(key))
            if value is not None:
                return value
    return None


def active_tool_calls(payload: object, since_ms: int | None = None) -> list[dict]:
    """Return pending/running tool parts, optionally scoped to the current attempt."""
    active: list[dict] = []
    for message in _as_list(_as_dict(payload).get("messages")):
        message = _as_dict(message)
        created = message_created_ms(message)
        if since_ms is not None and created is not None and created < since_ms:
            continue
        info = _as_dict(message.get("info"))
        for part in _as_list(message.get("parts")):
            part = _as_dict(part)
            state = _as_dict(part.get("state"))
            status = str(state.get("status") or "").lower()
            if status not in ACTIVE_STATUSES:
                continue
            active.append(
                {
                    "message_id": info.get("id"),
                    "type": part.get("type"),
                    "tool": part.get("tool"),
                    "status": status,
                }
            )
    return active


def completion_evidence(payload: object, since_ms: int | None = None) -> dict | None:
    """Return evidence that the agent turn is complete, or ``None``.

    Requirements, all of which must hold:

    - at least one message was created at or after ``since_ms`` (attempt scope);
    - the newest such message is an assistant message with ``finish == "stop"``;
    - that message has no error;
    - no tool part created in the same attempt is pending or running.

    ``finish=stop`` is necessary but never sufficient for job success; the job
    engine still runs every required acceptance criterion.
    """

    if not isinstance(payload, dict):
        return None
    relevant: list[tuple[int, str, dict]] = []
    for message in _as_list(payload.get("messages")):
        message = _as_dict(message)
        created = message_created_ms(message)
        if created is None:
            continue
        if since_ms is not None and created < since_ms:
            continue
        info = _as_dict(message.get("info"))
        relevant.append((created, str(info.get("id") or ""), message))
    if not relevant:
        return None
    created, _message_id, latest = max(relevant, key=lambda item: (item[0], item[1]))
    info = _as_dict(latest.get("info"))
    if str(info.get("role") or "") != "assistant":
        return None
    if str(info.get("finish") or "") != "stop":
        return None
    if info.get("error"):
        return None
    active = active_tool_calls(payload, since_ms=since_ms)
    if active:
        return None
    return {
        "session_id": str(_as_dict(payload.get("info")).get("id") or "") or None,
        "message_id": str(info.get("id") or "") or None,
        "message_created_ms": created,
        "finished_at_ms": message_completed_ms(latest) or created,
        "finish": "stop",
        "active_tool_calls": 0,
        "observed_at_ms": int(time.time() * 1000),
    }


def discover_session_id(
    sessions: object,
    *,
    session_id: str | None = None,
    title: str | None = None,
) -> str | None:
    if session_id:
        return session_id
    if not title:
        return None
    for item in _as_list(sessions):
        item = _as_dict(item)
        item_title = str(item.get("title") or "")
        if item_title == title:
            return str(item.get("id") or item.get("sessionID") or "") or None
    return None


def list_sessions(
    *,
    cwd: str | Path | None = None,
    timeout: int = SESSION_LIST_TIMEOUT,
    max_count: int = 50,
) -> list[dict] | None:
    try:
        result = subprocess.run(
            [
                "opencode",
                "session",
                "list",
                "--format",
                "json",
                "--max-count",
                str(max_count),
            ],
            cwd=str(cwd) if cwd is not None else None,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0 or not result.stdout.strip():
        return None
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    if isinstance(payload, dict):
        payload = payload.get("sessions") or payload.get("data") or []
    if not isinstance(payload, list):
        return None
    return [item for item in payload if isinstance(item, dict)]


def load_export(
    session_id: str | None,
    *,
    cwd: str | Path | None = None,
    timeout: int = SESSION_EXPORT_TIMEOUT,
    max_bytes: int = MAX_SESSION_BYTES,
) -> dict | None:
    if not session_id:
        return None
    try:
        with tempfile.TemporaryFile(mode="w+b") as handle:
            result = subprocess.run(
                ["opencode", "export", str(session_id)],
                cwd=str(cwd) if cwd is not None else None,
                stdout=handle,
                stderr=subprocess.DEVNULL,
                timeout=timeout,
                check=False,
            )
            if result.returncode != 0:
                return None
            handle.seek(0)
            data = handle.read(max_bytes + 1)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if len(data) > max_bytes or not data.strip():
        return None
    try:
        payload = json.loads(data.decode("utf-8", "replace"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def has_observable_events(payload: object) -> bool:
    """True when an export contains tool parts or assistant text to inspect."""
    for message in _as_list(_as_dict(payload).get("messages")):
        message = _as_dict(message)
        role = str(_as_dict(message.get("info")).get("role") or "")
        for part in _as_list(message.get("parts")):
            part = _as_dict(part)
            part_type = str(part.get("type") or "")
            if part_type == "tool" or (part_type == "text" and role == "assistant"):
                return True
    return False


def iter_relevant_messages(
    payload: object, since_ms: int | None = None
) -> Iterable[dict]:
    for message in _as_list(_as_dict(payload).get("messages")):
        message = _as_dict(message)
        created = message_created_ms(message)
        if since_ms is not None and created is not None and created < since_ms:
            continue
        yield message
