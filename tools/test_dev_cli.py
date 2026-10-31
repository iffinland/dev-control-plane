#!/usr/bin/env python3
"""Tests for the Workflow v3 development CLI.

The integration tests use a disposable fake `opencode` executable, a synthetic
procfs root and a temporary XDG state directory. They never start a real
OpenCode model session, never signal Qortium and never touch the live node.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
CONTROL_PLANE = TOOLS.parent
DEV = TOOLS / "dev.py"
sys.path.insert(0, str(TOOLS))

from devjob import detect, notify, runner  # noqa: E402
from devjob.store import load_job, list_jobs, save_job, state_root  # noqa: E402


def write_process(proc_root: Path, pid: int, argv: list[str], rss_kib: int) -> None:
    directory = proc_root / str(pid)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "cmdline").write_bytes(b"\0".join(item.encode() for item in argv) + b"\0")
    (directory / "comm").write_text(f"{Path(argv[0]).name}\n", encoding="utf-8")
    (directory / "status").write_text(
        f"Name:\t{Path(argv[0]).name}\nVmRSS:\t{rss_kib} kB\n",
        encoding="utf-8",
    )


def wait_until_gone(pid: int, timeout: float = 10.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        time.sleep(0.05)
    return False


def make_empty_proc(root: Path) -> Path:
    proc = root / "proc"
    proc.mkdir(parents=True, exist_ok=True)
    (proc / "meminfo").write_text(
        "MemTotal:       12548681 kB\n"
        "MemAvailable:    8388608 kB\n"
        "SwapTotal:             0 kB\n"
        "SwapFree:              0 kB\n",
        encoding="utf-8",
    )
    (proc / "loadavg").write_text("0.10 0.10 0.10 1/100 1\n", encoding="utf-8")
    (proc / "swaps").write_text("Filename\tType\tSize\tUsed\tPriority\n", encoding="utf-8")
    return proc


FAKE_OPENCODE = r'''#!/usr/bin/env python3
import json
import os
import sys
import time

state = os.environ.get("FAKE_OPENCODE_STATE", "")
mode = os.environ.get("FAKE_OPENCODE_MODE", "success")
repo = os.environ.get("FAKE_OPENCODE_REPO", os.getcwd())
os.makedirs(state, exist_ok=True)
session_file = os.path.join(state, "session.json")
args = sys.argv[1:]


def find_arg(name):
    for index, value in enumerate(args[:-1]):
        if value == name:
            return args[index + 1]
    return None


if args[:2] == ["session", "list"]:
    if os.path.exists(session_file):
        with open(session_file, encoding="utf-8") as handle:
            print(json.dumps([json.load(handle)]))
    else:
        print("[]")
    sys.exit(0)

if args and args[0] == "export":
    export_file = os.environ.get("FAKE_OPENCODE_EXPORT", "")
    if export_file and os.path.exists(export_file):
        with open(export_file, encoding="utf-8") as handle:
            sys.stdout.write(handle.read())
    sys.exit(0)

if not args or args[0] != "run":
    print("fake opencode helper")
    sys.exit(0)

title = find_arg("--title")
session = find_arg("--session")
if title:
    with open(session_file, "w", encoding="utf-8") as handle:
        json.dump({"id": "ses_fake123", "title": title, "directory": repo}, handle)

if mode == "timeout":
    print("fake run sleeping until the guard kills it", flush=True)
    time.sleep(300)
    sys.exit(0)
if mode == "permission":
    print("Permission denied: bash command rejected by policy")
    sys.exit(0)
if mode == "missing":
    print("bash: needed-tool: command not found")
    sys.exit(0)
if mode == "steps":
    print("Reached the maximum number of steps for this agent")
    sys.exit(0)
if mode == "incomplete":
    print("The implementation is incomplete")
    sys.exit(0)
if mode == "noise":
    print("auto-rejected in a non-interactive run. The full model, the development policy")
    print('     @unittest.skipUnless(shutil.which("opencode"), "opencode is not installed")')
    print('+        self.assertNotIn(\'"ssh *": deny\', text)')
    print("fake opencode run completed")
    sys.exit(0)
if mode == "hang":
    now = int(time.time() * 1000)
    payload = {
        "info": {"id": "ses_fake123", "title": title or "fake", "time": {"updated": now}},
        "messages": [
            {
                "info": {
                    "id": "msg_final",
                    "role": "assistant",
                    "finish": "stop",
                    "time": {"created": now, "completed": now},
                },
                "parts": [],
            }
        ],
    }
    export_file = os.environ.get("FAKE_OPENCODE_EXPORT", "")
    if export_file:
        with open(export_file, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)
    pid_file = os.environ.get("FAKE_OPENCODE_PIDFILE", "")
    if pid_file:
        with open(pid_file, "w", encoding="utf-8") as handle:
            handle.write(str(os.getpid()))
    print("fake run produced a final assistant message and will hang", flush=True)
    time.sleep(300)
    sys.exit(0)
if mode == "resume":
    print("continuing the existing session")
    if session:
        with open(os.path.join(repo, "impl.txt"), "w", encoding="utf-8") as handle:
            handle.write("complete\n")
    sys.exit(0)
if mode == "exit1":
    print("a command failed with exit code 1")
    sys.exit(1)
print("fake opencode run completed")
sys.exit(0)
'''


class CliTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="dev-cli-test-")
        self.root = Path(self.temp.name)
        self.state = self.root / "state"
        self.state.mkdir()
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.proc = make_empty_proc(self.root)
        self.bin_dir = self.root / "bin"
        self.bin_dir.mkdir()
        fake = self.bin_dir / "opencode"
        fake.write_text(FAKE_OPENCODE, encoding="utf-8")
        fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
        self.fake_state = self.root / "fake-state"
        self.fake_state.mkdir()
        self.env = os.environ.copy()
        self.env["PATH"] = f"{self.bin_dir}:{self.env.get('PATH', '')}"
        self.env["DEV_CONTROL_PLANE_STATE"] = str(self.state)
        self.env["DEV_TELEGRAM_CONFIG"] = str(self.root / "missing-telegram.json")
        self.env["DEV_TELEGRAM_ENABLED"] = "0"
        self.env["FAKE_OPENCODE_STATE"] = str(self.fake_state)
        self.env["FAKE_OPENCODE_REPO"] = str(self.repo)
        self.env["FAKE_OPENCODE_MODE"] = "success"
        self.env["FAKE_OPENCODE_EXPORT"] = ""
        self.env["FAKE_OPENCODE_PIDFILE"] = ""
        # Keep the guard's completion watchdog fast and deterministic in tests.
        self.env["DEV_SESSION_POLL_SECONDS"] = "0.1"
        self.env["DEV_SESSION_IDLE_SECONDS"] = "0.2"
        self.env["DEV_SESSION_CONFIRM_SECONDS"] = "0.2"

    def set_export(self, messages: list[dict]) -> None:
        path = self.root / "opencode-export.json"
        path.write_text(json.dumps({"info": {"id": "ses_fake123"}, "messages": messages}), encoding="utf-8")
        self.env["FAKE_OPENCODE_EXPORT"] = str(path)

    def tearDown(self) -> None:
        for job in list_jobs(self.state):
            pid = job.get("worker_pid")
            if not pid:
                continue
            try:
                cmdline = Path(f"/proc/{pid}/cmdline").read_bytes().decode("utf-8", "replace")
            except OSError:
                continue
            if "_worker" in cmdline and str(self.state) in cmdline:
                try:
                    os.kill(pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
        time.sleep(0.1)
        self.temp.cleanup()

    def cli(self, *args: str, timeout: float = 30.0) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(DEV), *args],
            cwd=CONTROL_PLANE,
            env=self.env,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )

    def start(
        self,
        *,
        mode: str = "success",
        criterion: str | None = None,
        manual: str | None = None,
        timeout: str = "10s",
    ) -> dict:
        self.env["FAKE_OPENCODE_MODE"] = mode
        args = [
            "start",
            "--state-dir",
            str(self.state),
            "--title",
            f"test-{mode}",
            "--repo",
            str(self.repo),
            "--prompt",
            "Do the authorized development work.",
            "--criterion",
            criterion or "python3 -c \"print('accepted')\"",
            "--timeout",
            timeout,
            "--proc-root",
            str(self.proc),
            "--workspace",
            str(self.workspace),
            "--no-notify",
            "--json",
        ]
        if manual:
            args.extend(["--manual-criterion", manual])
        result = self.cli(*args)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def wait_for_state(self, job_id: str, timeout: float = 30.0) -> dict:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            result = self.cli("status", "--state-dir", str(self.state), job_id, "--json")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            if payload["state"] != "RUNNING":
                return payload
            time.sleep(0.2)
        self.fail(f"job {job_id} did not reach a terminal state")

    def test_success_requires_verified_acceptance(self) -> None:
        job = self.start(mode="success")
        payload = self.wait_for_state(job["id"])
        self.assertEqual(payload["state"], "SUCCESS", payload)
        self.assertEqual(payload["exit_code"], 0)
        stored = load_job(job["id"], self.state)
        self.assertTrue(stored["verification"]["AC1"]["verified"])

    def test_exit_zero_with_failing_acceptance_is_failed(self) -> None:
        job = self.start(mode="success", criterion="python3 -c \"raise SystemExit(1)\"")
        payload = self.wait_for_state(job["id"])
        self.assertEqual(payload["state"], "FAILED", payload)
        self.assertEqual(payload["exit_code"], 0)
        kinds = {issue["kind"] for issue in payload["issues"]}
        self.assertIn("incomplete_implementation", kinds)

    def test_permission_rejection_is_blocked(self) -> None:
        job = self.start(mode="permission")
        payload = self.wait_for_state(job["id"])
        self.assertEqual(payload["state"], "BLOCKED", payload)
        self.assertIn("permission_rejection", {issue["kind"] for issue in payload["issues"]})

    def test_missing_dependency_is_blocked(self) -> None:
        job = self.start(mode="missing")
        payload = self.wait_for_state(job["id"])
        self.assertEqual(payload["state"], "BLOCKED", payload)
        self.assertIn("missing_dependency", {issue["kind"] for issue in payload["issues"]})

    def test_step_exhaustion_is_failed(self) -> None:
        job = self.start(mode="steps")
        payload = self.wait_for_state(job["id"])
        self.assertEqual(payload["state"], "FAILED", payload)
        self.assertIn("step_exhaustion", {issue["kind"] for issue in payload["issues"]})

    def test_incomplete_implementation_is_failed(self) -> None:
        job = self.start(mode="incomplete")
        payload = self.wait_for_state(job["id"])
        self.assertEqual(payload["state"], "FAILED", payload)
        self.assertIn("incomplete_implementation", {issue["kind"] for issue in payload["issues"]})

    def test_noisy_log_does_not_trigger_documentation_false_positives(self) -> None:
        job = self.start(mode="noise")
        payload = self.wait_for_state(job["id"])
        self.assertEqual(payload["state"], "SUCCESS", payload)
        self.assertEqual(payload["issues"], [])

    def test_structured_success_ignores_documentation_and_source_text(self) -> None:
        self.set_export(
            [
                {
                    "info": {"role": "assistant"},
                    "parts": [
                        {
                            "type": "tool",
                            "tool": "bash",
                            "state": {
                                "status": "completed",
                                "metadata": {"exit": 0},
                                "output": "auto-rejected in a non-interactive run.\n"
                                '     @unittest.skipUnless(shutil.which("opencode"), "opencode is not installed")',
                            },
                        },
                        {
                            "type": "tool",
                            "tool": "read",
                            "state": {
                                "status": "completed",
                                "output": "Permission denied: documentation example\ncommand not found: source example",
                            },
                        },
                    ],
                }
            ]
        )
        job = self.start(mode="noise")
        payload = self.wait_for_state(job["id"])
        self.assertEqual(payload["state"], "SUCCESS", payload)
        self.assertEqual(payload["issues"], [])

    def test_structured_permission_denial_blocks(self) -> None:
        self.set_export(
            [
                {
                    "info": {"role": "assistant"},
                    "parts": [
                        {
                            "type": "tool",
                            "tool": "bash",
                            "state": {
                                "status": "error",
                                "error": "The user has specified a rule which prevents you from using this specific tool call.",
                            },
                        }
                    ],
                }
            ]
        )
        job = self.start(mode="success")
        payload = self.wait_for_state(job["id"])
        self.assertEqual(payload["state"], "BLOCKED", payload)
        self.assertIn("permission_rejection", {issue["kind"] for issue in payload["issues"]})

    def test_recovered_permission_does_not_block_success(self) -> None:
        self.set_export(
            [
                {
                    "info": {"role": "assistant"},
                    "parts": [
                        {
                            "type": "tool",
                            "tool": "bash",
                            "state": {
                                "status": "error",
                                "error": "The user has specified a rule which prevents you from using this specific tool call.",
                                "input": {
                                    "command": "cat ~/.local/state/dev-control-plane/jobs/example/job.json"
                                },
                            },
                        }
                    ],
                },
                {
                    "info": {"role": "assistant"},
                    "parts": [
                        {
                            "type": "tool",
                            "tool": "bash",
                            "state": {
                                "status": "completed",
                                "metadata": {"exit": 0},
                                "output": "job state read",
                                "input": {"command": "python3 tools/dev.py status --json"},
                            },
                        }
                    ],
                },
            ]
        )
        job = self.start(mode="success")
        payload = self.wait_for_state(job["id"])
        self.assertEqual(payload["state"], "SUCCESS", payload)
        permission = [
            issue for issue in payload["issues"] if issue["kind"] == "permission_rejection"
        ]
        self.assertEqual(len(permission), 1)
        self.assertTrue(permission[0]["recovered"])
        self.assertEqual(permission[0]["severity"], "warning")

    def test_unresolved_permission_blocks_even_with_passing_acceptance(self) -> None:
        self.set_export(
            [
                {
                    "info": {"role": "assistant"},
                    "parts": [
                        {
                            "type": "tool",
                            "tool": "bash",
                            "state": {
                                "status": "completed",
                                "metadata": {"exit": 0},
                                "output": "ok",
                                "input": {"command": "git status"},
                            },
                        }
                    ],
                },
                {
                    "info": {"role": "assistant"},
                    "parts": [
                        {
                            "type": "tool",
                            "tool": "bash",
                            "state": {
                                "status": "error",
                                "error": "The user has specified a rule which prevents you from using this specific tool call.",
                                "input": {"command": "cat /home/iffi/qortium-data/blockchain.data"},
                            },
                        }
                    ],
                },
            ]
        )
        job = self.start(mode="success")
        payload = self.wait_for_state(job["id"])
        self.assertEqual(payload["state"], "BLOCKED", payload)
        permission = [
            issue for issue in payload["issues"] if issue["kind"] == "permission_rejection"
        ]
        self.assertEqual(len(permission), 1)
        self.assertFalse(permission[0]["recovered"])

    def test_recovered_permission_does_not_hide_acceptance_failure(self) -> None:
        self.set_export(
            [
                {
                    "info": {"role": "assistant"},
                    "parts": [
                        {
                            "type": "tool",
                            "tool": "bash",
                            "state": {
                                "status": "error",
                                "error": "The user has specified a rule which prevents you from using this specific tool call.",
                            },
                        }
                    ],
                },
                {
                    "info": {"role": "assistant"},
                    "parts": [
                        {
                            "type": "tool",
                            "tool": "bash",
                            "state": {"status": "completed", "metadata": {"exit": 0}, "output": "ok"},
                        }
                    ],
                },
            ]
        )
        job = self.start(mode="success", criterion="python3 -c \"raise SystemExit(1)\"")
        payload = self.wait_for_state(job["id"])
        self.assertEqual(payload["state"], "FAILED", payload)
        self.assertIn(
            "incomplete_implementation",
            {issue["kind"] for issue in payload["issues"]},
        )
        permission = [
            issue for issue in payload["issues"] if issue["kind"] == "permission_rejection"
        ]
        self.assertTrue(permission[0]["recovered"])

    def test_recovered_failed_command_does_not_block_success(self) -> None:
        self.set_export(
            [
                {
                    "info": {"role": "assistant"},
                    "parts": [
                        {
                            "type": "tool",
                            "tool": "bash",
                            "state": {
                                "status": "completed",
                                "metadata": {"exit": 2},
                                "output": "docs/example.md:1: trailing whitespace.",
                                "input": {"command": "git diff --check && git status --short"},
                            },
                        }
                    ],
                },
                {
                    "info": {"role": "assistant"},
                    "parts": [
                        {
                            "type": "tool",
                            "tool": "bash",
                            "state": {
                                "status": "completed",
                                "metadata": {"exit": 0},
                                "output": "OUR DIFF CLEAN",
                                "input": {"command": "git diff --check -- tools/example.py"},
                            },
                        }
                    ],
                },
            ]
        )
        job = self.start(mode="success")
        payload = self.wait_for_state(job["id"])
        self.assertEqual(payload["state"], "SUCCESS", payload)
        failed = [
            issue for issue in payload["issues"] if issue["kind"] == "failed_command"
        ]
        self.assertEqual(len(failed), 1)
        self.assertTrue(failed[0]["recovered"])

    def test_unrelated_success_does_not_recover_failed_command(self) -> None:
        self.set_export(
            [
                {
                    "info": {"role": "assistant"},
                    "parts": [
                        {
                            "type": "tool",
                            "tool": "bash",
                            "state": {
                                "status": "completed",
                                "metadata": {"exit": 1},
                                "output": "FAILED (failures=1)",
                                "input": {"command": "npm test"},
                            },
                        }
                    ],
                },
                {
                    "info": {"role": "assistant"},
                    "parts": [
                        {
                            "type": "tool",
                            "tool": "bash",
                            "state": {
                                "status": "completed",
                                "metadata": {"exit": 0},
                                "output": "ok",
                                "input": {"command": "ls -la"},
                            },
                        }
                    ],
                },
            ]
        )
        job = self.start(mode="success")
        payload = self.wait_for_state(job["id"])
        self.assertEqual(payload["state"], "FAILED", payload)
        failed = [
            issue for issue in payload["issues"] if issue["kind"] == "failed_command"
        ]
        self.assertFalse(failed[0]["recovered"])

    def test_structured_missing_dependency_blocks(self) -> None:
        self.set_export(
            [
                {
                    "info": {"role": "assistant"},
                    "parts": [
                        {
                            "type": "tool",
                            "tool": "bash",
                            "state": {
                                "status": "completed",
                                "metadata": {"exit": 1},
                                "output": "bash: vitest: command not found",
                            },
                        }
                    ],
                }
            ]
        )
        job = self.start(mode="success")
        payload = self.wait_for_state(job["id"])
        self.assertEqual(payload["state"], "BLOCKED", payload)
        self.assertIn("missing_dependency", {issue["kind"] for issue in payload["issues"]})

    def test_structured_failed_command_fails(self) -> None:
        self.set_export(
            [
                {
                    "info": {"role": "assistant"},
                    "parts": [
                        {
                            "type": "tool",
                            "tool": "bash",
                            "state": {
                                "status": "completed",
                                "metadata": {"exit": 1},
                                "output": "FAILED (failures=1)",
                            },
                        }
                    ],
                }
            ]
        )
        job = self.start(mode="success")
        payload = self.wait_for_state(job["id"])
        self.assertEqual(payload["state"], "FAILED", payload)
        self.assertIn("failed_command", {issue["kind"] for issue in payload["issues"]})

    def test_structured_step_exhaustion_fails(self) -> None:
        self.set_export(
            [
                {
                    "info": {"role": "assistant"},
                    "parts": [
                        {
                            "type": "text",
                            "text": "Reached the maximum number of steps for this agent",
                        }
                    ],
                }
            ]
        )
        job = self.start(mode="success")
        payload = self.wait_for_state(job["id"])
        self.assertEqual(payload["state"], "FAILED", payload)
        self.assertIn("step_exhaustion", {issue["kind"] for issue in payload["issues"]})

    def test_structured_user_text_is_not_scanned(self) -> None:
        self.set_export(
            [
                {
                    "info": {"role": "user"},
                    "parts": [
                        {
                            "type": "text",
                            "text": "permission denied; command not found; The implementation is incomplete",
                        }
                    ],
                }
            ]
        )
        job = self.start(mode="success")
        payload = self.wait_for_state(job["id"])
        self.assertEqual(payload["state"], "SUCCESS", payload)
        self.assertEqual(payload["issues"], [])

    def test_timeout_is_timeout(self) -> None:
        job = self.start(mode="timeout", timeout="1s")
        payload = self.wait_for_state(job["id"], timeout=25)
        self.assertEqual(payload["state"], "TIMEOUT", payload)
        self.assertEqual(payload["exit_code"], 124)

    def test_hung_cli_after_structured_completion_is_success(self) -> None:
        export_path = self.root / "completion-export.json"
        pid_path = self.root / "hang.pid"
        self.env["FAKE_OPENCODE_EXPORT"] = str(export_path)
        self.env["FAKE_OPENCODE_PIDFILE"] = str(pid_path)
        job = self.start(mode="hang", timeout="20s")
        payload = self.wait_for_state(job["id"], timeout=35)
        self.assertEqual(payload["state"], "SUCCESS", payload)
        self.assertEqual(payload["exit_code"], 0)
        self.assertIsNotNone(payload["completion"], payload)
        self.assertEqual(payload["completion"]["finish"], "stop")
        self.assertEqual(payload["completion"]["active_tool_calls"], 0)
        stored = load_job(job["id"], self.state)
        self.assertEqual(
            stored["attempts"][-1]["completion"]["action"],
            "session_completed_cli_stopped",
        )
        self.assertTrue(pid_path.exists(), "fake run did not record its pid")
        self.assertTrue(
            wait_until_gone(int(pid_path.read_text(encoding="utf-8"))),
            "the hung fake OpenCode process was not stopped",
        )

    def test_hung_cli_completion_still_requires_acceptance(self) -> None:
        export_path = self.root / "completion-export-fail.json"
        self.env["FAKE_OPENCODE_EXPORT"] = str(export_path)
        self.env["FAKE_OPENCODE_PIDFILE"] = str(self.root / "hang-fail.pid")
        job = self.start(
            mode="hang",
            criterion="python3 -c \"raise SystemExit(1)\"",
            timeout="20s",
        )
        payload = self.wait_for_state(job["id"], timeout=35)
        self.assertEqual(payload["state"], "FAILED", payload)
        self.assertEqual(payload["exit_code"], 0)
        self.assertIn(
            "incomplete_implementation",
            {issue["kind"] for issue in payload["issues"]},
        )

    def test_logs_and_report_are_persistent(self) -> None:
        job = self.start(mode="success")
        payload = self.wait_for_state(job["id"])
        self.assertEqual(payload["state"], "SUCCESS")
        logs = self.cli("logs", "--state-dir", str(self.state), job["id"], "-n", "200")
        self.assertEqual(logs.returncode, 0, logs.stdout + logs.stderr)
        self.assertIn("fake opencode run completed", logs.stdout)
        report = self.cli("report", "--state-dir", str(self.state), job["id"])
        self.assertEqual(report.returncode, 0, report.stdout + report.stderr)
        self.assertIn("## Acceptance criteria", report.stdout)
        self.assertIn("SUCCESS", report.stdout)
        self.assertTrue(Path(payload["report_path"]).is_file())

    def test_resume_keeps_job_and_continues_session(self) -> None:
        job = self.start(mode="resume", criterion="test -f impl.txt")
        first = self.wait_for_state(job["id"])
        self.assertEqual(first["state"], "FAILED", first)
        self.assertTrue(first["session_id"])
        resume = self.cli("resume", "--state-dir", str(self.state), job["id"], "--json")
        self.assertEqual(resume.returncode, 0, resume.stdout + resume.stderr)
        second = self.wait_for_state(job["id"])
        self.assertEqual(second["state"], "SUCCESS", second)
        self.assertEqual(second["id"], job["id"])
        self.assertGreaterEqual(second["attempts"], 2)
        self.assertEqual(second["resume_count"], 1)
        stored = load_job(job["id"], self.state)
        self.assertEqual(stored["attempts"][-1]["session_id"], "ses_fake123")

    def test_manual_acceptance_can_complete_a_blocked_job(self) -> None:
        job = self.start(mode="success", manual="owner inspects the live app")
        first = self.wait_for_state(job["id"])
        self.assertEqual(first["state"], "BLOCKED", first)
        accepted = self.cli(
            "accept", "--state-dir", str(self.state), job["id"], "--all-manual", "--json"
        )
        self.assertEqual(accepted.returncode, 0, accepted.stdout + accepted.stderr)
        payload = json.loads(accepted.stdout)
        self.assertEqual(payload["state"], "SUCCESS", payload)

    def test_start_requires_explicit_acceptance(self) -> None:
        result = self.cli(
            "start",
            "--state-dir",
            str(self.state),
            "--title",
            "no-criteria",
            "--repo",
            str(self.repo),
            "--prompt",
            "work",
        )
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("explicit acceptance criteria", result.stderr)

    def test_default_timeout_is_eight_hours(self) -> None:
        result = self.cli(
            "start",
            "--state-dir",
            str(self.state),
            "--title",
            "dry-run",
            "--repo",
            str(self.repo),
            "--prompt",
            "work",
            "--criterion",
            "true",
            "--proc-root",
            str(self.proc),
            "--workspace",
            str(self.workspace),
            "--dry-run",
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["timeout_seconds"], 8 * 60 * 60)


class DetectionTests(unittest.TestCase):
    def test_permission_and_dependency(self) -> None:
        issues = detect.scan_text("Permission denied: bash rejected\nnpm ERR! command not found: x\n")
        kinds = {issue.kind for issue in issues}
        self.assertIn("permission_rejection", kinds)
        self.assertIn("missing_dependency", kinds)

    def test_step_and_incomplete(self) -> None:
        issues = detect.scan_text("Reached the maximum number of steps\nThe task is incomplete\n")
        kinds = {issue.kind for issue in issues}
        self.assertIn("step_exhaustion", kinds)
        self.assertIn("incomplete_implementation", kinds)

    def test_guard_metadata_is_not_scanned(self) -> None:
        issues = detect.scan_text("command=echo 'permission denied'\nnormal output\n")
        self.assertEqual(issues, [])


class NotificationTests(unittest.TestCase):
    def settings(self, token: str = "TESTONLYTOKEN") -> notify.TelegramSettings:
        return notify.TelegramSettings(
            enabled=True,
            bot_token=token,
            chat_id="12345",
            events=notify.NOTIFY_STATES,
            timeout_seconds=2,
            config_path=None,
            warnings=[],
        )

    def job(self) -> dict:
        return {
            "id": "job-1",
            "title": "demo",
            "state": "SUCCESS",
            "repo": "/home/iffi/dev-workspace/control-plane",
            "started_at": "2026-10-31T00:00:00Z",
            "ended_at": "2026-10-31T00:01:00Z",
            "duration_seconds": 60,
            "detected_issues": [],
            "report_path": "/tmp/report.md",
            "log_path": "/tmp/run.log",
        }

    def test_message_has_no_credentials(self) -> None:
        text = notify.build_message(self.job())
        self.assertIn("completed", text)
        self.assertNotIn("TESTONLYTOKEN", text)

    def test_send_success_with_fake_transport(self) -> None:
        captured = {}

        def transport(url, payload, timeout):
            captured["url"] = url
            captured["payload"] = payload
            return 200, "ok"

        sent, reason = notify.send_message(self.settings(), "hello", transport)
        self.assertTrue(sent)
        self.assertEqual(reason, "sent")
        self.assertEqual(captured["payload"]["chat_id"], "12345")

    def test_failure_reason_redacts_token(self) -> None:
        def transport(url, payload, timeout):
            return 401, f"bad token {url}"

        sent, reason = notify.send_message(self.settings(), "hello", transport)
        self.assertFalse(sent)
        self.assertNotIn("TESTONLYTOKEN", reason)

    def test_config_is_outside_git_by_default(self) -> None:
        path = notify.config_path()
        self.assertNotIn(str(CONTROL_PLANE), str(path))

    def test_missing_config_is_disabled(self) -> None:
        settings = notify.load_settings(self.root_missing(), environ={"DEV_TELEGRAM_ENABLED": ""})
        self.assertFalse(settings.enabled)

    @staticmethod
    def root_missing() -> Path:
        return Path(tempfile.gettempdir()) / "dev-control-plane-missing-telegram.json"


class StoreTests(unittest.TestCase):
    def test_job_roundtrip_and_listing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            job = {
                "id": "20261031T000000Z-demo-deadbeef",
                "title": "demo",
                "state": "RUNNING",
                "created_at": "2026-10-31T00:00:00Z",
            }
            save_job(job, root)
            loaded = load_job(job["id"], root)
            self.assertEqual(loaded["title"], "demo")
            self.assertEqual([item["id"] for item in list_jobs(root)], [job["id"]])


def main() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
