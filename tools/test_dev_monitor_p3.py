#!/usr/bin/env python3
"""P3 cancellation and queued owner-messaging tests.

The Telegram API and Workflow v3 CLI are local fakes. No real bot, job, signal,
Qortium process or VPS service is used.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

from devmonitor.admission import AdmissionManager  # noqa: E402
from devmonitor.config import with_overrides  # noqa: E402
from devmonitor.control import ControlManager  # noqa: E402
from devmonitor.documents import DocumentLibrary  # noqa: E402
from devmonitor.jobs import JobError, JobFacade  # noqa: E402
from devmonitor.lifecycle import LifecycleNotifier  # noqa: E402
from devmonitor.projects import Registry  # noqa: E402
from devmonitor.router import Router  # noqa: E402
from devmonitor.state import MonitorState  # noqa: E402
from devmonitor_test_support import (  # noqa: E402
    CHAT_ID,
    USER_ID,
    FakeApi,
    callback_update,
    install_fake_dev,
    make_config,
    make_job,
    message_update,
    write_fake_jobs,
)


def find_button(markup, text_fragment: str) -> str:
    for row in (markup or {}).get("inline_keyboard", []):
        for item in row:
            if text_fragment.lower() in item.get("text", "").lower():
                return item["callback_data"]
    raise AssertionError(f"button not found: {text_fragment}")


def has_button(markup, text_fragment: str) -> bool:
    try:
        find_button(markup, text_fragment)
        return True
    except AssertionError:
        return False


class P3Base(unittest.TestCase):
    mode = "control"

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="qdm-p3-")
        self.root = Path(self.temporary.name)
        self.projects = self.root / "projects"
        self.projects.mkdir()
        self.project_repo = self.projects / "Demo"
        self.project_repo.mkdir()
        self.docs = self.root / "docs"
        self.docs.mkdir()
        self.registry_file = self.root / "PROJECT-REGISTRY.md"
        self.registry_file.write_text(
            "# Project registry\n\n## Registered projects\n\n"
            "| ID | Platform | Verified local path | Project-level `AGENTS.md` | Canonical context | Central report root |\n"
            "| --- | --- | --- | --- | --- | --- |\n"
            f"| `demo/project` | Qortal | `{self.project_repo}` | Yes | Pending | `{self.docs}/` |\n",
            encoding="utf-8",
        )
        self.state_root = self.root / "state"
        self.fake_dev = install_fake_dev(self.root)
        self.config = make_config(
            self.root,
            mode=self.mode,
            docs_roots=[self.docs],
            repo_roots=[self.projects],
        )
        self.config = with_overrides(self.config, registry_path=self.registry_file)
        self.state = MonitorState(self.root / "monitor" / "monitor.db")
        self.api = FakeApi()
        self.registry = Registry(self.registry_file, (self.projects,))
        self.documents = DocumentLibrary.from_sources(
            self.config.docs_roots, self.registry.load(force=True)
        )
        self.jobs = JobFacade(self.state_root, dev_script=self.fake_dev)
        self.admission = AdmissionManager(
            self.config.state_dir, self.jobs, self.registry
        )
        self.notifier = LifecycleNotifier(
            self.config, self.state, self.jobs, self.api, self.registry
        )
        self.control = ControlManager(
            self.config,
            self.state,
            self.jobs,
            self.registry,
            self.admission,
            notifier=self.notifier,
        )
        self.router = Router(
            self.config,
            self.state,
            self.api,
            self.jobs,
            self.registry,
            self.documents,
            control=self.control,
            admission=self.admission,
            notifier=self.notifier,
        )
        self.update_id = 1

    def tearDown(self) -> None:
        self.state.close()
        self.temporary.cleanup()

    def next_id(self) -> int:
        self.update_id += 1
        return self.update_id

    def invocations(self) -> list[dict]:
        path = self.state_root / "fake_invocations.jsonl"
        if not path.is_file():
            return []
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def terminal_job(self, *, state: str = "FAILED", session_id: str | None = "ses_demo") -> dict:
        job = make_job(
            "20261101T120000Z-p3-terminal-33333333",
            state=state,
            title="P3 terminal job",
            repo=str(self.project_repo),
            session_id=session_id,
            notifications_enabled=True,
            notifications=[{"state": state, "sent": True, "reason": "sent"}],
        )
        write_fake_jobs(self.state_root, [job])
        return job

    def running_job(self) -> dict:
        job = make_job(
            "20261101T120000Z-p3-running-44444444",
            repo=str(self.project_repo),
            title="P3 running job",
        )
        write_fake_jobs(self.state_root, [job])
        return job

    def open_job(self, job_id: str) -> None:
        self.router.handle(message_update(self.next_id(), f"/job {job_id}"))

    def send_text(self, value: str) -> None:
        self.router.handle(message_update(self.next_id(), value))

    def confirm(self, callback_data: str) -> None:
        self.router.handle(callback_update(self.next_id(), callback_data))

    def queue_instruction(self, job_id: str, body: str) -> None:
        self.open_job(job_id)
        queue_button = find_button(self.api.sent[-1]["markup"], "Queue instruction")
        self.confirm(queue_button)
        self.assertIn("Queue an owner instruction", self.api.edited[-1]["text"])
        self.send_text(body)


class CancelMonitorTests(P3Base):
    def test_running_job_exposes_verified_cancel_flow(self) -> None:
        job = self.running_job()
        self.open_job(job["id"])
        self.assertTrue(has_button(self.api.sent[-1]["markup"], "Cancel job"))
        self.assertTrue(has_button(self.api.sent[-1]["markup"], "Queue instruction"))

        cancel_button = find_button(self.api.sent[-1]["markup"], "Cancel job")
        self.confirm(cancel_button)
        self.assertIn("Cancel this running job", self.api.edited[-1]["text"])
        self.assertIn("SIGTERM", self.api.edited[-1]["text"])
        confirm = find_button(self.api.edited[-1]["markup"], "Confirm: Cancel running job")
        self.confirm(confirm)

        records = self.invocations()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["args"][:2], ["cancel", job["id"]])
        self.assertIn("--json", records[0]["args"])
        self.assertIn("Cancel result: cancelled", self.api.edited[-1]["text"])
        status = self.jobs.job_status(job["id"])
        self.assertEqual(status["state"], "CANCELLED")
        self.assertTrue(
            any("cancel" in str(row["action"]) for row in self._audit_rows())
        )

    def test_cancel_confirmation_is_one_time(self) -> None:
        job = self.running_job()
        self.router.handle(message_update(self.next_id(), f"/cancel {job['id']}"))
        confirm = find_button(self.api.sent[-1]["markup"], "Confirm: Cancel running job")
        self.confirm(confirm)
        self.confirm(confirm)
        self.assertEqual(len(self.invocations()), 1)
        self.assertIn("expired or already used", self.api.edited[-1]["text"])

    def test_terminal_job_cancel_is_refused_without_cli(self) -> None:
        job = self.terminal_job()
        self.router.handle(message_update(self.next_id(), f"/cancel {job['id']}"))
        self.assertIn("not RUNNING", self.api.sent[-1]["text"])
        self.assertEqual(self.invocations(), [])

    def _audit_rows(self) -> list[dict]:
        rows = self.state.connection.execute("SELECT action, result FROM audit").fetchall()
        return [dict(row) for row in rows]


class ReadOnlyCancelTests(P3Base):
    mode = "read_only"

    def test_cancel_and_queue_are_not_exposed(self) -> None:
        job = self.running_job()
        self.open_job(job["id"])
        self.assertFalse(has_button(self.api.sent[-1]["markup"], "Cancel job"))
        self.assertFalse(has_button(self.api.sent[-1]["markup"], "Queue instruction"))
        self.router.handle(message_update(self.next_id(), f"/cancel {job['id']}"))
        self.assertIn("read-only mode", self.api.sent[-1]["text"])
        self.router.handle(message_update(self.next_id(), f"/queue {job['id']}"))
        self.assertIn("read-only mode", self.api.sent[-1]["text"])
        self.assertEqual(self.invocations(), [])


class OwnerMessageTests(P3Base):
    def test_queue_while_running_is_not_live_injection_and_survives_resume(self) -> None:
        job = self.running_job()
        self.queue_instruction(job["id"], "Also update the acceptance notes.")
        self.assertIn("not delivered live", self.api.sent[-1]["text"])
        self.assertEqual(self.state.count_pending_owner_messages(job["id"]), 1)

        # The current attempt ends as FAILED; the queued instruction remains.
        finished = dict(job)
        finished["state"] = "FAILED"
        finished["worker_alive"] = False
        finished["ended_at"] = "2026-11-01T12:30:00Z"
        finished["notifications"] = [{"state": "FAILED", "sent": True, "reason": "sent"}]
        write_fake_jobs(self.state_root, [finished])

        self.router.handle(message_update(self.next_id(), f"/resume {job['id']}"))
        preview = self.api.sent[-1]["text"]
        self.assertIn("Queued instructions for the next resume: 1", preview)
        self.assertIn("Also update the acceptance notes.", preview)
        preview_confirm = find_button(self.api.sent[-1]["markup"], "Confirm resume")
        self.confirm(preview_confirm)
        self.assertIn("Queued instructions included: 1", self.api.edited[-1]["text"])
        confirm = find_button(self.api.edited[-1]["markup"], "Confirm: Resume job")
        self.confirm(confirm)

        records = self.invocations()
        self.assertEqual(len(records), 1)
        args = records[0]["args"]
        self.assertIn("--prompt-file", args)
        self.assertEqual(args[args.index("--prompt-file") + 1], "-")
        self.assertIn("Also update the acceptance notes.", records[0]["stdin"])
        self.assertIn("The owner queued the following follow-up", records[0]["stdin"])

        messages = self.state.list_owner_messages(job["id"])
        self.assertEqual(messages[0]["delivery_state"], "delivered")
        self.assertEqual(messages[0]["delivered_attempt"], 2)
        self.assertEqual(self.state.count_pending_owner_messages(job["id"]), 0)

        self.router.handle(message_update(self.next_id(), f"/messages {job['id']}"))
        self.assertIn("[delivered]", self.api.sent[-1]["text"])
        self.assertIn("attempt #2", self.api.sent[-1]["text"])

    def test_failed_resume_keeps_the_queue_queued(self) -> None:
        job = self.terminal_job()
        self.queue_instruction(job["id"], "Deliver this only after a successful resume.")

        original = self.jobs.resume_job

        def fail_resume(*_args, **_kwargs):
            raise JobError("simulated Workflow v3 refusal")

        self.jobs.resume_job = fail_resume
        try:
            self.router.handle(message_update(self.next_id(), f"/resume {job['id']}"))
            preview_confirm = find_button(self.api.sent[-1]["markup"], "Confirm resume")
            self.confirm(preview_confirm)
            confirm = find_button(self.api.edited[-1]["markup"], "Confirm: Resume job")
            self.confirm(confirm)
        finally:
            self.jobs.resume_job = original

        self.assertIn("Request failed", self.api.edited[-1]["text"])
        messages = self.state.list_owner_messages(job["id"])
        self.assertEqual(messages[0]["delivery_state"], "queued")
        self.assertIn("simulated Workflow v3 refusal", messages[0]["last_error_redacted"])

    def test_messages_are_delivered_once_per_resume(self) -> None:
        job = self.terminal_job()
        self.queue_instruction(job["id"], "First and only delivery.")
        self.router.handle(message_update(self.next_id(), f"/resume {job['id']}"))
        self.confirm(find_button(self.api.sent[-1]["markup"], "Confirm resume"))
        self.confirm(find_button(self.api.edited[-1]["markup"], "Confirm: Resume job"))

        # The fake resume puts the job back into RUNNING. Finish it again.
        finished = self.jobs.job_status(job["id"])
        finished["state"] = "FAILED"
        finished["worker_alive"] = False
        finished["ended_at"] = "2026-11-01T13:00:00Z"
        write_fake_jobs(self.state_root, [finished])

        self.router.handle(message_update(self.next_id(), f"/resume {job['id']}"))
        self.assertIn("Queued instructions: none", self.api.sent[-1]["text"])
        self.assertNotIn("First and only delivery.", self.api.sent[-1]["text"])

    def test_oversized_instruction_is_rejected(self) -> None:
        job = self.terminal_job()
        self.open_job(job["id"])
        self.confirm(find_button(self.api.sent[-1]["markup"], "Queue instruction"))
        self.send_text("x" * (self.config.owner_message_max_chars + 1))
        self.assertIn("Input rejected", self.api.sent[-1]["text"])
        self.assertEqual(self.state.count_pending_owner_messages(job["id"]), 0)

    def test_unknown_session_requires_explicit_new_session(self) -> None:
        job = self.terminal_job(session_id=None)
        self.router.handle(message_update(self.next_id(), f"/resume {job['id']}"))
        confirm_preview = find_button(self.api.sent[-1]["markup"], "Confirm resume")
        self.confirm(confirm_preview)
        self.assertIn("session id is unknown", self.api.edited[-1]["text"])
        self.assertEqual(self.invocations(), [])

        # Start the wizard again and use the explicit New session toggle.
        self.router.handle(message_update(self.next_id(), f"/resume {job['id']}"))
        new_session = find_button(self.api.sent[-1]["markup"], "New session")
        self.confirm(new_session)
        confirm_preview = find_button(self.api.edited[-1]["markup"], "Confirm resume")
        self.confirm(confirm_preview)
        confirm = find_button(self.api.edited[-1]["markup"], "Confirm: Resume job")
        self.confirm(confirm)
        records = self.invocations()
        self.assertEqual(len(records), 1)
        self.assertIn("--new-session", records[0]["args"])


class CancelledLifecycleTests(P3Base):
    def test_cancelled_job_is_a_terminal_notification_state(self) -> None:
        job = make_job(
            "20261101T120000Z-p3-cancelled-55555555",
            state="CANCELLED",
            repo=str(self.project_repo),
            notifications_enabled=False,
            ended_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
        write_fake_jobs(self.state_root, [job])
        sent = self.notifier.poll()
        self.assertIn("TERMINAL:CANCELLED", sent)
        self.assertTrue(any("Job CANCELLED" in item["text"] for item in self.api.sent))
        # Deduplication: a second poll does not send it again.
        sent_again = self.notifier.poll()
        self.assertNotIn("TERMINAL:CANCELLED", sent_again)


if __name__ == "__main__":
    unittest.main()
