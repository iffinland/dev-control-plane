"""Telegram notifications for Workflow v3 final job states.

Credentials are read from an owner-controlled file outside Git or from the
environment. They are never written to a job record, log or report. Failures to
notify never change the job result.
"""

from __future__ import annotations

import json
import os
import re
import stat
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .store import safe_text, utc_now


NOTIFY_STATES = ("SUCCESS", "FAILED", "BLOCKED", "TIMEOUT")
DEFAULT_CONFIG = Path.home() / ".config/dev-control-plane/telegram.json"

Transport = Callable[[str, dict, float], tuple[int, str]]


@dataclass
class TelegramSettings:
    enabled: bool
    bot_token: str | None
    chat_id: str | None
    events: tuple[str, ...]
    timeout_seconds: float
    config_path: Path | None
    warnings: list[str]

    def __repr__(self) -> str:
        return (
            "TelegramSettings("
            f"enabled={self.enabled!r}, "
            f"bot_token={'<set>' if self.bot_token else None}, "
            f"chat_id={'<set>' if self.chat_id else None}, "
            f"events={self.events!r})"
        )


def config_path(explicit: str | Path | None = None) -> Path:
    if explicit is not None:
        return Path(explicit).expanduser()
    value = os.environ.get("DEV_TELEGRAM_CONFIG")
    if value:
        return Path(value).expanduser()
    return DEFAULT_CONFIG


def _truthy(value: str | None) -> bool | None:
    if value is None:
        return None
    return value.strip().lower() not in {"0", "false", "no", "off", "disabled"}


def load_settings(
    path: str | Path | None = None,
    environ: dict[str, str] | None = None,
) -> TelegramSettings:
    env = dict(os.environ if environ is None else environ)
    target = config_path(path)
    warnings: list[str] = []
    data: dict = {}
    if target.is_file():
        try:
            data = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            warnings.append(f"telegram config could not be read: {exc.__class__.__name__}")
            data = {}
        else:
            try:
                mode = stat.S_IMODE(target.stat().st_mode)
                if mode & (stat.S_IRWXG | stat.S_IRWXO):
                    warnings.append(
                        f"telegram config {target} is group/world accessible; set mode 0600"
                    )
            except OSError:
                pass
    if not isinstance(data, dict):
        warnings.append("telegram config must be a JSON object")
        data = {}

    enabled_value = _truthy(env.get("DEV_TELEGRAM_ENABLED"))
    if enabled_value is None:
        enabled_value = bool(data.get("enabled", True))

    token = env.get("DEV_TELEGRAM_BOT_TOKEN") or data.get("bot_token")
    chat_id = env.get("DEV_TELEGRAM_CHAT_ID") or data.get("chat_id")
    if isinstance(chat_id, int):
        chat_id = str(chat_id)
    events_value = data.get("events", list(NOTIFY_STATES))
    if isinstance(events_value, str):
        events_value = [events_value]
    events = tuple(
        item for item in events_value if isinstance(item, str) and item in NOTIFY_STATES
    ) if isinstance(events_value, list) else NOTIFY_STATES
    try:
        timeout = float(data.get("timeout_seconds", 10))
    except (TypeError, ValueError):
        timeout = 10.0

    if enabled_value and (not token or not chat_id):
        warnings.append("telegram notifications enabled but bot_token/chat_id is missing")
        enabled_value = False

    return TelegramSettings(
        enabled=bool(enabled_value),
        bot_token=str(token) if token else None,
        chat_id=str(chat_id) if chat_id else None,
        events=events or NOTIFY_STATES,
        timeout_seconds=max(1.0, min(timeout, 60.0)),
        config_path=target if target.is_file() else None,
        warnings=warnings,
    )


def _redact(text: str, token: str | None) -> str:
    if token:
        text = text.replace(token, "<redacted>")
    text = re.sub(r"(?i)bot[0-9A-Za-z:_-]{8,}", "bot<redacted>", text)
    return safe_text(text, 500)


def _default_transport(url: str, payload: dict, timeout: float) -> tuple[int, str]:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return int(response.status), response.read(2000).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read(2000).decode("utf-8", "replace")
    except (urllib.error.URLError, OSError) as exc:
        raise RuntimeError(str(exc)) from exc


def send_message(
    settings: TelegramSettings,
    text: str,
    transport: Transport | None = None,
) -> tuple[bool, str]:
    if not settings.enabled:
        return False, "disabled"
    if not settings.bot_token or not settings.chat_id:
        return False, "missing credentials"
    url = f"https://api.telegram.org/bot{settings.bot_token}/sendMessage"
    payload = {
        "chat_id": settings.chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }
    try:
        status, body = (transport or _default_transport)(url, payload, settings.timeout_seconds)
    except Exception as exc:  # noqa: BLE001 - never let notification errors escape
        return False, _redact(f"{exc.__class__.__name__}: {exc}", settings.bot_token)
    if 200 <= status < 300:
        return True, "sent"
    return False, _redact(f"telegram HTTP {status}: {body}", settings.bot_token)


def build_message(job: dict, state: str | None = None) -> str:
    final_state = state or str(job.get("state", "UNKNOWN"))
    label = {
        "SUCCESS": "completed",
        "FAILED": "failed",
        "BLOCKED": "blocked",
        "TIMEOUT": "timed out",
    }.get(final_state, final_state.lower())
    lines = [
        f"[dev] Job {label}: {job.get('title', '(untitled)')}",
        f"job: {job.get('id', '')}",
        f"state: {final_state}",
    ]
    if job.get("repo"):
        branch = job.get("git", {}).get("branch") if isinstance(job.get("git"), dict) else None
        lines.append(f"repo: {job['repo']}" + (f" ({branch})" if branch else ""))
    if job.get("started_at"):
        lines.append(f"started: {job['started_at']}")
    if job.get("ended_at"):
        lines.append(f"ended: {job['ended_at']}")
    if job.get("duration_seconds") is not None:
        lines.append(f"duration: {int(job['duration_seconds'])}s")
    issues = job.get("detected_issues") or []
    if issues:
        lines.append(f"issues: {len(issues)}")
        for issue in issues[:5]:
            message = issue.get("message") if isinstance(issue, dict) else str(issue)
            lines.append(f"- {message}")
    if job.get("blocker"):
        lines.append(f"blocker: {job['blocker']}")
    if job.get("report_path"):
        lines.append(f"report: {job['report_path']}")
    if job.get("log_path"):
        lines.append(f"log: {job['log_path']}")
    return safe_text("\n".join(lines), 3500)


def notify_job(
    job: dict,
    settings: TelegramSettings | None = None,
    transport: Transport | None = None,
    notification_root=None,
) -> dict:
    """Send one final-state notification and return a sanitized record."""
    if job.get("notifications_enabled") is False:
        return {"state": job.get("state"), "sent": False, "reason": "disabled for job"}
    settings = settings or load_settings()
    state = str(job.get("state", ""))
    record = {
        "at": utc_now(),
        "state": state,
        "sent": False,
        "reason": "",
    }
    if state not in NOTIFY_STATES:
        record["reason"] = "state is not notifiable"
        return record
    if state not in settings.events:
        record["reason"] = "state is not enabled for notifications"
        return record
    sent, reason = send_message(settings, build_message(job, state), transport)
    record["sent"] = sent
    record["reason"] = reason
    job.setdefault("notifications", []).append(record)
    job["notifications"] = job["notifications"][-20:]
    return record
