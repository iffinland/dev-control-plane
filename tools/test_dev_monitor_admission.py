#!/usr/bin/env python3
"""Per-project admission and global execution-guard awareness tests."""

from __future__ import annotations

import fcntl
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

from devmonitor.admission import (  # noqa: E402
    AdmissionLockTimeout,
    AdmissionManager,
    GlobalGuardBusy,
    ProjectBusy,
)
from devmonitor.jobs import JobFacade  # noqa: E402
from devmonitor.projects import Registry  # noqa: E402
from devmonitor_test_support import (  # noqa: E402
    install_fake_dev,
    make_config,
    make_job,
    write_fake_jobs,
)


class AdmissionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="qdm-adm-")
        self.root = Path(self.temporary.name)
        self.projects = self.root / "projects"
        self.projects.mkdir()
        self.repo_a = self.projects / "A"
        self.repo_a.mkdir()
        self.repo_b = self.projects / "B"
        self.repo_b.mkdir()
        self.registry_file = self.root / "PROJECT-REGISTRY.md"
        self.registry_file.write_text(
            "# Project registry\n\n## Registered projects\n\n"
            "| ID | Platform | Verified local path | Project-level `AGENTS.md` | Canonical context | Central report root |\n"
            "| --- | --- | --- | --- | --- | --- |\n"
            f"| `demo/a` | Qortal | `{self.repo_a}` | Yes | Pending | `{self.root / 'docs/a'}/` |\n"
            f"| `demo/b` | Qortal | `{self.repo_b}` | Yes | Pending | `{self.root / 'docs/b'}/` |\n",
            encoding="utf-8",
        )
        self.state_root = self.root / "state"
        self.fake_dev = install_fake_dev(self.root)
        self.config = make_config(self.root, repo_roots=[self.projects])
        self.registry = Registry(self.registry_file, (self.projects,))
        self.registry.load(force=True)
        self.jobs = JobFacade(self.state_root, dev_script=self.fake_dev)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _manager(self, *, timeout: float = 2.0) -> AdmissionManager:
        return AdmissionManager(
            self.config.state_dir, self.jobs, self.registry, lock_timeout=timeout
        )

    def test_project_key_matches_registered_repository_realpath(self) -> None:
        manager = self._manager()
        self.assertEqual(manager.project_key_for_repo(self.repo_a), "demo/a")
        self.assertEqual(manager.project_key_for_repo(self.repo_b), "demo/b")
        unknown = manager.project_key_for_repo(self.root / "elsewhere")
        self.assertTrue(unknown.startswith("repo:"))

    def test_same_project_active_job_is_busy(self) -> None:
        write_fake_jobs(
            self.state_root,
            [make_job("20261031T120000Z-adm-a-aaaaaaaa", repo=str(self.repo_a))],
        )
        manager = self._manager()
        with self.assertRaises(ProjectBusy):
            manager.check_project("demo/a")

    def test_different_project_active_job_is_global_guard_busy(self) -> None:
        write_fake_jobs(
            self.state_root,
            [make_job("20261031T120000Z-adm-b-bbbbbbbb", repo=str(self.repo_b))],
        )
        manager = self._manager()
        with self.assertRaises(GlobalGuardBusy):
            manager.check_project("demo/a")

    def test_stale_running_job_without_live_worker_is_not_active(self) -> None:
        job = make_job("20261031T120000Z-adm-stale-cccccccc", repo=str(self.repo_a))
        job["worker_alive"] = False
        write_fake_jobs(self.state_root, [job])
        manager = self._manager()
        manager.check_project("demo/a")

    def test_guard_lock_is_detected_read_only(self) -> None:
        self.state_root.mkdir(parents=True, exist_ok=True)
        guard = self.state_root / "guard.lock"
        handle = guard.open("a+", encoding="utf-8")
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            manager = self._manager()
            self.assertTrue(manager.guard_lock_held())
            with self.assertRaises(GlobalGuardBusy):
                manager.check_project("demo/a")
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()

    def test_project_lock_serializes_concurrent_sections(self) -> None:
        manager = self._manager(timeout=3.0)
        order: list[str] = []
        entered = threading.Event()

        def first() -> None:
            with manager.reserve("demo/a"):
                order.append("first-in")
                entered.set()
                time.sleep(0.25)
                order.append("first-out")

        def second() -> None:
            entered.wait(1.0)
            with manager.reserve("demo/a"):
                order.append("second-in")
                order.append("second-out")

        threads = [threading.Thread(target=first), threading.Thread(target=second)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(5)

        self.assertEqual(order, ["first-in", "first-out", "second-in", "second-out"])

    def test_lock_timeout_is_reported(self) -> None:
        manager = self._manager(timeout=0.2)
        entered = threading.Event()
        release = threading.Event()

        def holder() -> None:
            with manager.reserve("demo/a"):
                entered.set()
                release.wait(2.0)

        thread = threading.Thread(target=holder)
        thread.start()
        entered.wait(1.0)
        try:
            with self.assertRaises(AdmissionLockTimeout):
                with manager.reserve("demo/a"):
                    pass
        finally:
            release.set()
            thread.join(5)


if __name__ == "__main__":
    unittest.main()
