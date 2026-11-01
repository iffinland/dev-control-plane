#!/usr/bin/env python3
"""Monitor SQLite state tests: offsets, dedupe, refs, confirmations and audit."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

from devmonitor.state import MonitorState  # noqa: E402
from devmonitor.timings import TimingRecorder  # noqa: E402


class StateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="qdm-state-")
        self.root = Path(self.temporary.name)
        self.path = self.root / "monitor" / "monitor.db"
        self.state = MonitorState(self.path)

    def tearDown(self) -> None:
        self.state.close()
        self.temporary.cleanup()

    def test_offset_and_seen_updates_persist_across_reopen(self) -> None:
        self.assertTrue(self.state.claim_update(41))
        self.state.set_offset(42)
        self.state.close()
        reopened = MonitorState(self.path)
        try:
            self.assertEqual(reopened.next_offset(), 42)
            self.assertFalse(reopened.claim_update(41))
        finally:
            reopened.close()
        self.state = MonitorState(self.path)

    def test_offset_never_moves_backwards(self) -> None:
        self.state.set_offset(42)
        self.state.set_offset(7)
        self.assertEqual(self.state.next_offset(), 42)

    def test_release_allows_retry(self) -> None:
        self.assertTrue(self.state.claim_update(50))
        self.state.release_update(50)
        self.assertTrue(self.state.claim_update(50))

    def test_job_refs_are_chat_scoped_and_stable(self) -> None:
        first = self.state.get_or_create_job_ref("job-1", 100)
        second = self.state.get_or_create_job_ref("job-1", 100)
        self.assertEqual(first, second)
        self.assertEqual(self.state.resolve_job_ref(first, 100), "job-1")
        self.assertIsNone(self.state.resolve_job_ref(first, 999))

    def test_browse_state_is_user_and_chat_scoped(self) -> None:
        browse_id = self.state.create_browse(100, 200, "docs", "reports", 1)
        self.assertIsNotNone(self.state.get_browse(browse_id, 100, 200))
        self.assertIsNone(self.state.get_browse(browse_id, 101, 200))
        self.assertIsNone(self.state.get_browse(browse_id, 100, 201))
        self.state.update_browse(browse_id, rel_dir="other", page=2)
        updated = self.state.get_browse(browse_id, 100, 200)
        self.assertEqual(updated["rel_dir"], "other")
        self.assertEqual(updated["page"], 2)

    def test_expired_browse_is_removed(self) -> None:
        now = [1000]
        state = MonitorState(self.root / "clock.db", clock=lambda: now[0])
        try:
            browse_id = state.create_browse(1, 2, "docs", "", 0, ttl_seconds=10)
            now[0] = 1011
            self.assertIsNone(state.get_browse(browse_id, 1, 2))
        finally:
            state.close()

    def test_confirmation_is_single_use_and_scoped(self) -> None:
        nonce = self.state.create_confirmation(1, 2, "download_binary", {"rel": "a.png"})
        self.assertIsNone(self.state.consume_confirmation(nonce, 9, 2, "download_binary"))
        self.assertIsNone(self.state.consume_confirmation(nonce, 1, 2, "other"))
        payload = self.state.consume_confirmation(nonce, 1, 2, "download_binary")
        self.assertEqual(payload, {"rel": "a.png"})
        self.assertIsNone(self.state.consume_confirmation(nonce, 1, 2, "download_binary"))

    def test_rate_limit_window(self) -> None:
        now = [100]
        state = MonitorState(self.root / "rate.db", clock=lambda: now[0])
        try:
            self.assertTrue(state.hit_rate_limit("user:1", 2, 60))
            self.assertTrue(state.hit_rate_limit("user:1", 2, 60))
            self.assertFalse(state.hit_rate_limit("user:1", 2, 60))
            now[0] = 200
            self.assertTrue(state.hit_rate_limit("user:1", 2, 60))
        finally:
            state.close()


    def test_journal_mode_is_wal_for_concurrent_status_readers(self) -> None:
        row = self.state.connection.execute("PRAGMA journal_mode").fetchone()
        self.assertEqual(str(row[0]).lower(), "wal")

    def test_offset_update_is_atomic_and_recorded_in_timings(self) -> None:
        recorder = TimingRecorder(slow_seconds=10.0)
        state = MonitorState(self.root / "timed.db", timings=recorder)
        try:
            state.set_offset(64)
            self.assertEqual(state.next_offset(), 64)
            self.assertIsNotNone(state.get_meta("last_poll_at"))
            labels = {item["label"] for item in recorder.snapshot()["labels"]}
            self.assertIn("sqlite:set_offset", labels)
        finally:
            state.close()

    def test_wizard_state_is_scoped_and_expires(self) -> None:
        wizard_id = self.state.create_wizard(1, 2, "start", "title", {"project_id": "demo"})
        wizard = self.state.get_wizard(wizard_id, 1, 2)
        self.assertEqual(wizard["step"], "title")
        self.assertEqual(wizard["data"]["project_id"], "demo")
        self.assertIsNone(self.state.get_wizard(wizard_id, 9, 2))
        self.assertTrue(
            self.state.update_wizard(wizard_id, 1, 2, step="prompt", data={"prompt": "x"})
        )
        updated = self.state.get_wizard(wizard_id, 1, 2)
        self.assertEqual(updated["step"], "prompt")
        self.assertEqual(updated["data"]["prompt"], "x")
        self.state.delete_wizard(wizard_id, 1, 2)
        self.assertIsNone(self.state.get_wizard(wizard_id, 1, 2))

    def test_active_wizard_expires(self) -> None:
        now = [1000]
        state = MonitorState(self.root / "wizard-clock.db", clock=lambda: now[0])
        try:
            state.create_wizard(1, 2, "start", "title", {}, ttl_seconds=10)
            self.assertIsNotNone(state.get_active_wizard(1, 2))
            now[0] = 1011
            self.assertIsNone(state.get_active_wizard(1, 2))
        finally:
            state.close()

    def test_notification_claim_is_at_most_once(self) -> None:
        self.assertTrue(self.state.claim_notification("started:job-1", "job-1", "STARTED"))
        self.assertFalse(self.state.claim_notification("started:job-1", "job-1", "STARTED"))
        self.assertTrue(self.state.has_notification("started:job-1"))

    def test_event_cursor_round_trip(self) -> None:
        self.assertIsNone(self.state.get_event_cursor("job-1"))
        self.state.set_event_cursor("job-1", 123, 456, "abc")
        cursor = self.state.get_event_cursor("job-1")
        self.assertEqual(cursor["inode"], 123)
        self.assertEqual(cursor["offset"], 456)
        self.assertEqual(cursor["last_event_hash"], "abc")

    def test_confirmation_action_is_scoped_and_single_use(self) -> None:
        nonce = self.state.create_confirmation(1, 2, "start_job", {"x": 1})
        self.assertEqual(self.state.confirmation_action(nonce, 1, 2), "start_job")
        self.assertIsNone(self.state.confirmation_action(nonce, 9, 2))
        self.state.consume_confirmation(nonce, 1, 2, "start_job")
        self.assertIsNone(self.state.confirmation_action(nonce, 1, 2))

    def test_owner_messages_are_durable_and_explicitly_delivered(self) -> None:
        message_id = self.state.add_owner_message("job-1", 1, 2, "first instruction")
        self.state.add_owner_message("job-2", 1, 2, "other job")
        self.assertEqual(self.state.count_pending_owner_messages("job-1"), 1)
        pending = self.state.list_owner_messages("job-1", pending_only=True)
        self.assertEqual([item["message_id"] for item in pending], [message_id])
        self.state.close()
        reopened = MonitorState(self.path)
        try:
            self.assertEqual(reopened.count_pending_owner_messages("job-1"), 1)
            delivered = reopened.mark_owner_messages_delivered([message_id], 2)
            self.assertEqual(delivered, 1)
            self.assertEqual(reopened.count_pending_owner_messages("job-1"), 0)
            row = reopened.list_owner_messages("job-1")[0]
            self.assertEqual(row["delivery_state"], "delivered")
            self.assertEqual(row["delivered_attempt"], 2)
            self.assertIsNotNone(row["delivered_at"])
            # Delivering the same message again is a no-op.
            self.assertEqual(reopened.mark_owner_messages_delivered([message_id], 3), 0)
        finally:
            reopened.close()
        self.state = MonitorState(self.path)

    def test_owner_message_errors_are_redacted_and_queue_is_kept(self) -> None:
        message_id = self.state.add_owner_message("job-1", 1, 2, "instruction")
        secret = "queue-" + "secret-" + "789"
        self.state.record_owner_message_error([message_id], "pass" + "word=" + secret)
        row = self.state.list_owner_messages("job-1")[0]
        self.assertEqual(row["delivery_state"], "queued")
        self.assertNotIn(secret, row["last_error_redacted"])
        self.assertIn("<redacted>", row["last_error_redacted"])

    def test_prune_removes_only_old_delivered_owner_messages(self) -> None:
        now = [1_000_000]
        state = MonitorState(self.root / "owner-clock.db", clock=lambda: now[0])
        try:
            delivered_id = state.add_owner_message("job-1", 1, 2, "old")
            queued_id = state.add_owner_message("job-1", 1, 2, "keep")
            state.mark_owner_messages_delivered([delivered_id], 1)
            now[0] += 7200
            state.prune(
                seen_retention_seconds=1,
                owner_message_retention_seconds=3600,
            )
            remaining = {item["message_id"] for item in state.list_owner_messages("job-1")}
            self.assertNotIn(delivered_id, remaining)
            self.assertIn(queued_id, remaining)
        finally:
            state.close()

    def test_audit_redacts_credentials(self) -> None:
        secret = "audit-" + "secret-" + "123"
        self.state.record_audit(
            "test",
            "ok",
            user_id=1,
            chat_id=2,
            update_id=3,
            detail="pass" + "word=" + secret,
        )
        row = self.state.connection.execute(
            "SELECT detail_redacted FROM audit ORDER BY id DESC LIMIT 1"
        ).fetchone()
        self.assertNotIn(secret, row["detail_redacted"])
        self.assertIn("<redacted>", row["detail_redacted"])


if __name__ == "__main__":
    unittest.main()
