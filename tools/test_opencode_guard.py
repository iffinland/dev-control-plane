#!/usr/bin/env python3
"""Tests for the unattended OpenCode execution guard.

The tests use temporary procfs fixtures and disposable subprocesses. They never
signal the real Qortium process and never start a real OpenCode model session.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


TOOLS = Path(__file__).resolve().parent
CONTROL_PLANE = TOOLS.parent
GUARD = TOOLS / "opencode_guard.py"
AGENT = CONTROL_PLANE / "adapters/opencode/agents/opencode-unattended.md"
DEV_AGENT = CONTROL_PLANE / "adapters/opencode/agents/opencode-development.md"
sys.path.insert(0, str(TOOLS))

import opencode_guard as guard  # noqa: E402


def write_process(proc_root: Path, pid: int, argv: list[str], rss_kib: int) -> None:
    directory = proc_root / str(pid)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "cmdline").write_bytes(b"\0".join(item.encode() for item in argv) + b"\0")
    (directory / "comm").write_text(f"{Path(argv[0]).name}\n", encoding="utf-8")
    (directory / "status").write_text(
        f"Name:\t{Path(argv[0]).name}\nVmRSS:\t{rss_kib} kB\n",
        encoding="utf-8",
    )


def make_proc(
    root: Path,
    available_kib: int = 8 * 1024 * 1024,
    load5: float = 1.0,
    processes: list[tuple[int, list[str], int]] | None = None,
) -> Path:
    proc = root / "proc"
    proc.mkdir(parents=True, exist_ok=True)
    (proc / "meminfo").write_text(
        "MemTotal:       12548681 kB\n"
        f"MemAvailable:   {available_kib} kB\n"
        "SwapTotal:             0 kB\n"
        "SwapFree:              0 kB\n",
        encoding="utf-8",
    )
    (proc / "loadavg").write_text(f"1.00 {load5:.2f} 1.00 1/100 1\n", encoding="utf-8")
    (proc / "swaps").write_text("Filename\tType\tSize\tUsed\tPriority\n", encoding="utf-8")
    if processes is None:
        processes = [
            (100, ["opencode"], 800000),
            (102, ["opencode", "stats"], 500000),
            (13615, ["java", "-jar", "/home/iffi/qortium-preview/qortium.jar"], 3500000),
        ]
    for pid, argv, rss in processes:
        write_process(proc, pid, argv, rss)
    return proc


def run_guard(args: list[str], timeout: float = 30.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(GUARD), *args],
        cwd=CONTROL_PLANE,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


def wait_for_file(path: Path, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.exists() and path.stat().st_size > 0:
            return True
        time.sleep(0.05)
    return False


def wait_until_gone(pid: int, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        time.sleep(0.05)
    return False


class DurationTests(unittest.TestCase):
    def test_duration_units(self) -> None:
        self.assertEqual(guard.parse_duration("8h"), 28800)
        self.assertEqual(guard.parse_duration("480m"), 28800)
        self.assertEqual(guard.parse_duration("28800s"), 28800)
        self.assertEqual(guard.parse_duration("1s"), 1)

    def test_default_maximum_is_eight_hours(self) -> None:
        self.assertEqual(guard.MAX_TIMEOUT_SECONDS, 8 * 60 * 60)
        parser = guard.build_parser()
        args = parser.parse_args(["run", "--", "true"])
        self.assertEqual(args.timeout, 8 * 60 * 60)

    def test_duration_rejects_over_eight_hours(self) -> None:
        with self.assertRaises(argparse.ArgumentTypeError):
            guard.parse_duration("9h")

    def test_duration_rejects_garbage(self) -> None:
        with self.assertRaises(argparse.ArgumentTypeError):
            guard.parse_duration("tomorrow")


class ProcessDetectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.proc = make_proc(
            self.root,
            processes=[
                (100, ["opencode"], 800000),
                (101, ["opencode", "run", "hello"], 600000),
                (102, ["opencode", "stats"], 500000),
                (13615, ["java", "-jar", "/home/iffi/qortium-preview/qortium.jar"], 3500000),
                (200, ["sleep", "300"], 1000),
            ],
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_heavy_opencode_detection(self) -> None:
        found = guard.find_heavy_opencode(self.proc, 128)
        self.assertEqual([process.pid for process in found], [100, 101])

    def test_helper_command_is_ignored(self) -> None:
        self.assertFalse(guard.command_is_heavy_opencode(["opencode", "stats"]))
        self.assertFalse(guard.command_is_heavy_opencode(["opencode", "session", "list"]))
        self.assertTrue(guard.command_is_heavy_opencode(["opencode"]))
        self.assertTrue(guard.command_is_heavy_opencode(["/home/iffi/.opencode/bin/opencode", "run", "x"]))
        self.assertFalse(guard.command_is_heavy_opencode(["python3", "script.py"]))

    def test_qortium_detection_is_read_only(self) -> None:
        found = guard.find_qortium(self.proc, "qortium.jar")
        self.assertEqual([process.pid for process in found], [13615])
        self.assertEqual(found[0].argv[0], "java")

    def test_safe_target_rejects_unsafe_groups(self) -> None:
        with self.assertRaises(guard.GuardError):
            guard.assert_safe_target(1, set())
        with self.assertRaises(guard.GuardError):
            guard.assert_safe_target(13615, {13615})


class EvaluationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def snapshot(self, available_kib: int = 8 * 1024 * 1024, load5: float = 1.0, processes=None):
        proc = make_proc(self.root, available_kib=available_kib, load5=load5, processes=processes)
        return guard.collect_snapshot(CONTROL_PLANE, proc, "qortium.jar", 128)

    def test_pass(self) -> None:
        decision = guard.evaluate(self.snapshot(), 3.0, 1.5, 5.0, 0.0, False)
        self.assertEqual(decision.status, "PASS")
        self.assertEqual(decision.exit_code, guard.EXIT_PASS)

    def test_ram_warning(self) -> None:
        decision = guard.evaluate(self.snapshot(available_kib=2 * 1024 * 1024), 3.0, 1.5, 5.0, 20.0, False)
        self.assertEqual(decision.status, "WARN")
        self.assertEqual(decision.exit_code, guard.EXIT_WARN)

    def test_ram_refusal(self) -> None:
        decision = guard.evaluate(self.snapshot(available_kib=1024 * 1024), 3.0, 1.5, 5.0, 20.0, False)
        self.assertEqual(decision.status, "REFUSE")
        self.assertEqual(decision.exit_code, guard.EXIT_REFUSE)

    def test_load_warning(self) -> None:
        decision = guard.evaluate(self.snapshot(load5=6.0), 3.0, 1.5, 5.0, 20.0, False)
        self.assertEqual(decision.status, "WARN")

    def test_disk_warning(self) -> None:
        snapshot = self.snapshot()
        snapshot.disk_available_bytes = 10 * guard.GIB
        decision = guard.evaluate(snapshot, 3.0, 1.5, 5.0, 20.0, False)
        self.assertEqual(decision.status, "WARN")

    def test_second_heavy_opencode_refuses(self) -> None:
        snapshot = self.snapshot(
            processes=[
                (100, ["opencode"], 800000),
                (101, ["opencode", "run", "hello"], 600000),
            ]
        )
        decision = guard.evaluate(snapshot, 3.0, 1.5, 5.0, 20.0, False)
        self.assertEqual(decision.status, "REFUSE")

    def test_existing_session_refuses_new_opencode(self) -> None:
        snapshot = self.snapshot()
        decision = guard.evaluate(snapshot, 3.0, 1.5, 5.0, 20.0, True)
        self.assertEqual(decision.status, "REFUSE")

    def test_existing_session_allows_non_opencode_dry_run(self) -> None:
        snapshot = self.snapshot()
        decision = guard.evaluate(snapshot, 3.0, 1.5, 5.0, 0.0, False)
        self.assertEqual(decision.status, "PASS")


class CommandTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.proc = make_proc(self.root)
        self.lock = self.root / "guard.lock"
        self.log = self.root / "guard.log"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def check_args(self, *extra: str) -> list[str]:
        return [
            "check",
            "--proc-root",
            str(self.proc),
            "--workspace",
            str(CONTROL_PLANE),
            "--warn-disk-gib",
            "0",
            *extra,
        ]

    def test_check_pass(self) -> None:
        result = run_guard(self.check_args())
        self.assertEqual(result.returncode, guard.EXIT_PASS, result.stdout + result.stderr)
        self.assertIn("PASS", result.stdout)

    def test_check_ram_warning(self) -> None:
        proc = make_proc(self.root / "warn", available_kib=2 * 1024 * 1024)
        result = run_guard(["check", "--proc-root", str(proc), "--workspace", str(CONTROL_PLANE)])
        self.assertEqual(result.returncode, guard.EXIT_WARN, result.stdout + result.stderr)
        self.assertIn("WARN", result.stdout)

    def test_check_ram_refusal(self) -> None:
        proc = make_proc(self.root / "refuse", available_kib=1024 * 1024)
        result = run_guard(["check", "--proc-root", str(proc), "--workspace", str(CONTROL_PLANE)])
        self.assertEqual(result.returncode, guard.EXIT_REFUSE, result.stdout + result.stderr)
        self.assertIn("REFUSE", result.stdout)

    def test_check_json(self) -> None:
        result = run_guard(self.check_args("--json"))
        self.assertEqual(result.returncode, guard.EXIT_PASS, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "PASS")

    def test_run_refuses_when_opencode_already_running(self) -> None:
        result = run_guard(
            [
                "run",
                "--proc-root",
                str(self.proc),
                "--workspace",
                str(CONTROL_PLANE),
                "--lock-file",
                str(self.lock),
                "--log",
                str(self.log),
                "--",
                "opencode",
                "run",
                "test",
            ]
        )
        self.assertEqual(result.returncode, guard.EXIT_REFUSE, result.stdout + result.stderr)
        self.assertIn("REFUSE", result.stdout)

    def test_run_allows_harmless_non_opencode_command(self) -> None:
        result = run_guard(
            [
                "run",
                "--timeout",
                "5s",
                "--proc-root",
                str(self.proc),
                "--workspace",
                str(CONTROL_PLANE),
                "--lock-file",
                str(self.lock),
                "--log",
                str(self.log),
                "--",
                "sh",
                "-c",
                "printf 'dry-run-ok\\n'",
            ]
        )
        self.assertEqual(result.returncode, guard.EXIT_PASS, result.stdout + result.stderr)
        self.assertIn("dry-run-ok", result.stdout)
        self.assertTrue(self.log.exists())

    def test_run_writes_pid_file(self) -> None:
        pid_file = self.root / "child.pid.json"
        result = run_guard(
            [
                "run",
                "--timeout",
                "5s",
                "--proc-root",
                str(self.proc),
                "--workspace",
                str(CONTROL_PLANE),
                "--lock-file",
                str(self.lock),
                "--log",
                str(self.log),
                "--pid-file",
                str(pid_file),
                "--",
                "sh",
                "-c",
                "printf 'pid-file-ok\\n'",
            ]
        )
        self.assertEqual(result.returncode, guard.EXIT_PASS, result.stdout + result.stderr)
        payload = json.loads(pid_file.read_text(encoding="utf-8"))
        self.assertIsInstance(payload["pid"], int)
        self.assertEqual(payload["pid"], payload["pgid"])

    def test_lock_conflict_refuses_second_guard(self) -> None:
        first = subprocess.Popen(
            [
                sys.executable,
                str(GUARD),
                "run",
                "--timeout",
                "30s",
                "--proc-root",
                str(self.proc),
                "--workspace",
                str(CONTROL_PLANE),
                "--lock-file",
                str(self.lock),
                "--log",
                str(self.log),
                "--",
                "sh",
                "-c",
                "printf 'started\\n'; sleep 30",
            ],
            cwd=CONTROL_PLANE,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        try:
            assert first.stdout is not None
            for _ in range(30):
                line = first.stdout.readline()
                if "started" in line:
                    break
            second = run_guard(
                [
                    "run",
                    "--timeout",
                    "1s",
                    "--proc-root",
                    str(self.proc),
                    "--workspace",
                    str(CONTROL_PLANE),
                    "--lock-file",
                    str(self.lock),
                    "--log",
                    str(self.root / "second.log"),
                    "--",
                    "sh",
                    "-c",
                    "true",
                ]
            )
            self.assertEqual(second.returncode, guard.EXIT_REFUSE, second.stdout + second.stderr)
            self.assertIn("another guard holds", second.stderr)
        finally:
            first.send_signal(signal.SIGINT)
            first.communicate(timeout=15)
        self.assertEqual(first.returncode, 130)


class TimeoutTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.proc = make_proc(self.root)
        self.lock = self.root / "guard.lock"
        self.log = self.root / "guard.log"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def child_script(self) -> tuple[list[str], Path]:
        pidfile = self.root / "child.pid"
        script = (
            "import subprocess,sys,time;"
            "p=subprocess.Popen(['sleep','300']);"
            "open(sys.argv[1],'w').write(str(p.pid));"
            "time.sleep(300)"
        )
        return [sys.executable, "-c", script, str(pidfile)], pidfile

    def run_args(self, command: list[str]) -> list[str]:
        return [
            "run",
            "--timeout",
            "1s",
            "--term-grace",
            "1",
            "--proc-root",
            str(self.proc),
            "--workspace",
            str(CONTROL_PLANE),
            "--lock-file",
            str(self.lock),
            "--log",
            str(self.log),
            "--",
            *command,
        ]

    def test_timeout_kills_child_group(self) -> None:
        command, pidfile = self.child_script()
        result = run_guard(self.run_args(command), timeout=20)
        self.assertEqual(result.returncode, guard.EXIT_TIMEOUT, result.stdout + result.stderr)
        self.assertTrue(wait_for_file(pidfile))
        child_pid = int(pidfile.read_text(encoding="utf-8"))
        self.assertTrue(wait_until_gone(child_pid), f"child {child_pid} survived timeout")
        self.assertIn("TIMEOUT", self.log.read_text(encoding="utf-8"))

    def test_sigint_cancels_child_group(self) -> None:
        command, pidfile = self.child_script()
        process = subprocess.Popen(
            [sys.executable, str(GUARD), *self.run_args(command)],
            cwd=CONTROL_PLANE,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        try:
            self.assertTrue(wait_for_file(pidfile), "child did not start")
            child_pid = int(pidfile.read_text(encoding="utf-8"))
            process.send_signal(signal.SIGINT)
            output, _ = process.communicate(timeout=15)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
        self.assertEqual(process.returncode, 130, output)
        self.assertTrue(wait_until_gone(child_pid), f"child {child_pid} survived SIGINT")

    def test_unrelated_process_group_survives(self) -> None:
        sentinel = subprocess.Popen(["sleep", "300"], start_new_session=True)
        try:
            command, pidfile = self.child_script()
            result = run_guard(self.run_args(command), timeout=20)
            self.assertEqual(result.returncode, guard.EXIT_TIMEOUT, result.stdout + result.stderr)
            self.assertIsNone(sentinel.poll(), "guard signalled an unrelated process group")
        finally:
            sentinel.terminate()
            sentinel.wait(timeout=5)


class PermissionProfileTests(unittest.TestCase):
    def test_profile_is_restricted(self) -> None:
        text = AGENT.read_text(encoding="utf-8")
        for expected in (
            "mode: primary",
            "steps: 500",
            'question: deny',
            'task: deny',
            '"**/.env": deny',
            '"sudo *": deny',
            '"systemctl *": deny',
            '"systemd-run *": deny',
            '"kill *": deny',
            '"pkill *": deny',
            '"tmux kill-server*": deny',
            '"opencode serve*": deny',
            '"git push *": deny',
            '"git merge *": deny',
            '"gh *": deny',
            '"qortium*": deny',
            '"qortal*": deny',
            '"/home/iffi/qortium-preview/**": deny',
        ):
            self.assertIn(expected, text, expected)

    def test_development_profile_keeps_hard_boundaries(self) -> None:
        text = DEV_AGENT.read_text(encoding="utf-8")
        for expected in (
            "mode: primary",
            "steps: 1000",
            "question: deny",
            "doom_loop: deny",
            '"*": deny',
            '"sudo *": deny',
            '"apt *": deny',
            '"systemctl *": deny',
            '"kill *": deny',
            '"pkill *": deny',
            '"git push --force*": deny',
            '"gh pr merge*": deny',
            '"qortium*": deny',
            '"java *qortium*": deny',
            '"*qortium-preview*": deny',
            '"**/qortium-preview/**": deny',
            '"/home/iffi/dev-workspace/**": allow',
            '"/home/iffi/qortium-preview/**": allow',
            '"systemctl status*": allow',
            '"journalctl *--vacuum*": deny',
        ):
            self.assertIn(expected, text, expected)
        # Normal development and read-only diagnostics must not be blanket-denied.
        self.assertNotIn('"git push *": deny', text)
        self.assertNotIn('"qortal*": deny', text)
        self.assertNotIn('"ssh *": deny', text)
        self.assertNotIn('"journalctl *": deny', text)

    @unittest.skipUnless(shutil.which("opencode"), "opencode is not installed")
    def test_installed_profile_loads_with_restrictions(self) -> None:
        installed = Path.home() / ".config/opencode/agents/opencode-unattended.md"
        if not installed.exists():
            self.skipTest("installed unattended agent is absent")
        result = subprocess.run(
            ["opencode", "debug", "agent", "opencode-unattended"],
            text=True,
            capture_output=True,
            check=False,
            timeout=20,
        )
        if result.returncode != 0:
            self.skipTest("opencode debug agent unavailable")
        payload = json.loads(result.stdout)
        self.assertEqual(payload.get("steps"), 500)
        permissions = {
            (item.get("permission"), item.get("pattern")): item.get("action")
            for item in payload.get("permission", [])
        }
        self.assertEqual(permissions.get(("question", "*")), "deny")
        self.assertEqual(permissions.get(("bash", "git push *")), "deny")
        self.assertEqual(permissions.get(("bash", "qortium*")), "deny")
        self.assertEqual(permissions.get(("external_directory", "/home/iffi/qortium-preview/**")), "deny")


def main() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
