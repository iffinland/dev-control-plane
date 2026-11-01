#!/usr/bin/env python3
"""P4 hardening, fault-injection and end-to-end monitor tests.

Every test uses an isolated state directory, a fake Telegram API and a fake
Workflow v3 CLI. No real bot, token, job, OpenCode session, Qortium process or
VPS service is contacted or signalled.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

from devmonitor.admission import AdmissionManager  # noqa: E402
from devmonitor.api import (  # noqa: E402
    TelegramFatalError,
    TelegramRateLimited,
    TelegramTransientError,
)
from devmonitor.config import with_overrides  # noqa: E402
from devmonitor.control import ControlError, ControlManager  # noqa: E402
from devmonitor.documents import (  # noqa: E402
    DocumentError,
    DocumentLibrary,
    DocumentRoot,
    validate_relative,
)
from devmonitor.jobs import JobError, JobFacade  # noqa: E402
from devmonitor.lifecycle import LifecycleNotifier  # noqa: E402
from devmonitor.projects import Registry  # noqa: E402
from devmonitor.router import Router  # noqa: E402
from devmonitor.service import MonitorService  # noqa: E402
from devmonitor.state import MonitorState  # noqa: E402
from devmonitor_test_support import (  # noqa: E402
    CHAT_ID,
    OTHER_CHAT,
    OTHER_USER,
    USER_ID,
    FakeApi,
    callback_update,
    install_fake_dev,
    make_config,
    make_job,
    message_update,
    write_fake_jobs,
)

SECRET = "p4-" + "secret-" + "991122"
CRITERIA = "Build::python3 -m pytest -q"
PROMPT = "Implement the P4 flow safely and preserve the working tree."


def iso_now(offset: int = 0) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + offset))


def find_button(markup, text_fragment: str) -> str:
    for row in (markup or {}).get("inline_keyboard", []):
        for item in row:
            if text_fragment.lower() in item.get("text", "").lower():
                return item["callback_data"]
    raise AssertionError(f"button not found: {text_fragment}")


class P4Base(unittest.TestCase):
    """Control-mode fixture with fake Telegram and fake Workflow v3."""

    monitor_extra: dict | None = None

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="qdm-p4-")
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
        extra = {"terminal_grace_seconds": 0}
        if self.monitor_extra:
            extra.update(self.monitor_extra)
        self.config = make_config(
            self.root,
            mode="control",
            docs_roots=[self.docs],
            repo_roots=[self.projects],
            monitor_extra=extra,
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

    # ---- helpers ---------------------------------------------------------------
    def next_id(self) -> int:
        self.update_id += 1
        return self.update_id

    def send_text(self, value: str, *, user_id: int = USER_ID) -> None:
        self.router.handle(message_update(self.next_id(), value, user_id=user_id))

    def confirm(self, callback_data: str) -> None:
        self.router.handle(callback_update(self.next_id(), callback_data))

    def begin_start(self) -> str:
        self.router.handle(message_update(self.next_id(), "/start_job"))
        callback = find_button(self.api.sent[-1]["markup"], "demo/project")
        self.router.handle(callback_update(self.next_id(), callback))
        return callback.split(":")[1]

    def advance_to_preview(self) -> str:
        self.begin_start()
        self.send_text("P4 hardening job")
        self.send_text(PROMPT)
        self.send_text(CRITERIA)
        self.send_text("2h")
        self.send_text("/skip")
        return find_button(self.api.sent[-1]["markup"], "Confirm: Create job")

    def invocations(self) -> list[dict]:
        path = self.state_root / "fake_invocations.jsonl"
        if not path.is_file():
            return []
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def outbound_texts(self) -> list[str]:
        texts = [str(item.get("text") or "") for item in self.api.sent]
        texts.extend(str(item.get("text") or "") for item in self.api.edited)
        for document in self.api.documents:
            texts.append(str(document.get("caption") or ""))
            texts.append(bytes(document.get("data") or b"").decode("utf-8", "replace"))
        return texts

    def audit_rows(self) -> list[dict]:
        rows = self.state.connection.execute(
            "SELECT action, result, detail_redacted FROM audit ORDER BY id"
        ).fetchall()
        return [dict(row) for row in rows]

    def write_events(self, job_id: str, events: list[tuple[str, str]]) -> None:
        path = self.state_root / "jobs" / job_id / "events.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            for index, (event, detail) in enumerate(events):
                handle.write(
                    json.dumps(
                        {
                            "ts": iso_now(index - len(events)),
                            "event": event,
                            "detail": detail,
                        },
                        sort_keys=True,
                    )
                    + "\n"
                )

    def append_event(self, job_id: str, event: str, detail: str = "") -> None:
        path = self.state_root / "jobs" / job_id / "events.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {"ts": iso_now(), "event": event, "detail": detail},
                    sort_keys=True,
                )
                + "\n"
            )

    def docs_root_id(self) -> str:
        return self.documents.roots[0].root_id


# ---------------------------------------------------------------------------
# Authorization, replay and rate limiting
# ---------------------------------------------------------------------------


class AuthorizationAndReplayTests(P4Base):
    def _write_secret_job(self) -> dict:
        job = make_job(
            "20261101T120000Z-p4-secret-job-11111111",
            title="Owner secret job",
            repo=str(self.project_repo),
        )
        write_fake_jobs(self.state_root, [job])
        return job

    def test_unauthorized_identities_are_denied_without_job_data(self) -> None:
        self._write_secret_job()

        self.router.handle(message_update(10, "/jobs", user_id=999_999))
        self.assertEqual(self.api.sent[-1]["text"], "Access denied.")
        self.assertFalse(any("Owner secret job" in text for text in self.outbound_texts()))

        before = len(self.api.sent)
        self.router.handle(
            message_update(11, "/jobs", user_id=999_999, chat_type="group")
        )
        self.assertEqual(len(self.api.sent), before)

        self.router.handle(message_update(12, "/jobs", user_id=USER_ID, is_bot=True))
        self.assertEqual(self.api.sent[-1]["text"], "Access denied.")

        self.router.handle(
            callback_update(13, "jl:0", user_id=999_999)
        )
        self.assertEqual(self.api.answered[-1]["text"], "Access denied.")
        self.assertFalse(any("Owner secret job" in text for text in self.outbound_texts()))

        # An allowed user in the wrong private chat is still denied, but the
        # denial is generic and contains no job or project data.
        self.router.handle(
            message_update(14, "/jobs", user_id=USER_ID, chat_id=OTHER_CHAT)
        )
        self.assertEqual(self.api.sent[-1]["text"], "Access denied.")
        self.assertFalse(any("Owner secret job" in text for text in self.outbound_texts()))

    def test_duplicate_update_runs_its_action_once(self) -> None:
        service = MonitorService(
            self.config,
            self.api,
            self.state,
            self.router,
            lifecycle=None,
            sleep=lambda _seconds: None,
            clock=lambda: 0.0,
        )
        update = message_update(20, "/jobs")
        service.process_update(update)
        sent_after_first = len(self.api.sent)
        service.process_update(dict(update))
        self.assertEqual(len(self.api.sent), sent_after_first)
        self.assertEqual(self.state.next_offset(), 21)

    def test_confirmation_nonces_are_single_use_across_connections(self) -> None:
        nonce = self.state.create_confirmation(
            USER_ID, CHAT_ID, "start_job", {"wizard_id": "w1"}
        )
        self.assertEqual(
            self.state.consume_confirmation(nonce, USER_ID, CHAT_ID, "start_job"),
            {"wizard_id": "w1"},
        )
        self.assertIsNone(
            self.state.consume_confirmation(nonce, USER_ID, CHAT_ID, "start_job")
        )

        other = MonitorState(self.root / "monitor" / "monitor.db")
        try:
            second = self.state.create_confirmation(
                USER_ID, CHAT_ID, "cancel_job", {"job_id": "j1"}
            )
            self.assertEqual(
                self.state.consume_confirmation(
                    second, USER_ID, CHAT_ID, "cancel_job"
                ),
                {"job_id": "j1"},
            )
            # A second writer connection sees the durable used_at marker.
            self.assertIsNone(
                other.consume_confirmation(second, USER_ID, CHAT_ID, "cancel_job")
            )
        finally:
            other.close()

    def test_confirmation_rejects_wrong_owner_action_and_expiry(self) -> None:
        nonce = self.state.create_confirmation(
            USER_ID, CHAT_ID, "start_job", {"wizard_id": "w1"}
        )
        self.assertIsNone(
            self.state.consume_confirmation(nonce, OTHER_USER, CHAT_ID, "start_job")
        )
        self.assertIsNone(
            self.state.consume_confirmation(nonce, USER_ID, CHAT_ID, "cancel_job")
        )

        expiring = self.state.create_confirmation(
            USER_ID, CHAT_ID, "cancel_job", {"job_id": "j2"}, ttl_seconds=1
        )
        original_clock = self.state.clock
        self.state.clock = lambda: int(time.time()) + 100
        try:
            self.assertIsNone(
                self.state.consume_confirmation(
                    expiring, USER_ID, CHAT_ID, "cancel_job"
                )
            )
        finally:
            self.state.clock = original_clock


class RateLimitTests(P4Base):
    monitor_extra = {
        "max_actions_per_minute": 2,
        "max_actions_per_chat_per_minute": 100,
    }

    def test_per_user_action_rate_limit(self) -> None:
        self.send_text("/start")
        self.send_text("/start")
        self.send_text("/start")
        self.assertIn("Rate limit exceeded", self.api.sent[-1]["text"])
        self.assertTrue(
            any(row["detail_redacted"] == "user" for row in self.audit_rows())
        )


class PerChatRateLimitTests(P4Base):
    monitor_extra = {
        "authorized_user_ids": [USER_ID, OTHER_USER],
        "max_actions_per_minute": 100,
        "max_actions_per_chat_per_minute": 2,
    }

    def test_per_chat_rate_limit_applies_across_users(self) -> None:
        self.send_text("/start", user_id=USER_ID)
        self.send_text("/start", user_id=USER_ID)
        self.send_text("/start", user_id=OTHER_USER)
        self.assertIn("Rate limit exceeded", self.api.sent[-1]["text"])
        self.assertTrue(
            any(row["detail_redacted"] == "chat" for row in self.audit_rows())
        )


class StartRateLimitTests(P4Base):
    monitor_extra = {"max_starts_per_hour": 1}

    def test_hourly_start_cap_refuses_a_second_start_before_cli(self) -> None:
        confirm = self.advance_to_preview()
        self.confirm(confirm)
        self.assertEqual(len(self.invocations()), 1)

        # End the first job so the project admission rule is not the reason.
        write_fake_jobs(self.state_root, [])

        confirm = self.advance_to_preview()
        self.confirm(confirm)
        self.assertIn("start rate limit reached", self.api.edited[-1]["text"])
        starts = [item for item in self.invocations() if item["args"][:1] == ["start"]]
        self.assertEqual(len(starts), 1)


# ---------------------------------------------------------------------------
# Redaction at every outbound and persistence boundary
# ---------------------------------------------------------------------------


class RedactionTests(P4Base):
    def test_lifecycle_messages_redact_job_derived_fields(self) -> None:
        job = make_job(
            "20261101T120000Z-p4-redact-life-22222222",
            title=f"Job pass{'word'}={SECRET}",
            repo=str(self.project_repo),
            state="RUNNING",
            notifications_enabled=False,
        )
        write_fake_jobs(self.state_root, [job])
        self.write_events(
            job["id"],
            [("worker_error", f"failure token={SECRET}")],
        )
        self.state.set_meta("lifecycle_initialized", "1")
        self.notifier.poll()

        finished = dict(job)
        finished["state"] = "FAILED"
        finished["worker_alive"] = False
        finished["ended_at"] = iso_now()
        finished["blocker"] = f"token={SECRET}"
        write_fake_jobs(self.state_root, [finished])
        self.append_event(job["id"], "finished", "state=FAILED exit=1")
        self.notifier.poll()

        texts = self.outbound_texts()
        self.assertTrue(any("WORKER ERROR" in text for text in texts))
        self.assertTrue(any("Job FAILED" in text for text in texts))
        self.assertFalse(any(SECRET in text for text in texts))

    def test_logs_reports_errors_and_audit_are_redacted(self) -> None:
        job = make_job(
            "20261101T120000Z-p4-redact-job-33333333",
            title="Redaction job",
            repo=str(self.project_repo),
        )
        write_fake_jobs(self.state_root, [job])
        directory = self.state_root / "jobs" / job["id"]
        (directory / "run.log").write_text(
            "ok\n" + "pass" + "word=" + SECRET + "\n", encoding="utf-8"
        )
        (directory / "report.md").write_text(
            "# Report\n\n" + "token=" + SECRET + "\n", encoding="utf-8"
        )

        self.router.handle(message_update(self.next_id(), f"/job {job['id']}"))
        run_log = find_button(self.api.sent[-1]["markup"], "Run log")
        self.confirm(run_log)
        self.assertIn("run log", self.api.edited[-1]["text"].lower())

        self.router.handle(message_update(self.next_id(), f"/job {job['id']}"))
        report = find_button(self.api.sent[-1]["markup"], "Report")
        self.confirm(report)

        self.router.handle(message_update(self.next_id(), f"/job {job['id']}"))
        download = find_button(self.api.sent[-1]["markup"], "Download report")
        self.confirm(download)

        self.assertFalse(any(SECRET in text for text in self.outbound_texts()))

        original = self.jobs.job_status

        def fail_status(_job_id):
            raise JobError(f"Workflow v3 failed token={SECRET}")

        self.jobs.job_status = fail_status
        try:
            self.router.handle(
                message_update(self.next_id(), f"/job {job['id']}")
            )
        finally:
            self.jobs.job_status = original
        self.assertIn("Request failed", self.api.sent[-1]["text"])
        self.assertNotIn(SECRET, self.api.sent[-1]["text"])

        self.state.record_audit(
            "redaction_test", "error", detail=f"pass{'word'}={SECRET}"
        )
        self.assertFalse(
            any(SECRET in str(row["detail_redacted"]) for row in self.audit_rows())
        )

    def test_cli_error_text_is_redacted(self) -> None:
        bad_dev = self.root / "bad_dev.py"
        bad_dev.write_text(
            "import sys\n"
            f"print('failure token={SECRET}', file=sys.stderr)\n"
            "sys.exit(2)\n",
            encoding="utf-8",
        )
        facade = JobFacade(self.state_root, dev_script=bad_dev)
        with self.assertRaises(JobError) as raised:
            facade.list_jobs()
        self.assertNotIn(SECRET, str(raised.exception))
        self.assertIn("<redacted>", str(raised.exception))


# ---------------------------------------------------------------------------
# Document resolver hardening
# ---------------------------------------------------------------------------


class DocumentHardeningTests(P4Base):
    def setUp(self) -> None:
        super().setUp()
        self.library = DocumentLibrary([DocumentRoot("docs", "docs", self.docs)])
        self.root_id = self.library.roots[0].root_id
        (self.docs / "ok.md").write_text("# ok\n", encoding="utf-8")
        (self.docs / "nested").mkdir()
        (self.docs / "nested" / "note.txt").write_text("note\n", encoding="utf-8")

    def test_traversal_absolute_and_encoded_paths_are_refused(self) -> None:
        malicious = [
            "/etc/passwd",
            "../outside",
            "a/../../b",
            "a/./b",
            "a//b",
            "a\\b",
            "a%2f..%2fb",
            "..%2fetc%2fpasswd",
            "a\x00b",
            ".",
            "..",
            "",
            ".git/config",
            ".env",
            "secrets",
            "credentials",
            "id_rsa",
            "id_ed25519",
            "/".join(["x"] * 40),
        ]
        for value in malicious:
            with self.assertRaises(DocumentError, msg=repr(value)):
                validate_relative(value)

    def test_listing_excludes_hidden_symlinks_sensitive_and_special_files(self) -> None:
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "secret.md").write_text(SECRET, encoding="utf-8")
        (self.docs / ".git").mkdir()
        (self.docs / ".env").write_text("TOKEN=x\n", encoding="utf-8")
        (self.docs / "secret.pem").write_text("key\n", encoding="utf-8")
        (self.docs / "secrets").mkdir()
        os.mkfifo(self.docs / "pipe")
        os.symlink(outside / "secret.md", self.docs / "link.md")
        os.symlink(outside, self.docs / "linkdir")

        listing = self.library.list_dir(self.root_id, "", 0)
        names = {entry.name for entry in listing.entries}
        self.assertEqual(names, {"ok.md", "nested"})
        for ref in ("link.md", "linkdir/secret.md", "secret.pem", ".env", "pipe"):
            with self.assertRaises(DocumentError):
                self.library.preview(self.root_id, ref, 1024)
        with self.assertRaises(DocumentError):
            self.library.open_download(self.root_id, "pipe", 1024)

    def test_symlink_swap_between_listing_and_open_is_refused(self) -> None:
        outside = self.root / "outside-secret.md"
        outside.write_text(SECRET, encoding="utf-8")
        target = self.docs / "swap.md"
        target.write_text("safe contents\n", encoding="utf-8")
        self.assertIn("swap.md", {item.name for item in self.library.list_dir(self.root_id).entries})

        target.unlink()
        os.symlink(outside, target)
        with self.assertRaises(DocumentError):
            self.library.preview(self.root_id, "swap.md", 1024)

    def test_symlinked_root_is_refused(self) -> None:
        alias = self.root / "docs-alias"
        os.symlink(self.docs, alias)
        library = DocumentLibrary([DocumentRoot("alias", "alias", alias)])
        with self.assertRaises(DocumentError):
            library.list_dir(library.roots[0].root_id, "", 0)

    def test_text_preview_and_download_are_redacted_and_source_is_unchanged(self) -> None:
        path = self.docs / "secrets-note.md"
        original = ("line one\n" + "pass" + "word=" + SECRET + "\n").encode()
        path.write_bytes(original)
        before = (path.stat().st_size, hashlib.sha256(path.read_bytes()).hexdigest())

        preview = self.library.preview(self.root_id, "secrets-note.md", 4096, (SECRET,))
        self.assertNotIn(SECRET, preview.text)
        self.assertIn("<redacted>", preview.text)

        download = self.library.open_download(
            self.root_id, "secrets-note.md", 4096, secrets=(SECRET,)
        )
        payload = download.data.decode("utf-8")
        self.assertNotIn(SECRET, payload)
        self.assertIn(".redacted", download.name)
        self.assertTrue(download.is_text)
        self.assertEqual(
            (path.stat().st_size, hashlib.sha256(path.read_bytes()).hexdigest()),
            before,
        )

    def test_size_caps_and_binary_policy(self) -> None:
        (self.docs / "big.txt").write_text("x" * 64, encoding="utf-8")
        with self.assertRaises(DocumentError):
            self.library.preview(self.root_id, "big.txt", 16)

        (self.docs / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00binary")
        with self.assertRaises(DocumentError):
            self.library.preview(self.root_id, "image.png", 4096)
        with self.assertRaises(DocumentError):
            self.library.open_download(self.root_id, "image.png", 4096)
        download = self.library.open_download(
            self.root_id, "image.png", 4096, allow_binary=True
        )
        self.assertFalse(download.is_text)
        self.assertFalse(download.redacted)
        self.assertEqual(download.media_type, "image/png")

    def test_browsing_does_not_mutate_the_tree(self) -> None:
        path = self.docs / "ok.md"
        before = (path.stat().st_size, path.stat().st_mtime_ns, path.read_bytes())
        self.library.list_dir(self.root_id, "", 0)
        self.library.preview(self.root_id, "ok.md", 4096)
        self.library.open_download(self.root_id, "ok.md", 4096)
        after = (path.stat().st_size, path.stat().st_mtime_ns, path.read_bytes())
        self.assertEqual(before, after)


# ---------------------------------------------------------------------------
# Persistence, polling recovery and concurrency protection
# ---------------------------------------------------------------------------


class PersistenceAndFaultTests(P4Base):
    def test_restart_preserves_offset_seen_updates_nonces_and_queue(self) -> None:
        self.state.set_offset(42)
        self.assertTrue(self.state.claim_update(42))
        nonce = self.state.create_confirmation(
            USER_ID, CHAT_ID, "start_job", {"wizard_id": "restart"}
        )
        message_id = self.state.add_owner_message(
            "20261101T120000Z-p4-persist-44444444",
            USER_ID,
            CHAT_ID,
            "survive restart",
        )

        database = self.root / "monitor" / "monitor.db"
        self.state.close()
        self.state = MonitorState(database)

        self.assertEqual(self.state.next_offset(), 42)
        self.assertFalse(self.state.claim_update(42))
        self.assertEqual(
            self.state.consume_confirmation(nonce, USER_ID, CHAT_ID, "start_job"),
            {"wizard_id": "restart"},
        )
        pending = self.state.list_owner_messages(
            "20261101T120000Z-p4-persist-44444444", pending_only=True
        )
        self.assertEqual([item["message_id"] for item in pending], [message_id])
        self.assertEqual(pending[0]["body"], "survive restart")

    def test_notification_dedupe_survives_restart(self) -> None:
        job = make_job(
            "20261101T120000Z-p4-dedupe-55555555",
            repo=str(self.project_repo),
        )
        write_fake_jobs(self.state_root, [job])
        self.write_events(
            job["id"],
            [("worker_started", "pid=1"), ("attempt_started", "attempt=1 resume=False")],
        )
        self.assertEqual(self.notifier.poll(), ["STARTED"])
        before = len(self.api.sent)

        restarted = LifecycleNotifier(
            self.config, self.state, self.jobs, self.api, self.registry
        )
        self.assertEqual(restarted.poll(), [])
        self.assertEqual(len(self.api.sent), before)

    def test_polling_recovers_from_transient_and_rate_limit_without_losing_updates(self) -> None:
        self.api.updates = [[message_update(30, "/start")]]
        self.api.faults = [
            TelegramTransientError("temporary network failure"),
            TelegramRateLimited("slow down", retry_after=1.0),
        ]
        sleeps: list[float] = []
        service = MonitorService(
            self.config,
            self.api,
            self.state,
            self.router,
            lifecycle=None,
            sleep=sleeps.append,
            clock=lambda: 0.0,
        )
        service.run(max_iterations=4)
        self.assertEqual(self.state.next_offset(), 31)
        self.assertTrue(
            any("Qortium Dev Monitor" in item["text"] for item in self.api.sent)
        )
        self.assertTrue(any(value == 1.0 for value in sleeps))
        self.assertTrue(any(0.5 <= value <= 1.5 for value in sleeps))

    def test_fatal_poll_error_stops_without_advancing_offset(self) -> None:
        api = FakeApi()
        api.faults = [TelegramFatalError("401 unauthorized")]
        service = MonitorService(
            self.config,
            api,
            self.state,
            self.router,
            lifecycle=None,
            sleep=lambda _seconds: None,
            clock=lambda: 0.0,
        )
        with self.assertRaises(TelegramFatalError):
            service.run(max_iterations=1)
        self.assertEqual(self.state.next_offset(), 0)

    def test_transient_action_failure_releases_the_update_for_retry(self) -> None:
        service = MonitorService(
            self.config,
            self.api,
            self.state,
            self.router,
            lifecycle=None,
            sleep=lambda _seconds: None,
            clock=lambda: 0.0,
        )
        update = message_update(40, "/start")
        original = self.router.handle
        calls = {"count": 0}

        def flaky(value):
            calls["count"] += 1
            if calls["count"] == 1:
                raise TelegramTransientError("outbound failure")
            return original(value)

        self.router.handle = flaky
        try:
            with self.assertRaises(TelegramTransientError):
                service.process_update(update)
            self.assertEqual(self.state.next_offset(), 0)
            service.process_update(update)
        finally:
            self.router.handle = original

        self.assertEqual(calls["count"], 2)
        self.assertEqual(self.state.next_offset(), 41)
        self.assertTrue(any("Qortium Dev Monitor" in item["text"] for item in self.api.sent))

    def test_job_directory_symlink_is_refused(self) -> None:
        job_id = "20261101T120000Z-p4-symlink-66666666"
        outside = self.root / "outside-job"
        outside.mkdir()
        (outside / "job.json").write_text("{}", encoding="utf-8")
        jobs_dir = self.state_root / "jobs"
        jobs_dir.mkdir(parents=True, exist_ok=True)
        os.symlink(outside, jobs_dir / job_id)
        with self.assertRaises(JobError):
            self.jobs.job_dir(job_id)
        with self.assertRaises(JobError):
            self.jobs.job_log(job_id, "run")


# ---------------------------------------------------------------------------
# Control flow integration: start, queue, cancel, resume
# ---------------------------------------------------------------------------


class ControlFlowIntegrationTests(P4Base):
    def test_start_queue_cancel_resume_with_fake_cli(self) -> None:
        confirm = self.advance_to_preview()
        self.confirm(confirm)
        jobs = self.jobs.list_jobs()
        self.assertEqual(len(jobs), 1)
        job_id = jobs[0]["id"]
        self.assertEqual(jobs[0]["state"], "RUNNING")
        self.assertTrue(any("STARTED" in text for text in self.outbound_texts()))

        self.router.handle(message_update(self.next_id(), f"/job {job_id}"))
        queue_button = find_button(self.api.sent[-1]["markup"], "Queue instruction")
        self.confirm(queue_button)
        self.send_text("Also update the acceptance notes.")
        self.assertEqual(self.state.count_pending_owner_messages(job_id), 1)

        self.router.handle(message_update(self.next_id(), f"/cancel {job_id}"))
        cancel_confirm = find_button(
            self.api.sent[-1]["markup"], "Confirm: Cancel running job"
        )
        self.confirm(cancel_confirm)
        self.assertEqual(self.jobs.job_status(job_id)["state"], "CANCELLED")

        self.router.handle(message_update(self.next_id(), f"/resume {job_id}"))
        preview_confirm = find_button(self.api.sent[-1]["markup"], "Confirm resume")
        self.confirm(preview_confirm)
        final_confirm = find_button(
            self.api.edited[-1]["markup"], "Confirm: Resume job"
        )
        self.confirm(final_confirm)

        args = [item["args"] for item in self.invocations()]
        self.assertEqual([item[0] for item in args], ["start", "cancel", "resume"])
        resume = self.invocations()[-1]
        self.assertIn("--prompt-file", resume["args"])
        self.assertIn("Also update the acceptance notes.", resume["stdin"])
        self.assertIn("owner queued the following follow-up", resume["stdin"])

        messages = self.state.list_owner_messages(job_id)
        self.assertEqual(messages[0]["delivery_state"], "delivered")
        self.assertEqual(messages[0]["delivered_attempt"], 2)
        self.assertEqual(self.state.count_pending_owner_messages(job_id), 0)
        self.assertTrue(any("RESUMED" in text for text in self.outbound_texts()))

    def test_cancel_revalidates_running_state_before_signal(self) -> None:
        job = make_job(
            "20261101T120000Z-p4-cancel-state-77777777",
            repo=str(self.project_repo),
            state="FAILED",
        )
        write_fake_jobs(self.state_root, [job])
        payload = {"job_id": job["id"]}
        with self.assertRaises((JobError, ControlError)):
            self.control.perform_cancel(payload, type("D", (), {"chat_id": CHAT_ID})())
        # The monitor itself never signals; the additive CLI revalidated and
        # refused the terminal job without changing its state.
        self.assertEqual([item["args"][0] for item in self.invocations()], ["cancel"])
        self.assertEqual(self.jobs.job_status(job["id"])["state"], "FAILED")


if __name__ == "__main__":
    unittest.main()
