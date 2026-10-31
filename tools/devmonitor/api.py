"""Outbound-only Telegram Bot API client.

The client only makes HTTPS requests to the Telegram Bot API. It never registers
a webhook, never opens a listening socket and never downloads remote files.
Transports are injectable so tests use a fake instead of the real network.
"""

from __future__ import annotations

import json
import random
import urllib.error
import urllib.request
import uuid
from typing import Callable, Mapping

from .redact import redact_text
from .timings import TimingRecorder, default_recorder

JsonTransport = Callable[[str, dict, float], tuple[int, str]]
DocumentTransport = Callable[[str, dict, str, bytes, float], tuple[int, str]]


class TelegramError(RuntimeError):
    """Base class for sanitized Telegram failures."""


class TelegramFatalError(TelegramError):
    """A 401/403/409 or configuration conflict that must stop polling."""


class TelegramTransientError(TelegramError):
    """A 5xx, network error or timeout that should be retried with backoff."""


class TelegramRequestError(TelegramError):
    """A non-fatal 4xx request error for one message or update."""


class TelegramRateLimited(TelegramError):
    """A 429 response with the requested retry delay."""

    def __init__(self, message: str, retry_after: float = 1.0) -> None:
        super().__init__(message)
        self.retry_after = max(0.0, float(retry_after))


class TelegramStaleCallback(TelegramRequestError):
    """A callback query can no longer be answered (expired or already used).

    This is a UI acknowledgement failure, not a reason to drop the update: the
    associated read-only action can still be executed.
    """


STALE_CALLBACK_MARKERS = (
    "query is too old",
    "response timeout expired",
    "query id is invalid",
    "query_id_invalid",
)
CALLBACK_ACK_TIMEOUT_SECONDS = 5.0
DEFAULT_DOCUMENT_TIMEOUT_SECONDS = 60.0


def is_stale_callback_error(value: object) -> bool:
    """Return True for Telegram's expired/already-answered callback errors."""

    text = str(value).lower()
    return any(marker in text for marker in STALE_CALLBACK_MARKERS)


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
            return int(response.status), response.read(50000).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read(50000).decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise TelegramTransientError(str(exc)) from exc


