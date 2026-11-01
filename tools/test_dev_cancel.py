#!/usr/bin/env python3
"""Safety and lifecycle tests for additive Workflow v3 cancellation.

Every test uses real child processes that are owned by the test, a disposable
state directory and a synthetic job record. No OpenCode model session, Qortium
process or live VPS service is involved.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

from devjob import runner  # noqa: E402
from devjob.store import append_event, job_dir, load_job, save_job  # noqa: E402

FAKE_GUARD = r'''#!/usr/bin/env python3
import signal
import sys
import time

stopped = {"value": False}


def handle(signum, frame):
    stopped["value"] = True


signal.signal(signal.SIGTERM, handle)
signal.signal(signal.SIGINT, handle)
while not stopped["value"]:
    time.sleep(0.05)
sys.exit(143)
'''

FAKE_WORKER = r'''#!/usr/bin/env python3
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

job_id = sys.argv[2]
directory = Path(sys.argv[3])
marker = directory / "cancel.requested.json"
path = directory / "job.json"
deadline = time.time() + 15
while time.time() < deadline and not marker.exists():
    time.sleep(0.05)
if marker.exists():
    job = json.loads(path.read_text(encoding="utf-8"))
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    job["state"] = "CANCELLED"
    job["blocker"] = "cancelled by owner request"
    job["cancelled_at"] = now
    job["ended_at"] = now
    attempts = job.get("attempts") or []
    if attempts:
        attempts[-1]["cancelled"] = True
        attempts[-1]["ended_at"] = now
    path.write_text(json.dumps(job, indent=2, sort_keys=True), encoding="utf-8")
    with (directory / "events.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {"ts": now, "event": "cancel_observed", "detail": "worker finalization"},
                sort_keys=True,
            )
            + "\n"
        )
    time.sleep(0.2)
sys.exit(0)
'''


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class CancelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="dev-cancel-")
        self.root = Path(self.temporary.name)
        self.state = self.root / "state"
        self.repo = self.root / "repo"
        self.repo.mkdir()
        (self.repo / "untouched.txt").write_text("preserved\n", encoding="utf-8")
        self.guard_script = self.root / "opencode_guard.py"
        self.guard_script.write_text(FAKE_GUARD, encoding="utf-8")
        self.worker_script = self.root / "fake_dev.py"
        self.worker_script.write_text(FAKE_WORKER, encoding="utf-8")
        self.children: list[subprocess.Popen] = []
        self.previous_state = os.environ.get("DEV_CONTROL_PLANE_STATE")
        os.environ["DEV_CONTROL_PLANE_STATE"] = str(self.state)

    def tearDown(self) -> None:
        if self.previous_state is None:
            os.environ.pop("DEV_CONTROL_PLANE_STATE", None)
        else:
            os.environ["DEV_CONTROL_PLANE_STATE"] = self.previous_state
        for child in self.children:
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=5)
        self.temporary.cleanup()

    def spawn(self, argv: list[str]) -> subprocess.Popen:
        child = subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.children.append(child)
        return child

    def spawn_worker(self, job_id: str) -> subprocess.Popen:
        return self.spawn(
            [
                sys.executable,
                str(self.worker_script),
                "_worker",
                job_id,
                str(job_dir(job_id, self.state)),
            ]
        )

    def spawn_guard(self, job_id: str) -> subprocess.Popen:
        directory = job_dir(job_id, self.state)
        return self.spawn(
            [
                sys.executable,
                str(self.guard_script),
                "run",
                "--log",
                str(directory / "run.log"),
                "--session-title",
                f"Cancel test [job {job_id}]",
                job_id,
            ]
        )

    def make_job(self, *, state: str = "RUNNING") -> dict:
        job_id = "20261101T120000Z-cancel-test-12345678"
        directory = job_dir(job_id, self.state)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "run.log").write_text("guard output\n", encoding="utf-8")
        job = {
            "id": job_id,
            "title": "Cancel test",
            "state": state,
            "repo": str(self.repo),
            "branch": "main",
            "started_at": now(),
            "ended_at": None if state == "RUNNING" else now(),
            "timeout_seconds": 3600,
            "worker_pid": None,
            "guard_pid": None,
            "child_pid": None,
            "exit_code": None,
            "session_id": "ses_cancel_test",
            "attempts": [
                {
                    "number": 1,
                    "started_at": now(),
                    "ended_at": None,
                    "duration_seconds": None,
                }
            ],
            "acceptance_criteria": [
                {
                    "id": "AC1",
                    "kind": "command",
                    "label": "Build",
                    "command": "true",
                    "required": True,
                }
            ],
            "verification": {},
            "detected_issues": [],
            "blocker": None,
            "notifications_enabled": False,
            "notifications": [],
            "log_path": str(directory / "run.log"),
            "worker_log_path": str(directory / "worker.log"),
            "report_path": str(directory / "report.md"),
        }
        save_job(job, self.state)
        append_event(job, "attempt_started", "attempt=1 resume=False", root=self.state)
        return load_job(job_id, self.state)

    def test_verified_guard_receives_sigterm_and_job_becomes_cancelled(self) -> None:
        job = self.make_job()
        worker = self.spawn_worker(job["id"])
        guard = self.spawn_guard(job["id"])
        job = load_job(job["id"], self.state)
        job["worker_pid"] = worker.pid
        job["guard_pid"] = guard.pid
        save_job(job, self.state)

        result = runner.cancel_job(job["id"], grace_seconds=10.0)

        self.assertEqual(result["cancel_status"], "cancelled", result)
        final = load_job(job["id"], self.state)
        self.assertEqual(final["state"], "CANCELLED")
        self.assertIn("owner request", final["blocker"])
        self.assertEqual(final["attempts"][-1]["cancelled"], True)
        self.assertTrue(
            (job_dir(job["id"], self.state) / "cancel.requested.json").is_file()
        )
        events = [
            json.loads(line)["event"]
            for line in (job_dir(job["id"], self.state) / "events.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip()
        ]
        self.assertIn("cancel_requested", events)
        self.assertTrue((self.repo / "untouched.txt").is_file())
        self.assertTrue(Path(final["report_path"]).is_file())
        self.assertNotEqual(guard.poll(), None)

    def test_guard_identity_mismatch_is_refused_without_signal_or_marker(self) -> None:
        job = self.make_job()
        worker = self.spawn_worker(job["id"])
        not_guard = self.spawn(
            [sys.executable, "-c", "import time; time.sleep(30)", job["id"]]
        )
        job = load_job(job["id"], self.state)
        job["worker_pid"] = worker.pid
        job["guard_pid"] = not_guard.pid
        save_job(job, self.state)

        with self.assertRaises(runner.JobError):
            runner.cancel_job(job["id"], grace_seconds=2.0)

        self.assertIsNone(not_guard.poll())
        self.assertFalse(
            (job_dir(job["id"], self.state) / "cancel.requested.json").exists()
        )
        self.assertEqual(load_job(job["id"], self.state)["state"], "RUNNING")

    def test_terminal_job_is_refused(self) -> None:
        job = self.make_job(state="SUCCESS")
        with self.assertRaises(runner.JobError):
            runner.cancel_job(job["id"], grace_seconds=1.0)

    def test_missing_worker_is_reconciled_without_a_signal(self) -> None:
        job = self.make_job()
        job["worker_pid"] = 2_147_483_000
        job["guard_pid"] = 2_147_483_001
        save_job(job, self.state)

        result = runner.cancel_job(job["id"], grace_seconds=1.0)

        self.assertEqual(result["cancel_status"], "reconciled")
        self.assertEqual(load_job(job["id"], self.state)["state"], "FAILED")
        self.assertFalse(
            (job_dir(job["id"], self.state) / "cancel.requested.json").exists()
        )

    def test_cancel_marker_is_scoped_to_one_attempt(self) -> None:
        job = self.make_job()
        marker = {"job_id": job["id"], "attempt_number": 1, "guard_pid": 1}
        self.assertTrue(runner.cancel_request_matches(job, marker))
        job["attempts"].append({"number": 2, "started_at": now()})
        self.assertFalse(runner.cancel_request_matches(job, marker))

    def test_cli_cancel_refuses_terminal_job_with_a_sanitized_error(self) -> None:
        job = self.make_job(state="SUCCESS")
        result = subprocess.run(
            [
                sys.executable,
                str(TOOLS / "dev.py"),
                "cancel",
                "--state-dir",
                str(self.state),
                job["id"],
                "--json",
            ],
            text=True,
            capture_output=True,
            timeout=20,
            check=False,
        )
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("only a RUNNING job can be cancelled", result.stderr)


if __name__ == "__main__":
    unittest.main()
