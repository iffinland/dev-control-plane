#!/usr/bin/env python3
"""STARTED/RESUMED and terminal notification dedupe tests with fake Telegram."""

from __future__ import annotations

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

from devmonitor.config import with_overrides  # noqa: E402
from devmonitor.jobs import JobFacade  # noqa: E402
from devmonitor.lifecycle import LifecycleNotifier  # noqa: E402
from devmonitor.projects import Registry  # noqa: E402
from devmonitor.state import MonitorState  # noqa: E402
from devmonitor_test_support import (  # noqa: E402
    FakeApi,
    install_fake_dev,
    make_config,
    make_job,
    write_fake_jobs,
)


def iso_now(offset: int = 0) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + offset))


class LifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="qdm-life-")
        self.root = Path(self.temporary.name)
        self.projects = self.root / "projects"
        self.projects.mkdir()
        self.repo = self.projects / "Demo"
        self.repo.mkdir()
        self.docs = self.root / "docs"
        self.docs.mkdir()
        self.registry_file = self.root / "PROJECT-REGISTRY.md"
        self.registry_file.write_text(
            "# Project registry\n\n## Registered projects\n\n"
            "| ID | Platform | Verified local path | Project-level `AGENTS.md` | Canonical context | Central report root |\n"
            "| --- | --- | --- | --- | --- | --- |\n"
            f"| `demo/project` | Qortal | `{self.repo}` | Yes | Pending | `{self.docs}/` |\n",
            encoding="utf-8",
        )
        self.state_root = self.root / "state"
        self.fake_dev = install_fake_dev(self.root)
        self.config = with_overrides(
            make_config(
                self.root,
                docs_roots=[self.docs],
                repo_roots=[self.projects],
                monitor_extra={"terminal_grace_seconds": 0},
            ),
            registry_path=self.registry_file,
        )
        self.state = MonitorState(self.root / "monitor" / "monitor.db")
        self.api = FakeApi()
        self.registry = Registry(self.registry_file, (self.projects,))
        self.jobs = JobFacade(self.state_root, dev_script=self.fake_dev)
        self.notifier = LifecycleNotifier(
            self.config, self.state, self.jobs, self.api, self.registry
        )

    def tearDown(self) -> None:
        self.state.close()
        self.temporary.cleanup()

    def _job(self, job_id: str, *, state: str = "RUNNING", **kwargs) -> dict:
        kwargs.setdefault("repo", str(self.repo))
        job = make_job(job_id, state=state, **kwargs)
        write_fake_jobs(self.state_root, [job])
        return job

    def _events(self, job_id: str, events: list[tuple[str, str]]) -> None:
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

    def _texts(self) -> list[str]:
        return [item["text"] for item in self.api.sent]

    def test_started_is_sent_once_across_polls_and_restart(self) -> None:
        job = self._job("20261031T120000Z-life-start-aaaaaaaa")
        self._events(job["id"], [("worker_started", "pid=1"), ("attempt_started", "attempt=1 resume=False")])
        self.assertEqual(self.notifier.poll(), ["STARTED"])
        self.assertTrue(any("STARTED" in text for text in self._texts()))
        before = len(self.api.sent)
        self.assertEqual(self.notifier.poll(), [])
        restarted = LifecycleNotifier(
            self.config, self.state, self.jobs, self.api, self.registry
        )
        self.assertEqual(restarted.poll(), [])
        self.assertEqual(len(self.api.sent), before)

    def test_resumed_is_sent_once_per_resume_count(self) -> None:
        job = self._job("20261031T120000Z-life-resume-bbbbbbbb")
        job["resume_count"] = 1
        write_fake_jobs(self.state_root, [job])
        self._events(
            job["id"],
            [
                ("resume_requested", "resume_count=1"),
                ("attempt_started", "attempt=2 resume=True"),
            ],
        )
        self.assertEqual(self.notifier.poll(), ["RESUMED"])
        self.assertTrue(any("RESUMED" in text for text in self._texts()))
        self.assertEqual(self.notifier.poll(), [])

    def test_cli_started_terminal_with_sent_notification_is_not_duplicated(self) -> None:
        job = self._job(
            "20261031T120000Z-life-cli-dedupe-cccccccc",
            state="FAILED",
            ended_at=iso_now(),
            notifications_enabled=True,
            notifications=[{"state": "FAILED", "sent": True, "reason": "sent"}],
        )
        self._events(job["id"], [("finished", "state=FAILED exit=1")])
        self.assertEqual(self.notifier.poll(), [])
        self.assertFalse(any("Job FAILED" in text for text in self._texts()))

    def test_monitor_started_terminal_sends_one_final_message(self) -> None:
        job = self._job(
            "20261031T120000Z-life-monitor-final-dddddddd",
            state="FAILED",
            ended_at=iso_now(),
            notifications_enabled=False,
            notifications=[{"state": "FAILED", "sent": False, "reason": "disabled for job"}],
        )
        self._events(job["id"], [("finished", "state=FAILED exit=1")])
        self.assertEqual(self.notifier.poll(), ["TERMINAL:FAILED"])
        self.assertEqual(sum("Job FAILED" in text for text in self._texts()), 1)
        self.assertEqual(self.notifier.poll(), [])

    def test_external_terminal_without_notification_is_relayed_after_grace(self) -> None:
        job = self._job(
            "20261031T120000Z-life-external-final-eeeeeeee",
            state="TIMEOUT",
            ended_at=iso_now(-60),
            notifications_enabled=True,
            notifications=[],
        )
        self._events(job["id"], [("finished", "state=TIMEOUT exit=124")])
        self.assertEqual(self.notifier.poll(), ["TERMINAL:TIMEOUT"])
        self.assertEqual(self.notifier.poll(), [])

    def test_historical_terminal_is_not_replayed_on_first_run(self) -> None:
        job = self._job(
            "20261031T120000Z-life-old-final-ffffffff",
            state="FAILED",
            ended_at=iso_now(-3 * 86400),
            notifications_enabled=False,
            notifications=[],
        )
        self._events(job["id"], [("finished", "state=FAILED exit=1")])
        self.assertEqual(self.notifier.poll(), [])
        self.assertFalse(any("Job FAILED" in text for text in self._texts()))

    def test_worker_lost_alert_is_sent_once(self) -> None:
        job = self._job(
            "20261031T120000Z-life-worker-lost-99999999",
            state="FAILED",
            ended_at=iso_now(),
            notifications_enabled=True,
            notifications=[{"state": "FAILED", "sent": True, "reason": "sent"}],
        )
        self.state.set_meta("lifecycle_initialized", "1")
        self.assertEqual(self.notifier.poll(), [])
        self._events(job["id"], [("reconciled_stale", "background worker is gone")])
        self.assertIn("reconciled_stale".upper(), self.notifier.poll())
        self.assertEqual(self.notifier.poll(), [])


class _FakeRouter:
    def acknowledge_updates(self, _updates) -> None:
        return None

    def acknowledge_update(self, _update) -> None:
        return None

    def handle(self, _update) -> None:
        return None


class ServiceLifecycleTests(LifecycleTests):
    def test_service_polls_lifecycle_after_the_poll_batch(self) -> None:
        from devmonitor.service import MonitorService

        job = self._job(
            "20261031T120000Z-life-service-77777777",
            notifications_enabled=False,
            ended_at=iso_now(),
            notifications=[{"state": "FAILED", "sent": False, "reason": "disabled for job"}],
            state="FAILED",
        )
        self._events(job["id"], [("finished", "state=FAILED exit=1")])
        self.api.updates = [[]]
        service = MonitorService(
            self.config,
            self.api,
            self.state,
            _FakeRouter(),
            lifecycle=self.notifier,
            sleep=lambda _value: None,
        )
        service.run(max_iterations=1)
        self.assertTrue(any("Job FAILED" in text for text in self._texts()))


if __name__ == "__main__":
    unittest.main()
