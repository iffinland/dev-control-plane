#!/usr/bin/env python3
"""systemd user unit and single-instance/graceful-stop regression tests.

The unit is parsed as text so duplicate ``Environment=`` keys are allowed. No
service manager is invoked and nothing is installed or started.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

TOOLS = Path(__file__).resolve().parent
ROOT = TOOLS.parent
sys.path.insert(0, str(TOOLS))

from devmonitor.service import AlreadyRunning, MonitorService, monitor_running  # noqa: E402
from devmonitor.state import MonitorState  # noqa: E402
from devmonitor_test_support import FakeApi, make_config  # noqa: E402
from dev_monitor import _build_components  # noqa: E402

UNIT = ROOT / "deploy/systemd/user/qortium-dev-monitor.service"


class FakeRouter:
    def acknowledge_updates(self, _updates) -> None:
        return None


def parse_unit(text: str) -> dict[str, list[tuple[str, str]]]:
    sections: dict[str, list[tuple[str, str]]] = {}
    current: str | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current = line[1:-1]
            sections.setdefault(current, [])
            continue
        if current is None or "=" not in line:
            continue
        key, value = line.split("=", 1)
        sections[current].append((key.strip(), value.strip()))
    return sections


def values(sections, section: str, key: str) -> list[str]:
    return [value for name, value in sections.get(section, []) if name == key]


class SystemdUnitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.assertTrue(UNIT.is_file(), f"missing unit: {UNIT}")
        self.text = UNIT.read_text(encoding="utf-8")
        self.sections = parse_unit(self.text)

    def test_unit_runs_the_existing_monitor_from_the_control_plane(self) -> None:
        self.assertEqual(self.sections["Unit"].count(("Wants", "network-online.target")), 1)
        self.assertEqual(self.sections["Unit"].count(("After", "network-online.target")), 1)
        self.assertEqual(
            values(self.sections, "Service", "WorkingDirectory"),
            [str(ROOT)],
        )
        exec_start = values(self.sections, "Service", "ExecStart")
        self.assertEqual(len(exec_start), 1)
        self.assertIn("/usr/bin/python3", exec_start[0])
        self.assertIn(str(TOOLS / "dev_monitor.py"), exec_start[0])
        self.assertTrue(exec_start[0].endswith(" run"))
        self.assertNotIn("--auto", self.text)

    def test_restart_and_shutdown_contract(self) -> None:
        self.assertEqual(values(self.sections, "Service", "Restart"), ["on-failure"])
        self.assertEqual(values(self.sections, "Service", "RestartSec"), ["5"])
        self.assertEqual(
            values(self.sections, "Service", "RestartPreventExitStatus"), ["2 75 78"]
        )
        self.assertEqual(values(self.sections, "Service", "KillSignal"), ["SIGTERM"])
        self.assertEqual(values(self.sections, "Service", "KillMode"), ["mixed"])
        timeout = int(values(self.sections, "Service", "TimeoutStopSec")[0])
        self.assertGreaterEqual(timeout, 40)
        self.assertEqual(values(self.sections, "Unit", "StartLimitBurst"), ["5"])
        self.assertEqual(values(self.sections, "Install", "WantedBy"), ["default.target"])

    def test_unit_has_no_credentials_or_system_mutation(self) -> None:
        lowered = self.text.lower()
        for token in ("bot_token", "authorized_user_ids", "sudo", "qortium-data"):
            with self.subTest(token=token):
                self.assertNotIn(token, lowered)



class ComponentTimeoutTests(unittest.TestCase):
    def test_long_poll_timeout_is_not_reused_for_ordinary_api_calls(self) -> None:
        with tempfile.TemporaryDirectory(prefix="qdm-timeout-") as temporary:
            root = Path(temporary)
            with mock.patch.dict(
                os.environ,
                {"DEV_CONTROL_PLANE_STATE": str(root / "state")},
                clear=False,
            ):
                config = make_config(
                    root,
                    monitor_extra={
                        "poll_timeout_seconds": 25,
                        "request_timeout_seconds": 9,
                        "document_timeout_seconds": 44,
                    },
                )
                state, api, _registry, _documents, _jobs, _router, _timings = (
                    _build_components(config)
                )
                try:
                    self.assertEqual(api.timeout_seconds, 9)
                    self.assertEqual(api.document_timeout_seconds, 44)
                    # The long-poll grace period is still applied per call.
                    self.assertGreater(api.timeout_seconds, 0)
                    self.assertLess(api.timeout_seconds, config.poll_timeout_seconds + 10)
                finally:
                    state.close()


class SingleInstanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="qdm-unit-")
        self.root = Path(self.temporary.name)
        self.config = make_config(self.root)
        self.first_state = MonitorState(self.root / "monitor" / "monitor.db")
        self.second_state = MonitorState(self.root / "monitor" / "monitor.db")
        self.first = MonitorService(
            self.config, FakeApi(), self.first_state, FakeRouter(), log=lambda _line: None
        )
        self.second = MonitorService(
            self.config, FakeApi(), self.second_state, FakeRouter(), log=lambda _line: None
        )

    def tearDown(self) -> None:
        self.first._release_lock()
        self.first_state.close()
        self.second_state.close()
        self.temporary.cleanup()

    def test_second_instance_is_refused_and_status_detects_the_first(self) -> None:
        self.first._acquire_lock()
        self.assertTrue(monitor_running(self.config.state_dir))
        with self.assertRaises(AlreadyRunning):
            self.second.run(max_iterations=0)
        self.first._release_lock()
        self.assertFalse(monitor_running(self.config.state_dir))

    def test_mark_shutdown_is_idempotent_and_does_not_write_a_stop_file(self) -> None:
        self.first.mark_shutdown(15)
        self.assertTrue(self.first.stop_requested())
        self.assertFalse((self.config.state_dir / "monitor.stop").exists())


if __name__ == "__main__":
    unittest.main()
