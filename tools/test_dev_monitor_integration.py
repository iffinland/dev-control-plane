#!/usr/bin/env python3
"""End-to-end read-only monitor routing, polling and safety tests.

All Telegram traffic is an in-memory fake. Workflow v3 is a fake dev CLI in an
isolated state directory. No real token, network request, job or document tree is
used.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

from devmonitor.api import TelegramRateLimited, TelegramStaleCallback  # noqa: E402
from devmonitor.config import ConfigError, load_monitor_config, with_overrides  # noqa: E402
from devmonitor.documents import DocumentLibrary  # noqa: E402
from devmonitor.jobs import JobFacade  # noqa: E402
from devmonitor.projects import Registry  # noqa: E402
from devmonitor.router import Router  # noqa: E402
from devmonitor.service import MonitorService, check_monitor  # noqa: E402
from devmonitor.state import MonitorState  # noqa: E402
from devmonitor_test_support import (  # noqa: E402
    BOT_TOKEN,
    CHAT_ID,
    OTHER_CHAT,
    OTHER_USER,
    FakeApi,
    callback_update,
    install_fake_dev,
    make_config,
    make_job,
    message_update,
    write_fake_jobs,
)

SECRET = "doc-" + "secret-" + "445566"


def find_button(markup, text_fragment: str) -> str:
    for row in (markup or {}).get("inline_keyboard", []):
        for item in row:
            if text_fragment.lower() in item.get("text", "").lower():
                return item["callback_data"]
    raise AssertionError(f"button not found: {text_fragment}")


class VirtualClock:
    def __init__(self) -> None:
        self.now = 0.0


class ExpiringBatchApi(FakeApi):
    """Fake API where building a response consumes callback validity time."""

    def __init__(self, clock: VirtualClock, *, deadline: float = 5.0, handler_cost: float = 10.0):
        super().__init__()
        self.clock = clock
        self.deadline = deadline
        self.handler_cost = handler_cost

    def answer_callback_query(self, callback_query_id: str, text: str | None = None) -> bool:
        if self.clock.now > self.deadline:
            raise TelegramStaleCallback(
                "Bad Request: query is too old and response timeout expired or "
                "query ID is invalid"
            )
        return super().answer_callback_query(callback_query_id, text)

    def edit_message_text(self, chat_id, message_id, text, reply_markup=None):
        self.clock.now += self.handler_cost
        return super().edit_message_text(chat_id, message_id, text, reply_markup)


class StaleAckApi(FakeApi):
    """Fake API that rejects every callback acknowledgement as expired."""

    def __init__(self) -> None:
        super().__init__()
        self.ack_attempts: list[str] = []

    def answer_callback_query(self, callback_query_id: str, text: str | None = None) -> bool:
        self.ack_attempts.append(callback_query_id)
        raise TelegramStaleCallback(
            "Bad Request: query is too old and response timeout expired or query ID is invalid"
        )


class MonitorIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="qdm-int-")
        self.root = Path(self.temporary.name)
        self.projects = self.root / "projects"
        self.projects.mkdir()
        (self.projects / "Demo").mkdir()
        self.docs = self.root / "docs"
        (self.docs / "reports").mkdir(parents=True)
        (self.docs / "reports" / "note.md").write_text(
            "# Note\n\n" + "pass" + "word=" + SECRET + "\n", encoding="utf-8"
        )
        (self.docs / "reports" / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n\x00data")
        self.registry_file = self.root / "PROJECT-REGISTRY.md"
        self.registry_file.write_text(
            "# Project registry\n\n## Registered projects\n\n"
            "| ID | Platform | Verified local path | Project-level `AGENTS.md` | Canonical context | Central report root |\n"
            "| --- | --- | --- | --- | --- | --- |\n"
            f"| `demo/project` | Qortal | `{self.projects / 'Demo'}` | Yes | Pending | `{self.docs}/` |\n",
            encoding="utf-8",
        )
        self.state_root = self.root / "state"
        self.running = make_job("20261031T120000Z-demo-job-abcd1234")
        write_fake_jobs(self.state_root, [self.running])
        (self.state_root / "jobs" / self.running["id"] / "run.log").write_text(
            "\n".join(f"line {index}" for index in range(150))
            + "\n"
            + "pass" + "word=" + SECRET
            + "\n",
            encoding="utf-8",
        )
        (self.state_root / "jobs" / self.running["id"] / "report.md").write_text(
            "# Report\n\n" + "pass" + "word=" + SECRET + "\n", encoding="utf-8"
        )
        self.config = make_config(
            self.root,
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
        self.jobs = JobFacade(
            self.state_root, dev_script=install_fake_dev(self.root)
        )
        self.router = Router(
            self.config, self.state, self.api, self.jobs, self.registry, self.documents
        )

    def tearDown(self) -> None:
        self.state.close()
        self.temporary.cleanup()

    # ---- authorization and menu --------------------------------------------------
    def test_authorized_start_returns_main_menu(self) -> None:
        self.router.handle(message_update(1, "/start"))
        self.assertEqual(len(self.api.sent), 1)
        self.assertIn("Qortium Dev Monitor", self.api.sent[0]["text"])
        callbacks = [
            item["callback_data"]
            for row in self.api.sent[0]["markup"]["inline_keyboard"]
            for item in row
        ]
        self.assertIn("jl:0", callbacks)

    def test_unknown_user_gets_generic_denial_without_job_data(self) -> None:
        self.router.handle(message_update(1, "/jobs", user_id=OTHER_USER))
        self.assertEqual(len(self.api.sent), 1)
        self.assertEqual(self.api.sent[0]["text"], "Access denied.")
        self.assertNotIn("RUNNING", self.api.sent[0]["text"])

    def test_group_message_is_rejected_without_reply(self) -> None:
        self.router.handle(message_update(1, "/jobs", chat_id=OTHER_CHAT, chat_type="group"))
        self.assertEqual(self.api.sent, [])

    def test_unauthorized_callback_is_rejected_before_state_lookup(self) -> None:
        self.router.handle(callback_update(2, "m", user_id=OTHER_USER))
        self.assertEqual(self.api.edited, [])
        self.assertEqual(self.api.answered[-1]["text"], "Access denied.")

    def test_help_and_unknown_commands(self) -> None:
        self.router.handle(message_update(1, "/help"))
        self.assertIn("Commands", self.api.sent[-1]["text"])
        self.router.handle(message_update(2, "/nonsense"))
        self.assertIn("Unknown command", self.api.sent[-1]["text"])

    def test_control_commands_are_disabled_in_p1(self) -> None:
        self.router.handle(message_update(1, "/resume"))
        self.assertIn("not available in P1", self.api.sent[-1]["text"])
        self.assertNotIn(SECRET, self.api.sent[-1]["text"])

    # ---- jobs --------------------------------------------------------------------
    def test_job_list_status_logs_and_report(self) -> None:
        self.router.handle(message_update(1, "/jobs"))
        job_button = find_button(self.api.sent[-1]["markup"], "RUNNING")
        self.router.handle(callback_update(2, job_button))
        status_text = self.api.edited[-1]["text"]
        self.assertIn("State: RUNNING", status_text)
        self.assertIn("PIDs:", status_text)
        self.assertNotIn(str(self.state_root), status_text)
        self.assertNotIn("job.json", status_text)
        ref = job_button.split(":")[1]

        self.router.handle(callback_update(3, f"j:{ref}:lr"))
        log_text = self.api.edited[-1]["text"]
        self.assertNotIn(SECRET, log_text)
        self.assertIn("line 149", log_text)
        self.assertLessEqual(len(log_text.splitlines()), 120)

        self.router.handle(callback_update(4, f"j:{ref}:p"))
        self.assertIn("# Report", self.api.edited[-1]["text"])
        self.assertNotIn(SECRET, self.api.edited[-1]["text"])

        self.router.handle(callback_update(5, f"j:{ref}:dr"))
        self.assertTrue(self.api.documents)
        self.assertNotIn(SECRET.encode(), self.api.documents[-1]["data"])
        self.assertIn(".redacted", self.api.documents[-1]["filename"])

    def test_job_download_log(self) -> None:
        self.router.handle(message_update(1, "/jobs"))
        job_button = find_button(self.api.sent[-1]["markup"], "RUNNING")
        ref = job_button.split(":")[1]
        self.router.handle(callback_update(2, f"j:{ref}:dlr"))
        self.assertTrue(self.api.documents)
        self.assertNotIn(SECRET.encode(), self.api.documents[-1]["data"])

    # ---- projects and docs -------------------------------------------------------
    def test_projects_listing(self) -> None:
        self.router.handle(message_update(1, "/projects"))
        text = self.api.sent[-1]["text"]
        self.assertIn("demo/project", text)
        self.assertIn("repo ok", text)
        self.assertIn("P1 does not start jobs", text)

    def test_document_browse_preview_and_redacted_download(self) -> None:
        self.router.handle(message_update(1, "/docs"))
        root_callback = self.api.sent[-1]["markup"]["inline_keyboard"][0][0]["callback_data"]
        self.router.handle(callback_update(2, root_callback))
        reports_callback = find_button(self.api.edited[-1]["markup"], "reports")
        self.router.handle(callback_update(3, reports_callback))
        note_callback = find_button(self.api.edited[-1]["markup"], "note.md")
        self.router.handle(callback_update(4, note_callback.replace(":o:", ":v:")))
        preview_text = self.api.edited[-1]["text"]
        self.assertIn("Redacted text preview", preview_text)
        self.assertNotIn(SECRET, preview_text)

        download_callback = find_button(self.api.edited[-1]["markup"], "Download redacted")
        self.router.handle(callback_update(5, download_callback))
        self.assertTrue(self.api.documents)
        self.assertNotIn(SECRET.encode(), self.api.documents[-1]["data"])
        self.assertIn(".redacted", self.api.documents[-1]["filename"])

    def test_binary_download_is_disabled(self) -> None:
        self.router.handle(message_update(1, "/docs"))
        root_callback = self.api.sent[-1]["markup"]["inline_keyboard"][0][0]["callback_data"]
        self.router.handle(callback_update(2, root_callback))
        reports_callback = find_button(self.api.edited[-1]["markup"], "reports")
        self.router.handle(callback_update(3, reports_callback))
        image_callback = find_button(self.api.edited[-1]["markup"], "image.png")
        self.router.handle(callback_update(4, image_callback.replace(":v:", ":d:")))
        self.assertIn("Binary downloads are disabled", self.api.edited[-1]["text"])
        self.assertEqual(self.api.documents, [])

    def test_expired_or_foreign_browse_reference_is_refused(self) -> None:
        browse_id = self.state.create_browse(OTHER_USER, CHAT_ID, "docs", "", 0)
        self.router.handle(callback_update(2, f"b:{browse_id}"))
        self.assertIn("expired", self.api.edited[-1]["text"].lower())

    # ---- polling, offsets and resilience ----------------------------------------
    def test_service_deduplicates_updates_and_persists_offset(self) -> None:
        update = message_update(10, "/start")
        self.api.updates = [[update]]
        sleeps: list[float] = []
        service = MonitorService(
            self.config, self.api, self.state, self.router, sleep=sleeps.append
        )
        service.run(max_iterations=1)
        self.assertEqual(len(self.api.sent), 1)
        self.assertEqual(self.state.next_offset(), 11)

        service.process_update(update)
        self.assertEqual(len(self.api.sent), 1)
        self.assertEqual(self.api.get_updates_calls[0]["offset"], 0)

    def test_service_honors_429_without_dropping_the_update(self) -> None:
        update = message_update(20, "/start")
        self.api.updates = [[update]]
        self.api.faults = [TelegramRateLimited("slow down", 2)]
        sleeps: list[float] = []
        service = MonitorService(
            self.config, self.api, self.state, self.router, sleep=sleeps.append
        )
        service.run(max_iterations=2)
        self.assertEqual(len(self.api.sent), 1)
        self.assertIn(2.0, sleeps)
        self.assertEqual(self.state.next_offset(), 21)

    def _components_with(self, api):
        router = Router(
            self.config, self.state, api, self.jobs, self.registry, self.documents
        )
        service = MonitorService(
            self.config, api, self.state, router, sleep=lambda _value: None
        )
        return router, service

    def _audit_rows(self) -> list[tuple[str, str]]:
        rows = self.state.connection.execute(
            "SELECT action, result FROM audit ORDER BY id"
        ).fetchall()
        return [(str(row["action"]), str(row["result"])) for row in rows]

    def test_slow_handler_does_not_expire_other_callbacks_in_batch(self) -> None:
        clock = VirtualClock()
        api = ExpiringBatchApi(clock)
        _router, service = self._components_with(api)
        api.updates = [[callback_update(100, "jl:0"), callback_update(101, "h")]]
        service.run(max_iterations=1)
        self.assertEqual([item["id"] for item in api.answered], ["cb-100", "cb-101"])
        self.assertEqual(len(api.edited), 2)
        self.assertEqual(self.state.next_offset(), 102)
        self.assertNotIn(("update_dead_letter", "error"), self._audit_rows())

    def test_expired_callback_ack_still_runs_every_menu_action(self) -> None:
        api = StaleAckApi()
        _router, service = self._components_with(api)
        for index, action in enumerate(["jl:0", "p", "d", "h"], start=200):
            service.process_update(callback_update(index, action))
        self.assertEqual(api.ack_attempts, [f"cb-{index}" for index in range(200, 204)])
        self.assertEqual(len(api.edited), 4)
        self.assertEqual(self.state.next_offset(), 204)
        audits = self._audit_rows()
        self.assertNotIn(("update_dead_letter", "error"), audits)
        self.assertTrue(
            any(action == "callback_ack" and result == "stale" for action, result in audits)
        )

    def test_duplicate_callback_update_runs_action_once(self) -> None:
        api = StaleAckApi()
        _router, service = self._components_with(api)
        update = callback_update(300, "h")
        service.process_update(update)
        service.process_update(update)
        self.assertEqual(len(api.edited), 1)
        self.assertEqual(api.ack_attempts, ["cb-300"])
        self.assertEqual(self.state.next_offset(), 301)
        self.assertNotIn(("update_dead_letter", "error"), self._audit_rows())

    def test_duplicate_after_restart_acknowledges_without_repeating_action(self) -> None:
        first_api = FakeApi()
        _first_router, first_service = self._components_with(first_api)
        update = callback_update(400, "h")
        first_service.process_update(update)
        self.assertEqual(len(first_api.edited), 1)

        restarted_api = StaleAckApi()
        _restarted_router, restarted_service = self._components_with(restarted_api)
        restarted_service.process_update(update)
        self.assertEqual(restarted_api.ack_attempts, ["cb-400"])
        self.assertEqual(restarted_api.edited, [])
        self.assertEqual(self.state.next_offset(), 401)
        self.assertNotIn(("update_dead_letter", "error"), self._audit_rows())

    def test_stop_flag_stops_between_iterations(self) -> None:
        self.api.updates = [[message_update(30, "/start")]]
        service = MonitorService(
            self.config, self.api, self.state, self.router, sleep=lambda _value: None
        )

        def _sleep_then_stop(delay: float) -> None:
            service.request_stop()

        service.sleep = _sleep_then_stop
        service.run(max_iterations=5)
        self.assertEqual(len(self.api.get_updates_calls), 1)
        self.assertEqual(len(self.api.sent), 1)

    def test_check_fails_closed_on_configured_webhook(self) -> None:
        self.api.webhook = {"url": "https://example.invalid/hook"}
        ok, lines = check_monitor(self.config, self.api, self.registry, self.documents)
        self.assertFalse(ok)
        self.assertTrue(any("webhook is configured" in line for line in lines))

    def test_check_passes_with_fake_telegram(self) -> None:
        ok, lines = check_monitor(self.config, self.api, self.registry, self.documents)
        self.assertTrue(ok, "\n".join(lines))
        self.assertTrue(any("telegram getMe: ok" in line for line in lines))
        self.assertTrue(any("registry: ok" in line for line in lines))

    # ---- configuration -----------------------------------------------------------
    def test_insecure_config_permissions_are_refused(self) -> None:
        path = self.root / "telegram.json"
        os.chmod(path, 0o644)
        with self.assertRaises(ConfigError):
            load_monitor_config(path, environ={}, require_secure=True)

    def test_missing_allowlist_or_token_is_refused(self) -> None:
        path = self.root / "telegram.json"
        import json

        data = json.loads(path.read_text(encoding="utf-8"))
        data["monitor"]["authorized_user_ids"] = []
        path.write_text(json.dumps(data), encoding="utf-8")
        os.chmod(path, 0o600)
        with self.assertRaises(ConfigError):
            load_monitor_config(path, environ={}, require_secure=True)
        data["monitor"]["authorized_user_ids"] = [1]
        data["bot_token"] = ""
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaises(ConfigError):
            load_monitor_config(path, environ={}, require_secure=True)

    # ---- static safety -----------------------------------------------------------
    def test_monitor_source_has_no_listener_or_host_mutation(self) -> None:
        forbidden = (
            "set" + "Webhook",
            "socket." + "listen",
            "HTTPServer",
            "pkill",
            "killall",
            "sudo ",
            "systemctl",
            "systemd-run",
            "qortium-data",
            "qortium-preview",
        )
        for path in sorted((TOOLS / "devmonitor").glob("*.py")):
            text = path.read_text(encoding="utf-8")
            for token in forbidden:
                with self.subTest(path=path.name, token=token):
                    self.assertNotIn(token, text)
        entry = (TOOLS / "dev_monitor.py").read_text(encoding="utf-8")
        for token in forbidden:
            with self.subTest(path="dev_monitor.py", token=token):
                self.assertNotIn(token, entry)


if __name__ == "__main__":
    unittest.main()
