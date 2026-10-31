#!/usr/bin/env python3
"""Timing diagnostics tests.

The recorder must stay bounded, must never log payload content or exception text,
and must surface slow operations through the monitor logger.
"""

from __future__ import annotations

import signal
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

from devmonitor.service import (  # noqa: E402
    MonitorService,
    MonitorShutdown,
    install_shutdown_handlers,
    restore_signal_handlers,
)
from devmonitor.state import MonitorState  # noqa: E402
from devmonitor.timings import TimingRecorder, sanitize_label  # noqa: E402
from devmonitor_test_support import FakeApi, make_config  # noqa: E402

SECRET = "timing-" + "secret-" + "778899"


class Clock:
    def __init__(self, now: float = 0.0) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class FakeRouter:
    def acknowledge_updates(self, _updates) -> None:
        return None

    def acknowledge_update(self, _update) -> None:
        return None


class TimingRecorderTests(unittest.TestCase):
    def test_aggregates_and_emits_slow_events_without_payloads(self) -> None:
        clock = Clock()
        recorder = TimingRecorder(
            clock=clock,
            wall_clock=lambda: 1000.0,
            slow_seconds=0.5,
            summary_interval_samples=100,
        )
        with recorder.measure("telegram:sendMessage"):
            clock.advance(1.25)
        with recorder.measure("sqlite:set_offset"):
            clock.advance(0.01)

        lines = recorder.drain_log_lines()
        self.assertEqual(len(lines), 1)
        self.assertIn("label=telegram:sendMessage", lines[0])
        self.assertIn("duration_ms=1250.0", lines[0])
        self.assertEqual(recorder.drain_log_lines(), [])

        snapshot = recorder.snapshot()
        labels = {item["label"]: item for item in snapshot["labels"]}
        self.assertEqual(labels["telegram:sendMessage"]["count"], 1)
        self.assertEqual(labels["telegram:sendMessage"]["slow"], 1)
        self.assertEqual(snapshot["recent_slow"][0]["label"], "telegram:sendMessage")

    def test_exception_text_and_secrets_are_never_recorded(self) -> None:
        recorder = TimingRecorder(clock=Clock(), wall_clock=lambda: 1000.0, slow_seconds=0.0)
        with self.assertRaises(RuntimeError):
            with recorder.measure("telegram:editMessageText"):
                raise RuntimeError("token=" + SECRET)

        lines = recorder.drain_log_lines()
        self.assertEqual(len(lines), 1)
        self.assertNotIn(SECRET, lines[0])
        self.assertIn("outcome=error:RuntimeError", lines[0])
        snapshot = recorder.snapshot()
        self.assertNotIn(SECRET, repr(snapshot))

    def test_labels_are_bounded_and_identifier_safe(self) -> None:
        label = sanitize_label("action/../callback\n" + "x" * 200)
        self.assertLessEqual(len(label), 80)
        self.assertNotIn("/", label)
        self.assertNotIn("\n", label)

    def test_periodic_summary_is_bounded_and_secret_free(self) -> None:
        clock = Clock()
        recorder = TimingRecorder(
            clock=clock,
            wall_clock=lambda: 1000.0,
            slow_seconds=10.0,
            summary_interval_samples=2,
        )
        with recorder.measure("cli:dev_status"):
            clock.advance(0.1)
        with recorder.measure("docs:list"):
            clock.advance(0.2)

        lines = recorder.drain_log_lines()
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith("timing summary samples=2 slow=0 top="))
        self.assertNotIn(SECRET, lines[0])

    def test_service_drains_pending_lines_and_stops_on_signal(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="qdm-timing-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        config = make_config(root)
        clock = Clock()
        recorder = TimingRecorder(
            clock=clock, wall_clock=lambda: 1000.0, slow_seconds=0.5
        )
        state = MonitorState(root / "monitor" / "monitor.db", timings=recorder)
        self.addCleanup(state.close)
        logs: list[str] = []
        service = MonitorService(
            config,
            FakeApi(),
            state,
            FakeRouter(),
            sleep=lambda _value: None,
            log=logs.append,
            timings=recorder,
        )
        with recorder.measure("poll:getUpdates"):
            clock.advance(2.0)
        service.run(max_iterations=0)
        self.assertTrue(any("timing slow label=poll:getUpdates" in line for line in logs))
        self.assertNotIn(SECRET, "\n".join(logs))

        previous = install_shutdown_handlers(service)
        try:
            handler = signal.getsignal(signal.SIGTERM)
            self.assertTrue(callable(handler))
            with self.assertRaises(MonitorShutdown) as caught:
                handler(signal.SIGTERM, None)
            self.assertEqual(caught.exception.signum, signal.SIGTERM)
            self.assertTrue(service.stop_requested())
        finally:
            restore_signal_handlers(previous)


if __name__ == "__main__":
    unittest.main()
