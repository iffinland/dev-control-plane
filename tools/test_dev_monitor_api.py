#!/usr/bin/env python3
"""Telegram client tests using fake transports only (no network)."""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

from devmonitor.api import (  # noqa: E402
    CALLBACK_ACK_TIMEOUT_SECONDS,
    TelegramApi,
    TelegramFatalError,
    TelegramRateLimited,
    TelegramRequestError,
    TelegramStaleCallback,
    TelegramTransientError,
    backoff_seconds,
    is_stale_callback_error,
)
from devmonitor_test_support import BOT_TOKEN, FakeTransport  # noqa: E402


def response(result=None, ok: bool = True, description: str | None = None, parameters=None) -> str:
    payload = {"ok": ok, "result": result}
    if description is not None:
        payload["description"] = description
    if parameters is not None:
        payload["parameters"] = parameters
    return json.dumps(payload)


class ApiTests(unittest.TestCase):
    def test_get_me(self) -> None:
        transport = FakeTransport([(200, response({"id": 1, "username": "bot"}))])
        api = TelegramApi(BOT_TOKEN, transport=transport)
        self.assertEqual(api.get_me()["username"], "bot")
        self.assertTrue(transport.calls[0]["url"].endswith("/getMe"))

    def test_get_updates_offset_and_allowed_updates(self) -> None:
        transport = FakeTransport([(200, response([]))])
        api = TelegramApi(BOT_TOKEN, transport=transport)
        api.get_updates(42, 20)
        payload = transport.calls[0]["payload"]
        self.assertEqual(payload["offset"], 42)
        self.assertEqual(payload["allowed_updates"], ["message", "callback_query"])
        self.assertGreater(transport.calls[0]["timeout"], 20)

    def test_409_is_fatal_and_does_not_leak_token(self) -> None:
        transport = FakeTransport([(409, response(ok=False, description="Conflict"))])
        api = TelegramApi(BOT_TOKEN, transport=transport)
        with self.assertRaises(TelegramFatalError) as caught:
            api.get_updates(0, 1)
        self.assertIn("409", str(caught.exception))
        self.assertNotIn(BOT_TOKEN, str(caught.exception))

    def test_401_is_fatal(self) -> None:
        transport = FakeTransport([(401, response(ok=False, description="Unauthorized"))])
        api = TelegramApi(BOT_TOKEN, transport=transport)
        with self.assertRaises(TelegramFatalError):
            api.get_me()

    def test_429_exposes_retry_after(self) -> None:
        transport = FakeTransport(
            [(429, response(ok=False, description="Too Many Requests", parameters={"retry_after": 7}))]
        )
        api = TelegramApi(BOT_TOKEN, transport=transport)
        with self.assertRaises(TelegramRateLimited) as caught:
            api.get_updates(0, 1)
        self.assertEqual(caught.exception.retry_after, 7.0)

    def test_5xx_is_transient(self) -> None:
        transport = FakeTransport([(503, response(ok=False, description="Service Unavailable"))])
        api = TelegramApi(BOT_TOKEN, transport=transport)
        with self.assertRaises(TelegramTransientError):
            api.get_me()

    def test_network_exception_is_sanitized(self) -> None:
        def failing(url, payload, timeout):
            raise OSError(f"cannot connect to {url}")

        api = TelegramApi(BOT_TOKEN, transport=failing)
        with self.assertRaises(TelegramTransientError) as caught:
            api.get_me()
        self.assertNotIn(BOT_TOKEN, str(caught.exception))

    def test_error_body_containing_request_url_is_redacted(self) -> None:
        url = "https://api.telegram.org/bot" + BOT_TOKEN + "/getMe"
        transport = FakeTransport([(400, response(ok=False, description=f"bad {url}"))])
        api = TelegramApi(BOT_TOKEN, transport=transport)
        with self.assertRaises(TelegramRequestError) as caught:
            api.get_me()
        self.assertNotIn(BOT_TOKEN, str(caught.exception))

    def test_stale_callback_ack_is_classified_and_not_fatal(self) -> None:
        description = (
            "Bad Request: query is too old and response timeout expired or "
            "query ID is invalid"
        )
        transport = FakeTransport([(400, response(ok=False, description=description))])
        api = TelegramApi(BOT_TOKEN, transport=transport)
        with self.assertRaises(TelegramStaleCallback) as caught:
            api.answer_callback_query("cb-old")
        self.assertIsInstance(caught.exception, TelegramRequestError)
        self.assertTrue(is_stale_callback_error(caught.exception))
        self.assertNotIn(BOT_TOKEN, str(caught.exception))

    def test_other_callback_ack_400_remains_a_request_error(self) -> None:
        transport = FakeTransport(
            [(400, response(ok=False, description="Bad Request: callback_query_id is invalid"))]
        )
        api = TelegramApi(BOT_TOKEN, transport=transport)
        with self.assertRaises(TelegramRequestError) as caught:
            api.answer_callback_query("cb-bad")
        self.assertNotIsInstance(caught.exception, TelegramStaleCallback)

    def test_callback_ack_uses_a_short_bounded_timeout(self) -> None:
        transport = FakeTransport([(200, response(True))])
        api = TelegramApi(BOT_TOKEN, transport=transport, timeout_seconds=35)
        self.assertTrue(api.answer_callback_query("cb-1", "ok"))
        self.assertLessEqual(
            transport.calls[0]["timeout"], CALLBACK_ACK_TIMEOUT_SECONDS
        )

    def test_send_message_payload(self) -> None:
        transport = FakeTransport([(200, response({"message_id": 5}))])
        api = TelegramApi(BOT_TOKEN, transport=transport)
        result = api.send_message(2002, "hello", {"inline_keyboard": []})
        self.assertEqual(result["message_id"], 5)
        self.assertEqual(transport.calls[0]["payload"]["chat_id"], 2002)
        self.assertTrue(transport.calls[0]["payload"]["disable_web_page_preview"])

    def test_document_transport_receives_validated_bytes(self) -> None:
        calls = []

        def document_transport(url, fields, filename, data, timeout):
            calls.append((url, fields, filename, data, timeout))
            return 200, response({"message_id": 9})

        transport = FakeTransport([])
        api = TelegramApi(BOT_TOKEN, transport=transport, document_transport=document_transport)
        result = api.send_document(2002, "report.redacted.md", b"# report", "caption")
        self.assertEqual(result["message_id"], 9)
        self.assertEqual(calls[0][2], "report.redacted.md")
        self.assertEqual(calls[0][3], b"# report")


    def test_non_poll_calls_use_the_request_timeout(self) -> None:
        transport = FakeTransport(
            [
                (200, response({"id": 1})),
                (200, response([])),
                (200, response(True)),
            ]
        )
        api = TelegramApi(
            BOT_TOKEN,
            transport=transport,
            timeout_seconds=8,
            document_timeout_seconds=45,
        )
        api.get_me()
        self.assertEqual(transport.calls[-1]["timeout"], 8)
        api.get_updates(0, 25)
        self.assertGreaterEqual(transport.calls[-1]["timeout"], 25)
        self.assertTrue(api.answer_callback_query("cb-1"))
        self.assertLessEqual(transport.calls[-1]["timeout"], 5)
        self.assertEqual(api.document_timeout_seconds, 45)

    def test_document_upload_uses_the_document_timeout(self) -> None:
        calls = []

        def document_transport(url, fields, filename, data, timeout):
            calls.append(timeout)
            return 200, response({"message_id": 9})

        api = TelegramApi(
            BOT_TOKEN,
            transport=FakeTransport([]),
            document_transport=document_transport,
            timeout_seconds=7,
            document_timeout_seconds=55,
        )
        api.send_document(2002, "report.redacted.md", b"# report")
        self.assertEqual(calls, [55])

    def test_api_has_no_webhook_setter(self) -> None:
        api = TelegramApi(BOT_TOKEN, transport=FakeTransport())
        self.assertFalse(hasattr(api, "set_webhook"))
        self.assertFalse(hasattr(api, "setWebhook"))

    def test_backoff_is_bounded(self) -> None:
        for attempt in range(1, 10):
            self.assertGreaterEqual(backoff_seconds(attempt), 0.1)
            self.assertLessEqual(backoff_seconds(attempt), 60.0)


if __name__ == "__main__":
    unittest.main()
