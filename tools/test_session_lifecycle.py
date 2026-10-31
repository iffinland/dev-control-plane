#!/usr/bin/env python3
"""Regression tests for Workflow v3 session completion and duration reporting.

The completion cases use the real structure of an ``opencode export`` payload:
the final assistant message carries ``finish=stop`` and each tool part carries a
state. These tests never start a model session and never signal a real process.

The duration cases pin the distinction between total job elapsed time (which
includes earlier attempts) and the current/last attempt elapsed time.
"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

import session_state  # noqa: E402
from devjob import notify, runner  # noqa: E402


def message(
    *,
    message_id: str = "msg_1",
    role: str = "assistant",
    finish: str | None = "stop",
    created: int = 2000,
    completed: int | None = 2500,
    parts: list[dict] | None = None,
    error: object = None,
) -> dict:
    info: dict = {"id": message_id, "role": role, "time": {"created": created}}
    if finish is not None:
        info["finish"] = finish
    if completed is not None:
        info["time"]["completed"] = completed
    if error is not None:
        info["error"] = error
    return {"info": info, "parts": parts or []}


def tool_part(status: str, tool: str = "bash") -> dict:
    return {"type": "tool", "tool": tool, "state": {"status": status}}


def payload(messages: list[dict], *, session_id: str = "ses_test") -> dict:
    return {"info": {"id": session_id, "time": {"updated": 9000}}, "messages": messages}


class CompletionEvidenceTests(unittest.TestCase):
    def test_final_stop_with_no_active_tool_is_complete(self) -> None:
        evidence = session_state.completion_evidence(
            payload([message(parts=[tool_part("completed")])]),
            since_ms=1000,
        )
        self.assertIsNotNone(evidence)
        assert evidence is not None
        self.assertEqual(evidence["message_id"], "msg_1")
        self.assertEqual(evidence["finish"], "stop")
        self.assertEqual(evidence["active_tool_calls"], 0)

    def test_finish_stop_alone_is_not_enough_when_tool_is_running(self) -> None:
        evidence = session_state.completion_evidence(
            payload([message(parts=[tool_part("running")])]),
            since_ms=1000,
        )
        self.assertIsNone(evidence)

    def test_pending_tool_part_blocks_completion(self) -> None:
        evidence = session_state.completion_evidence(
            payload([message(parts=[tool_part("pending")])]),
            since_ms=1000,
        )
        self.assertIsNone(evidence)

    def test_tool_calls_finish_is_not_complete(self) -> None:
        evidence = session_state.completion_evidence(
            payload([message(finish="tool-calls")]),
            since_ms=1000,
        )
        self.assertIsNone(evidence)

    def test_assistant_error_is_not_complete(self) -> None:
        evidence = session_state.completion_evidence(
            payload([message(error="provider error")]),
            since_ms=1000,
        )
        self.assertIsNone(evidence)

    def test_previous_attempt_stop_is_ignored(self) -> None:
        evidence = session_state.completion_evidence(
            payload([message(created=1000, completed=1100)]),
            since_ms=2000,
        )
        self.assertIsNone(evidence)

    def test_newer_user_message_wins_over_old_stop(self) -> None:
        evidence = session_state.completion_evidence(
            payload(
                [
                    message(message_id="msg_stop", created=2000, completed=2100),
                    message(
                        message_id="msg_user",
                        role="user",
                        finish=None,
                        created=3000,
                        completed=3000,
                        parts=[{"type": "text", "text": "continue"}],
                    ),
                ]
            ),
            since_ms=1000,
        )
        self.assertIsNone(evidence)

    def test_active_tool_in_previous_attempt_does_not_block_current_turn(self) -> None:
        old = message(message_id="msg_old", created=1000, completed=1100, parts=[tool_part("running")])
        new = message(message_id="msg_new", created=3000, completed=3100)
        evidence = session_state.completion_evidence(payload([old, new]), since_ms=2000)
        self.assertIsNotNone(evidence)

    def test_has_observable_events(self) -> None:
        self.assertFalse(session_state.has_observable_events(payload([])))
        self.assertTrue(
            session_state.has_observable_events(payload([message(parts=[tool_part("completed")])]))
        )


class DurationReportingTests(unittest.TestCase):
    def iso(self, seconds_ago: int) -> str:
        moment = datetime.now(timezone.utc) - timedelta(seconds=seconds_ago)
        return moment.strftime("%Y-%m-%dT%H:%M:%SZ")

    def running_job(self) -> dict:
        return {
            "id": "job-duration",
            "title": "duration",
            "state": "RUNNING",
            "started_at": self.iso(1000),
            "ended_at": None,
            "timeout_seconds": 7200,
            "attempts": [
                {
                    "number": 1,
                    "started_at": self.iso(1000),
                    "ended_at": self.iso(700),
                    "duration_seconds": 300,
                },
                {
                    "number": 2,
                    "started_at": self.iso(100),
                    "ended_at": None,
                    "duration_seconds": None,
                },
            ],
        }

    def test_status_separates_total_and_attempt_elapsed(self) -> None:
        payload = runner.status_payload(self.running_job())
        self.assertGreaterEqual(payload["elapsed_seconds"], 995)
        self.assertLessEqual(payload["elapsed_seconds"], 1010)
        self.assertGreaterEqual(payload["attempt_elapsed_seconds"], 95)
        self.assertLessEqual(payload["attempt_elapsed_seconds"], 110)
        self.assertEqual(payload["attempt_number"], 2)
        self.assertGreaterEqual(payload["total_attempt_seconds"], 395)
        self.assertLessEqual(payload["total_attempt_seconds"], 420)

    def test_finished_job_elapsed_is_fixed(self) -> None:
        job = self.running_job()
        job["state"] = "SUCCESS"
        job["started_at"] = self.iso(2000)
        job["ended_at"] = self.iso(1000)
        job["attempts"][0] = {
            "number": 1,
            "started_at": self.iso(2000),
            "ended_at": self.iso(1000),
            "duration_seconds": 1000,
        }
        job["attempts"][1] = {
            "number": 2,
            "started_at": self.iso(1000),
            "ended_at": self.iso(900),
            "duration_seconds": 100,
        }
        job["duration_seconds"] = 1000
        job["attempt_duration_seconds"] = 100
        payload = runner.status_payload(job)
        self.assertEqual(payload["elapsed_seconds"], 1000)
        self.assertEqual(payload["duration_seconds"], 1000)
        self.assertEqual(payload["attempt_elapsed_seconds"], 100)

    def test_render_status_labels_total_and_attempt(self) -> None:
        text = runner.render_status(self.running_job())
        self.assertIn("total", text)
        self.assertIn("attempt", text)
        self.assertIn("#2", text)

    def test_notification_separates_total_and_attempt(self) -> None:
        job = self.running_job()
        job["state"] = "TIMEOUT"
        job["ended_at"] = self.iso(0)
        job["duration_seconds"] = 1000
        job["attempt_duration_seconds"] = 100
        job["detected_issues"] = []
        text = notify.build_message(job)
        self.assertIn("duration (total): 16m40s", text)
        self.assertIn("duration (attempt #2): 1m40s", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
