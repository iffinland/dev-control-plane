"""Numeric allowlist authorization for the Qortium Dev Monitor.

Only ``message`` and ``callback_query`` updates are considered. Usernames,
display names, forwarded metadata and callback content are never authorizing.
Every callback is rechecked against the same numeric user/chat allowlists.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .config import MonitorConfig


@dataclass(frozen=True)
class AuthDecision:
    allowed: bool
    reason: str
    kind: str | None = None
    user_id: int | None = None
    chat_id: int | None = None
    chat_type: str | None = None
    update_id: int | None = None


def extract_event(update: Any) -> tuple[str | None, dict[str, Any] | None]:
    """Return the supported event kind and object, or (None, None)."""

    if not isinstance(update, dict):
        return None, None
    for kind in ("message", "callback_query"):
        value = update.get(kind)
        if isinstance(value, dict):
            return kind, value
    return None, None


def _event_chat(kind: str, event: dict[str, Any]) -> dict[str, Any] | None:
    if kind == "message":
        chat = event.get("chat")
    else:
        message = event.get("message")
        chat = message.get("chat") if isinstance(message, dict) else None
    return chat if isinstance(chat, dict) else None


def _event_user(kind: str, event: dict[str, Any]) -> dict[str, Any] | None:
    user = event.get("from")
    return user if isinstance(user, dict) else None


def authorize(update: Any, config: MonitorConfig) -> AuthDecision:
    kind, event = extract_event(update)
    update_id = update.get("update_id") if isinstance(update, dict) else None
    if kind is None or event is None:
        return AuthDecision(False, "unsupported_update", update_id=update_id)

    user = _event_user(kind, event)
    chat = _event_chat(kind, event)
    if user is None or chat is None:
        return AuthDecision(False, "missing_identity", kind=kind, update_id=update_id)

    user_id = user.get("id")
    chat_id = chat.get("id")
    chat_type = chat.get("type") if isinstance(chat.get("type"), str) else None
    if isinstance(user_id, bool) or not isinstance(user_id, int):
        return AuthDecision(False, "non_numeric_user", kind=kind, update_id=update_id)
    if isinstance(chat_id, bool) or not isinstance(chat_id, int):
        return AuthDecision(
            False,
            "non_numeric_chat",
            kind=kind,
            user_id=user_id,
            update_id=update_id,
        )
    if user.get("is_bot") is True:
        return AuthDecision(
            False,
            "bot_sender",
            kind=kind,
            user_id=user_id,
            chat_id=chat_id,
            chat_type=chat_type,
            update_id=update_id,
        )
    if user_id not in config.authorized_user_ids:
        return AuthDecision(
            False,
            "user_not_authorized",
            kind=kind,
            user_id=user_id,
            chat_id=chat_id,
            chat_type=chat_type,
            update_id=update_id,
        )
    if chat_id not in config.allowed_chat_ids:
        return AuthDecision(
            False,
            "chat_not_allowed",
            kind=kind,
            user_id=user_id,
            chat_id=chat_id,
            chat_type=chat_type,
            update_id=update_id,
        )
    if config.require_private_chat and chat_type != "private":
        return AuthDecision(
            False,
            "chat_not_private",
            kind=kind,
            user_id=user_id,
            chat_id=chat_id,
            chat_type=chat_type,
            update_id=update_id,
        )
    return AuthDecision(
        True,
        "allowed",
        kind=kind,
        user_id=user_id,
        chat_id=chat_id,
        chat_type=chat_type,
        update_id=update_id,
    )


def is_authorized(config: MonitorConfig, user_id: int, chat_id: int) -> bool:
    return user_id in config.authorized_user_ids and chat_id in config.allowed_chat_ids
