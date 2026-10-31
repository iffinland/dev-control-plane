#!/usr/bin/env python3
"""Authorization tests for the Qortium Dev Monitor."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

from devmonitor.auth import authorize, extract_event  # noqa: E402
from devmonitor_test_support import (  # noqa: E402
    CHAT_ID,
    OTHER_CHAT,
    OTHER_USER,
    USER_ID,
    callback_update,
    make_config,
    message_update,
)


class AuthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="qdm-auth-")
        self.root = Path(self.temporary.name)
        self.config = make_config(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_authorized_private_message(self) -> None:
        decision = authorize(message_update(1, "/start"), self.config)
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.user_id, USER_ID)
        self.assertEqual(decision.chat_id, CHAT_ID)

    def test_unknown_numeric_user_is_denied(self) -> None:
        decision = authorize(message_update(1, "/start", user_id=OTHER_USER), self.config)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "user_not_authorized")

    def test_allowed_user_in_group_is_denied(self) -> None:
        decision = authorize(
            message_update(1, "/start", chat_id=CHAT_ID, chat_type="group"), self.config
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "chat_not_private")

    def test_wrong_private_chat_is_denied(self) -> None:
        decision = authorize(message_update(1, "/start", chat_id=OTHER_CHAT), self.config)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "chat_not_allowed")

    def test_bot_sender_is_denied(self) -> None:
        decision = authorize(message_update(1, "/start", is_bot=True), self.config)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "bot_sender")

    def test_callback_is_rechecked(self) -> None:
        allowed = authorize(callback_update(2, "m"), self.config)
        self.assertTrue(allowed.allowed)
        denied = authorize(callback_update(2, "m", user_id=OTHER_USER), self.config)
        self.assertFalse(denied.allowed)

    def test_callback_from_wrong_chat_is_denied(self) -> None:
        denied = authorize(callback_update(2, "m", chat_id=OTHER_CHAT), self.config)
        self.assertFalse(denied.allowed)
        self.assertEqual(denied.reason, "chat_not_allowed")

    def test_non_numeric_identity_is_denied(self) -> None:
        update = message_update(1, "/start")
        update["message"]["from"]["id"] = "1001"
        decision = authorize(update, self.config)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "non_numeric_user")

    def test_unsupported_update_is_ignored(self) -> None:
        decision = authorize({"update_id": 1, "edited_message": {}}, self.config)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "unsupported_update")
        self.assertEqual(extract_event({"update_id": 1}), (None, None))


if __name__ == "__main__":
    unittest.main()
