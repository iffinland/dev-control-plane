#!/usr/bin/env python3
"""Read-only Workflow v3 job facade tests using a fake dev CLI."""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

from devmonitor.jobs import JobError, JobFacade, validate_job_id  # noqa: E402
from devmonitor.timings import TimingRecorder  # noqa: E402
from devmonitor_test_support import (  # noqa: E402
    install_fake_dev,
    make_job,
    write_fake_jobs,
)

SECRET = "log-" + "secret-" + "998877"


class JobFacadeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="qdm-jobs-")
        self.root = Path(self.temporary.name)
        self.state_root = self.root / "state"
        self.dev = install_fake_dev(self.root)
        self.running = make_job("20261031T120000Z-demo-job-abcd1234")
        self.done = make_job(
            "20261031T110000Z-done-job-efgh5678", state="SUCCESS", title="Done job"
        )
        write_fake_jobs(self.state_root, [self.running, self.done])
        self.facade = JobFacade(self.state_root, dev_script=self.dev)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _write_log(self, job_id: str, name: str, text: str) -> Path:
        path = self.state_root / "jobs" / job_id / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_list_jobs_active_first(self) -> None:
        jobs = self.facade.list_jobs()
        self.assertEqual(jobs[0]["state"], "RUNNING")
        self.assertEqual(jobs[1]["state"], "SUCCESS")


    def test_cli_calls_are_timed_by_operation_name(self) -> None:
        recorder = TimingRecorder(slow_seconds=10.0)
        facade = JobFacade(self.state_root, dev_script=self.dev, timings=recorder)
        facade.list_jobs()
        labels = {item["label"] for item in recorder.snapshot()["labels"]}
        self.assertEqual(labels, {"cli:dev_status"})

    def test_job_status(self) -> None:
        payload = self.facade.job_status(self.running["id"])
        self.assertEqual(payload["attempt_number"], 1)
        self.assertEqual(payload["pending_criteria"], ["AC1"])

    def test_invalid_job_ids_are_refused(self) -> None:
        for value in ("", "../x", "a/b", ".", "..", "id with space"):
            with self.subTest(value=value):
                with self.assertRaises(JobError):
                    validate_job_id(value)

    def test_missing_job_is_an_error(self) -> None:
        with self.assertRaises(JobError):
            self.facade.job_status("20261031T000000Z-missing-00000000")

    def test_log_is_bounded_redacted_and_newest_last(self) -> None:
        lines = [f"line {index:03d}" for index in range(200)]
        lines.append("pass" + "word=" + SECRET)
        self._write_log(self.running["id"], "run.log", "\n".join(lines) + "\n")
        log = self.facade.job_log(self.running["id"], "run", max_lines=10)
        self.assertTrue(log.truncated)
        self.assertIn("line 199", log.text)
        self.assertNotIn("line 000", log.text)
        self.assertNotIn(SECRET, log.text)
        self.assertLessEqual(len(log.text.splitlines()), 10)

    def test_log_symlink_is_refused(self) -> None:
        outside = self.root / "outside.log"
        outside.write_text("outside\n", encoding="utf-8")
        os.symlink(outside, self.state_root / "jobs" / self.running["id"] / "worker.log")
        with self.assertRaises(JobError):
            self.facade.job_log(self.running["id"], "worker")

    def test_missing_log_is_an_error(self) -> None:
        with self.assertRaises(JobError):
            self.facade.job_log(self.running["id"], "run")

    def test_existing_report_is_redacted(self) -> None:
        (self.state_root / "jobs" / self.running["id"] / "report.md").write_text(
            "# Report\n\n" + "pass" + "word=" + SECRET + "\n", encoding="utf-8"
        )
        report = self.facade.job_report(self.running["id"], secrets=(SECRET,))
        self.assertIn("# Report", report.text)
        self.assertNotIn(SECRET, report.text)

    def test_missing_report_is_generated_through_dev_report(self) -> None:
        report = self.facade.job_report(self.running["id"])
        self.assertIn("# Report", report.text)
        self.assertTrue(
            (self.state_root / "jobs" / self.running["id"] / "report.md").is_file()
        )

    def test_job_record_is_bounded_and_validated(self) -> None:
        record = self.facade.job_record(self.running["id"])
        self.assertEqual(record["id"], self.running["id"])
        self.assertTrue(record.get("notifications_enabled"))

    def test_job_events_advance_and_reset_cursors(self) -> None:
        events = self.state_root / "jobs" / self.running["id"] / "events.jsonl"
        events.write_text(
            '{"ts":"2026-10-31T12:00:00Z","event":"worker_started","detail":"pid=1"}\n'
            '{"ts":"2026-10-31T12:00:01Z","event":"attempt_started","detail":"attempt=1 resume=False"}\n',
            encoding="utf-8",
        )
        first = self.facade.job_events(self.running["id"])
        self.assertEqual([item["event"] for item in first.events], ["worker_started", "attempt_started"])
        self.assertGreater(first.offset, 0)
        self.assertEqual(self.facade.job_events(self.running["id"], inode=first.inode, offset=first.offset).events, ())
        # Replacing the file changes the inode; the caller resets from zero.
        events.write_text('{"ts":"x","event":"finished","detail":""}\n', encoding="utf-8")
        reset = self.facade.job_events(self.running["id"], inode=first.inode, offset=first.offset)
        self.assertTrue(reset.reset)
        self.assertEqual([item["event"] for item in reset.events], ["finished"])

    def test_job_events_can_start_at_end_for_terminal_history(self) -> None:
        events = self.state_root / "jobs" / self.running["id"] / "events.jsonl"
        events.write_text('{"ts":"x","event":"finished","detail":""}\n', encoding="utf-8")
        batch = self.facade.job_events(self.running["id"], start_at_end=True)
        self.assertTrue(batch.skipped_existing)
        self.assertEqual(batch.events, ())
        self.assertEqual(batch.offset, events.stat().st_size)

    def test_report_is_bounded(self) -> None:
        (self.state_root / "jobs" / self.running["id"] / "report.md").write_text(
            "y" * 1000, encoding="utf-8"
        )
        report = self.facade.job_report(self.running["id"], max_bytes=100)
        self.assertTrue(report.truncated)
        self.assertLessEqual(len(report.text), 100)


if __name__ == "__main__":
    unittest.main()