def _default_document_transport(
    url: str, fields: dict, filename: str, data: bytes, timeout: float
) -> tuple[int, str]:
    boundary = f"----devmonitor{uuid.uuid4().hex}"
    body = bytearray()
    for name, value in fields.items():
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        body.extend(str(value).encode("utf-8"))
        body.extend(b"\r\n")
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(
        f'Content-Disposition: form-data; name="document"; filename="{filename}"\r\n'.encode()
    )
    body.extend(b"Content-Type: application/octet-stream\r\n\r\n")
    body.extend(data)
    body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode())
    request = urllib.request.Request(
        url,
        data=bytes(body),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return int(response.status), response.read(50000).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read(50000).decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise TelegramTransientError(str(exc)) from exc


class TelegramApi:
    def __init__(
        self,
        token: str,
        *,
        base_url: str = "https://api.telegram.org",
        timeout_seconds: float = 15.0,
        transport: JsonTransport | None = None,
        document_transport: DocumentTransport | None = None,
        document_timeout_seconds: float | None = None,
        timings: TimingRecorder | None = None,
    ) -> None:
        if not token:
            raise ValueError("Telegram bot token is required")
        self.token = token
        self.base_url = base_url.rstrip("/")
        # ``timeout_seconds`` bounds ordinary Bot API calls (send/edit/ack/
        # getMe). Long polling adds its own grace period in ``get_updates`` and
        # document uploads use the separate document timeout below.
        self.timeout_seconds = max(1.0, float(timeout_seconds))
        self.document_timeout_seconds = max(
            self.timeout_seconds,
            float(
                DEFAULT_DOCUMENT_TIMEOUT_SECONDS
                if document_timeout_seconds is None
                else document_timeout_seconds
            ),
        )
        self.transport = transport or _default_transport
        self.document_transport = document_transport or _default_document_transport
        self.timings = timings or default_recorder()

    def __repr__(self) -> str:
        return f"TelegramApi(base_url={self.base_url!r}, token='<set>')"

    def _sanitize(self, value: object, limit: int = 500) -> str:
        return redact_text(value, self.token, limit)

    def _call(
        self,
        method: str,
        payload: Mapping[str, object] | None = None,
        *,
        timeout: float | None = None,
    ) -> object:
        with self.timings.measure(f"telegram:{method}"):
            return self._call_impl(method, payload, timeout=timeout)

    def _call_impl(
        self,
        method: str,
        payload: Mapping[str, object] | None = None,
        *,
        timeout: float | None = None,
    ) -> object:
        url = f"{self.base_url}/bot{self.token}/{method}"
        try:
            status, body = self.transport(
                url, dict(payload or {}), timeout or self.timeout_seconds
            )
        except TelegramRateLimited as exc:
            raise TelegramRateLimited(self._sanitize(exc), exc.retry_after) from exc
        except TelegramError as exc:
            raise type(exc)(self._sanitize(exc)) from exc
        except Exception as exc:  # noqa: BLE001 - sanitize every transport failure
            raise TelegramTransientError(
                self._sanitize(f"{exc.__class__.__name__}: {exc}")
            ) from exc

        try:
            data = json.loads(body)
        except (TypeError, json.JSONDecodeError):
            data = {}
        if not isinstance(data, dict):
            data = {}
        description = data.get("description") or f"Telegram HTTP {status}"

        if 200 <= int(status) < 300 and data.get("ok") is True:
            return data.get("result")

        if int(status) == 409:
            raise TelegramFatalError(
                "Telegram 409 conflict: another poller or a webhook is active; "
                "stop the other poller or clear the webhook explicitly"
            )
        if int(status) in {401, 403}:
            raise TelegramFatalError(
                self._sanitize(f"Telegram authorization failed ({status}): {description}")
            )
        if int(status) == 429:
            parameters = data.get("parameters") if isinstance(data.get("parameters"), dict) else {}
            retry_after = parameters.get("retry_after", data.get("retry_after", 1))
            try:
                delay = float(retry_after)
            except (TypeError, ValueError):
                delay = 1.0
            raise TelegramRateLimited(
                self._sanitize(f"Telegram rate limited: {description}"), delay
            )
        if int(status) >= 500:
            raise TelegramTransientError(
                self._sanitize(f"Telegram server error ({status}): {description}")
            )
        if 400 <= int(status) < 500:
            raise TelegramRequestError(
                self._sanitize(f"Telegram rejected the request ({status}): {description}")
            )
        raise TelegramTransientError(
            self._sanitize(f"Telegram returned an unexpected status ({status})")
        )

    # ---- Bot API methods ---------------------------------------------------------
    def get_me(self) -> dict:
        result = self._call("getMe")
        return result if isinstance(result, dict) else {}

    def get_webhook_info(self) -> dict:
        result = self._call("getWebhookInfo")
        return result if isinstance(result, dict) else {}

    def get_updates(self, offset: int, timeout: float, limit: int = 100) -> list[dict]:
        result = self._call(
            "getUpdates",
            {
                "offset": max(0, int(offset)),
                "timeout": int(max(0, min(50, timeout))),
                "limit": max(1, min(100, int(limit))),
                "allowed_updates": ["message", "callback_query"],
            },
            timeout=timeout + 10,
        )
        if result is None:
            return []
        if not isinstance(result, list):
            raise TelegramTransientError("Telegram getUpdates returned an unexpected shape")
        return [item for item in result if isinstance(item, dict)]

    def send_message(self, chat_id: int, text: str, reply_markup: dict | None = None) -> dict:
        payload: dict[str, object] = {
            "chat_id": int(chat_id),
            "text": text,
            "disable_web_page_preview": True,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        result = self._call("sendMessage", payload)
        return result if isinstance(result, dict) else {}

    def edit_message_text(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        reply_markup: dict | None = None,
    ) -> dict:
        payload: dict[str, object] = {
            "chat_id": int(chat_id),
            "message_id": int(message_id),
            "text": text,
            "disable_web_page_preview": True,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        result = self._call("editMessageText", payload)
        return result if isinstance(result, dict) else {}

    def answer_callback_query(
        self,
        callback_query_id: str,
        text: str | None = None,
        *,
        timeout: float | None = None,
    ) -> bool:
        payload: dict[str, object] = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text[:200]
        # Long-poll timeouts must not apply to a UI acknowledgement. Keeping this
        # call short prevents one slow request from consuming the window in which
        # the remaining queued callback queries can still be answered.
        ack_timeout = min(
            self.timeout_seconds if timeout is None else float(timeout),
            CALLBACK_ACK_TIMEOUT_SECONDS,
        )
        try:
            self._call("answerCallbackQuery", payload, timeout=ack_timeout)
        except TelegramRequestError as exc:
            if is_stale_callback_error(exc):
                raise TelegramStaleCallback(str(exc)) from exc
            raise
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
        url = f"{self.base_url}/bot{self.token}/sendDocument"
        fields: dict[str, object] = {"chat_id": int(chat_id)}
        if caption:
            fields["caption"] = caption[:1024]
        try:
            with self.timings.measure("telegram:sendDocument"):
                status, body = self.document_transport(
                    url, fields, filename, data, self.document_timeout_seconds
                )
        except TelegramRateLimited as exc:
            raise TelegramRateLimited(self._sanitize(exc), exc.retry_after) from exc
        except TelegramError as exc:
            raise type(exc)(self._sanitize(exc)) from exc
        except Exception as exc:  # noqa: BLE001
            raise TelegramTransientError(
                self._sanitize(f"{exc.__class__.__name__}: {exc}")
            ) from exc
        try:
            parsed = json.loads(body)
        except (TypeError, json.JSONDecodeError):
            parsed = {}
        if not isinstance(parsed, dict):
            parsed = {}
        if 200 <= int(status) < 300 and parsed.get("ok") is True:
            result = parsed.get("result")
            return result if isinstance(result, dict) else {}
        if int(status) == 429:
            parameters = parsed.get("parameters") if isinstance(parsed.get("parameters"), dict) else {}
            raise TelegramRateLimited("Telegram rate limited while sending a document", float(parameters.get("retry_after", 1)))
        if int(status) >= 500:
            raise TelegramTransientError("Telegram server error while sending a document")
        raise TelegramRequestError(
            self._sanitize(f"Telegram rejected the document ({status})")
        )

    def set_my_commands(self, commands: list[dict]) -> bool:
        self._call("setMyCommands", {"commands": commands})
        return True


def backoff_seconds(attempt: int, base: float = 1.0, cap: float = 60.0) -> float:
    """Exponential backoff with jitter for transient failures."""

    delay = min(cap, base * (2 ** max(0, attempt - 1)))
    return min(cap, delay * (0.75 + random.random() * 0.5))
