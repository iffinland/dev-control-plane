#!/usr/bin/env python3
"""Tests for monitor credential redaction and control-character sanitizing."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

from devmonitor.redact import (  # noqa: E402
    REDACTED,
    contains_secret,
    redact_error,
    redact_text,
    sanitize_control,
)


class RedactionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.token = str(987654321) + ":" + ("B" * 30)

    def test_exact_bot_token_is_removed(self) -> None:
        text = f"request https://api.telegram.org/bot{self.token}/getMe failed"
        result = redact_text(text, self.token)
        self.assertNotIn(self.token, result)
        self.assertIn(REDACTED, result)

    def test_bot_token_shape_without_known_secret(self) -> None:
        shaped = str(555555555) + ":" + ("C" * 28)
        result = redact_text(f"token {shaped}", ())
        self.assertNotIn(shaped, result)

    def test_bearer_authorization_value(self) -> None:
        value = "auth-value-" + "x" * 20
        result = redact_text(f"Authorization: Bearer {value}")
        self.assertNotIn(value, result)
        self.assertIn("Bearer " + REDACTED, result)

    def test_assignment_and_env_secret_patterns(self) -> None:
        secret = "value-" + "9" * 20
        samples = [
            "pass" + "word=" + secret,
            "api" + "_key: " + secret,
            "DEV_" + "TOKEN=" + secret,
            "client_" + "secret = '" + secret + "'",
        ]
        for sample in samples:
            with self.subTest(sample=sample.split("=", 1)[0]):
                result = redact_text(sample)
                self.assertNotIn(secret, result)
                self.assertIn(REDACTED, result)

    def test_common_token_shapes(self) -> None:
        github = "ghp_" + ("a" * 36)
        aws = "AKIA" + ("B" * 16)
        slack = "xoxb-" + ("1234567890" * 2)
        openai = "sk-" + ("d" * 30)
        result = redact_text(f"{github}\n{aws}\n{slack}\n{openai}")
        for value in (github, aws, slack, openai):
            self.assertNotIn(value, result)

    def test_private_key_block(self) -> None:
        begin = "-----BEGIN " + "PRIVATE KEY-----"
        end = "-----END " + "PRIVATE KEY-----"
        block = begin + "\nMIIExample\n" + end
        result = redact_text(block)
        self.assertNotIn("MIIExample", result)
        self.assertIn("redacted-private-key", result)

    def test_credential_bearing_url(self) -> None:
        url = "https://" + "user" + ":" + "pass" + "@example.invalid/path"
        result = redact_text(url)
        self.assertNotIn("user:pass", result)
        self.assertIn("<redacted>@example.invalid", result)

    def test_redaction_before_truncation(self) -> None:
        secret = "Z" * 40
        text = "prefix " + secret + " suffix"
        result = redact_text(text, (secret,), limit=10)
        self.assertNotIn(secret[:5], result)
        self.assertTrue(result.startswith("prefix"))

    def test_control_characters_and_ansi_are_removed(self) -> None:
        text = "hello\x1b[31m red\x00 world\x07"
        result = sanitize_control(text)
        self.assertNotIn("\x1b", result)
        self.assertNotIn("\x00", result)
        self.assertNotIn("\x07", result)
        self.assertIn("hello red world", result)

    def test_redact_error_does_not_leak_token(self) -> None:
        exc = RuntimeError(f"failed for https://api.telegram.org/bot{self.token}/getMe")
        result = redact_error(exc, self.token)
        self.assertNotIn(self.token, result)
        self.assertIn("RuntimeError", result)

    def test_contains_secret_helper(self) -> None:
        self.assertTrue(contains_secret("prefix " + self.token, self.token))
        self.assertFalse(contains_secret(redact_text(self.token, self.token), self.token))


if __name__ == "__main__":
    unittest.main()
