#!/usr/bin/env python3
"""Monitor single-instance lock and health-check semantics.

These tests use only temporary state directories and short-lived helper
processes created by the test. They never contact Telegram, start the real
monitor, inspect production monitor state, or signal a service. The helpers hold
an isolated ``monitor.lock`` so the read-only inspection logic can be exercised
against stopped, healthy-running, stale/unknown and competing instances.
"""

from __future__ import annotations

import fcntl
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

from devmonitor.config import with_overrides  # noqa: E402
from devmonitor.documents import DocumentLibrary  # noqa: E402
from devmonitor.projects import Registry  # noqa: E402
from devmonitor.service import (  # noqa: E402
    check_monitor,
    inspect_monitor_instance,
    monitor_running,
)
from devmonitor_test_support import FakeApi, make_config  # noqa: E402

HELPER = """\
import fcntl
import os
import time

lock_path = os.environ["TEST_MONITOR_LOCK"]
hold = os.environ.get("TEST_MONITOR_HOLD", "1") == "1"
handle = None
if hold:
    handle = open(lock_path, "a+", encoding="utf-8")
    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    handle.seek(0)
    handle.truncate()
    handle.write(f"pid={os.getpid()} started={int(time.time())}\\n")
    handle.flush()
print("ready", flush=True)
time.sleep(60)
"""


class FailingApi(FakeApi):
    def get_me(self) -> dict:
        raise RuntimeError("telegram unavailable in isolated test")


class MonitorHealthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="qdm-health-")
        self.root = Path(self.temporary.name)
        self.projects = self.root / "projects"
        self.projects.mkdir()
        self.state_dir = self.root / "monitor"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.lock_path = self.state_dir / "monitor.lock"
        self.registry_path = self.root / "PROJECT-REGISTRY.md"
        self.registry_path.write_text(
            "# Project registry\n\n## Registered projects\n\n"
            "| ID | Platform | Verified local path | Project-level `AGENTS.md` | Canonical context | Central report root | Git remote | GitHub repository | Development branch pattern | Automatic push |\n"
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
            f"| `demo/project` | Control plane | `{self.projects}` | Yes | Pending | `{self.root}/docs/` | "
            "`origin` | `demo/project` | `agent/*` | `yes` |\n",
            encoding="utf-8",
        )
        self.config = with_overrides(
            make_config(self.root), registry_path=self.registry_path
        )
        self.registry = Registry(self.registry_path, (self.projects,))
        self.documents = DocumentLibrary.from_sources(
            self.config.docs_roots, self.registry.load(force=True)
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    # ---- helpers -------------------------------------------------------------
    def start_helper(
        self, *, name: str = "dev_monitor.py", hold: bool = True
    ) -> subprocess.Popen:
        script = self.root / name
        script.write_text(HELPER, encoding="utf-8")
        environment = os.environ.copy()
        environment["TEST_MONITOR_LOCK"] = str(self.lock_path)
        environment["TEST_MONITOR_HOLD"] = "1" if hold else "0"
        process = subprocess.Popen(
            [
                sys.executable,
                str(script),
                "run",
                "--state-dir",
                str(self.state_dir),
            ],
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.addCleanup(self.stop_helper, process)
        assert process.stdout is not None
        line = process.stdout.readline().strip()
        if line != "ready":
            error = process.stderr.read() if process.stderr else ""
            raise AssertionError(f"helper did not become ready: {line!r} {error!r}")
        return process

    @staticmethod
    def stop_helper(process: subprocess.Popen) -> None:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        for stream in (process.stdout, process.stderr):
            if stream is not None:
                stream.close()

    def check(self, expect: str = "auto", api=None):
        return check_monitor(
            self.config,
            api or FakeApi(),
            self.registry,
            self.documents,
            expect=expect,
        )

    # ---- cases ---------------------------------------------------------------
    def test_stopped_monitor_is_preflight_ready_and_not_running(self) -> None:
        instance = inspect_monitor_instance(self.state_dir)
        self.assertEqual(instance.state, "stopped")
        self.assertTrue(instance.start_ready)
        self.assertFalse(instance.healthy)
        self.assertFalse(monitor_running(self.state_dir))

        ok, lines = self.check("start")
        self.assertTrue(ok, "\n".join(lines))
        self.assertTrue(any("lock: free" in line for line in lines))
        self.assertTrue(any("preflight: ready" in line for line in lines))

        ok, lines = self.check("running")
        self.assertFalse(ok)
        self.assertTrue(any("expectation: FAILED" in line for line in lines))

    def test_healthy_running_instance_passes_health_but_not_start_preflight(self) -> None:
        process = self.start_helper()
        instance = inspect_monitor_instance(self.state_dir)
        self.assertEqual(instance.state, "running")
        self.assertEqual(instance.holder_pid, process.pid)
        self.assertEqual(instance.pid, process.pid)
        self.assertTrue(instance.healthy)
        self.assertFalse(instance.start_ready)
        self.assertTrue(monitor_running(self.state_dir))

        ok, lines = self.check("auto")
        self.assertTrue(ok, "\n".join(lines))
        self.assertTrue(any(f"held by live monitor pid={process.pid}" in line for line in lines))
        self.assertTrue(any("preflight: NOT ready" in line for line in lines))

        ok, lines = self.check("running")
        self.assertTrue(ok, "\n".join(lines))
        self.assertTrue(any("healthy running monitor verified" in line for line in lines))

        ok, lines = self.check("start")
        self.assertFalse(ok)
        self.assertTrue(any("preflight for starting a new monitor is not ready" in line for line in lines))

    def test_stale_unheld_lock_is_detected_but_does_not_block_start(self) -> None:
        self.lock_path.write_text("pid=999999 started=123\n", encoding="utf-8")
        instance = inspect_monitor_instance(self.state_dir)
        self.assertEqual(instance.state, "stale")
        self.assertEqual(instance.pid, 999999)
        self.assertTrue(instance.start_ready)
        self.assertFalse(instance.healthy)
        self.assertFalse(monitor_running(self.state_dir))

        ok, lines = self.check("start")
        self.assertTrue(ok, "\n".join(lines))
        self.assertTrue(any("lock: stale" in line for line in lines))
        self.assertTrue(any("replaces the stale lock file" in line for line in lines))

        ok, _lines = self.check("running")
        self.assertFalse(ok)

    def test_unknown_lock_owner_fails_closed(self) -> None:
        process = self.start_helper(name="other_process.py")
        instance = inspect_monitor_instance(self.state_dir)
        self.assertEqual(instance.state, "unknown")
        self.assertEqual(instance.holder_pid, process.pid)
        self.assertFalse(instance.start_ready)
        self.assertFalse(instance.healthy)

        for expect in ("auto", "start", "running"):
            with self.subTest(expect=expect):
                ok, lines = self.check(expect)
                self.assertFalse(ok, "\n".join(lines))
                self.assertTrue(any("lock: FAILED" in line for line in lines))
                self.assertTrue(any("cannot be verified" in line for line in lines))

    def test_competing_monitor_processes_fail_closed(self) -> None:
        owner = self.start_helper()
        competitor = self.start_helper(hold=False)
        instance = inspect_monitor_instance(self.state_dir)
        self.assertEqual(instance.state, "competing")
        self.assertEqual(instance.holder_pid, owner.pid)
        self.assertIn(competitor.pid, instance.competing_pids)
        self.assertFalse(instance.healthy)

        for expect in ("auto", "start", "running"):
            with self.subTest(expect=expect):
                ok, lines = self.check(expect)
                self.assertFalse(ok, "\n".join(lines))
                self.assertTrue(any("competing monitor processes" in line for line in lines))

    def test_real_telegram_failure_still_fails_health_check(self) -> None:
        process = self.start_helper()
        ok, lines = self.check("auto", api=FailingApi())
        self.assertFalse(ok)
        self.assertIn(process.pid, [inspect_monitor_instance(self.state_dir).holder_pid])
        self.assertTrue(any("telegram getMe: FAILED" in line for line in lines))

    def test_lock_metadata_is_not_used_as_proof(self) -> None:
        self.lock_path.write_text(
            json.dumps({"pid": 1, "started": 2}) + "\n", encoding="utf-8"
        )
        handle = self.lock_path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            instance = inspect_monitor_instance(self.state_dir)
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()
        # The test process itself is the real lock holder, but it is not a
        # monitor run command, so the check fails closed instead of trusting the
        # unparsable/non-matching metadata.
        self.assertEqual(instance.state, "unknown")
        self.assertFalse(instance.healthy)


if __name__ == "__main__":
    unittest.main()
