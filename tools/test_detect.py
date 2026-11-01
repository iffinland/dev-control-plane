#!/usr/bin/env python3
"""Regression tests for Workflow v3 run detection.

The false-positive examples below are taken from the actual run log of job
``20261031T150806Z-workflow-v3-permissions-moderniz-e39072d7``: a documentation
sentence, a source line in a diff and a code string. They must not produce
permission or dependency issues. Real failed-tool blocks must still be detected.
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

TOOLS = Path(__file__).resolve().parent
CONTROL_PLANE = TOOLS.parent
sys.path.insert(0, str(TOOLS))

from devjob import detect  # noqa: E402


NOISY_DOCUMENTATION_LOG = """$ python3 - <<'PY'
### Permission semantics and limitations

OpenCode evaluates permission patterns with **last matching rule wins**; bash
rules match each parsed shell command. Without `--auto`, an `ask` decision is
auto-rejected in a non-interactive run. The full model, the development policy
and the remaining bypasses are documented in
PY
$ git diff -- tools/test_opencode_guard.py
diff --git a/tools/test_opencode_guard.py b/tools/test_opencode_guard.py
index 1234567..89abcde 100644
--- a/tools/test_opencode_guard.py
+++ b/tools/test_opencode_guard.py
@@ -1,3 +1,3 @@
-        self.assertNotIn('"git push *": deny', text)
+        self.assertNotIn('"ssh *": deny', text)
      @unittest.skipUnless(shutil.which("opencode"), "opencode is not installed")
"""


class FalsePositiveRegressionTests(unittest.TestCase):
    def test_actual_documentation_and_diff_lines_are_ignored(self) -> None:
        issues = detect.scan_text(NOISY_DOCUMENTATION_LOG)
        self.assertEqual(issues, [])

    def test_actual_readme_sentence_alone_is_ignored(self) -> None:
        issues = detect.scan_text(
            "auto-rejected in a non-interactive run. The full model, the development policy\n"
        )
        self.assertEqual(issues, [])

    def test_actual_source_diff_line_is_ignored(self) -> None:
        issues = detect.scan_text(
            '      @unittest.skipUnless(shutil.which("opencode"), "opencode is not installed")\n'
        )
        self.assertEqual(issues, [])

    def test_source_code_permission_string_is_ignored(self) -> None:
        issues = detect.scan_text('raise PermissionError("permission denied by policy")\n')
        self.assertEqual(issues, [])

    def test_successful_command_output_is_not_scanned_for_failure_words(self) -> None:
        log = (
            "$ cat docs/notes.md\n"
            "permission denied is an example phrase\n"
            "command not found is another\n"
            "Error: permission denied is documentation\n"
        )
        self.assertEqual(detect.scan_text(log), [])


class RealFailureTests(unittest.TestCase):
    def test_actual_permission_denial_block(self) -> None:
        log = (
            "✗ ls -la ~/.opencode/ ~/.opencode/bin failed\n"
            "Error: The user has specified a rule which prevents you from using this specific tool call. "
            'Here are some of the relevant rules [{"permission":"*","action":"deny"}]\n'
        )
        issues = detect.scan_text(log)
        kinds = {issue.kind for issue in issues}
        self.assertIn("permission_rejection", kinds)
        self.assertTrue(any("rule which prevents" in issue.excerpt for issue in issues))

    def test_failed_bash_command_is_detected(self) -> None:
        issues = detect.scan_text("✗ echo hi > /tmp/opencode/test.txt failed\nFAILED (failures=1)\n")
        self.assertIn("failed_command", {issue.kind for issue in issues})

    def test_missing_dependency_in_failed_block(self) -> None:
        issues = detect.scan_text("✗ npm test failed\nbash: vitest: command not found\n")
        self.assertIn("missing_dependency", {issue.kind for issue in issues})

    def test_non_execution_tool_error_is_not_a_command_failure(self) -> None:
        log = (
            "✗ WebFetch https://example.invalid/missing failed\n"
            "Error: StatusCode: non 2xx status code (404 GET https://example.invalid/missing)\n"
        )
        self.assertEqual(detect.scan_text(log), [])

    def test_step_exhaustion_and_incomplete_text(self) -> None:
        issues = detect.scan_text(
            "Error: Reached the maximum number of steps for this agent\n"
            "The implementation is incomplete\n"
            "BLOCKED: waiting for an owner decision\n"
        )
        kinds = {issue.kind for issue in issues}
        self.assertIn("step_exhaustion", kinds)
        self.assertIn("incomplete_implementation", kinds)
        self.assertIn("blocked_marker", kinds)

    def test_simple_runtime_permission_and_dependency_lines(self) -> None:
        issues = detect.scan_text(
            "Permission denied: bash rejected\nnpm ERR! command not found: x\n"
        )
        kinds = {issue.kind for issue in issues}
        self.assertIn("permission_rejection", kinds)
        self.assertIn("missing_dependency", kinds)


class MissingDependencyClassificationTests(unittest.TestCase):
    """A missing data file is not a missing dependency.

    Job ``20261101T061959Z-qortium-dev-monitor-p3-961a2a11`` was marked BLOCKED
    by a detector excerpt containing ``FileNotFoundError ... job.json`` from a
    failing cancel-test fixture. The underlying test failure was real and had to
    be fixed, but its classification as a missing dependency was wrong.
    """

    @staticmethod
    def payload(output: str) -> dict:
        return {
            "info": {"id": "ses_test"},
            "messages": [
                {
                    "info": {"role": "assistant"},
                    "parts": [
                        {
                            "type": "tool",
                            "tool": "bash",
                            "state": {
                                "status": "completed",
                                "metadata": {"exit": 1},
                                "output": output,
                            },
                        }
                    ],
                }
            ],
        }

    def test_file_not_found_in_traceback_is_a_failed_command(self) -> None:
        output = (
            "Traceback (most recent call last):\n"
            "  File \"/tmp/test_cancel.py\", line 1, in <module>\n"
            "    load_job(job_id)\n"
            "devjob.store.StoreError: job not found: cancel-test\n"
            "FileNotFoundError: [Errno 2] No such file or directory: "
            "'/home/iffi/.local/state/dev-control-plane/jobs/"
            "20261101T120000Z-cancel-test-12345678/job.json'\n"
        )
        kinds = {issue.kind for issue in detect.scan_events(self.payload(output))}
        self.assertIn("failed_command", kinds)
        self.assertNotIn("missing_dependency", kinds)

    def test_file_not_found_in_failed_console_block_is_a_failed_command(self) -> None:
        log = (
            "✗ python3 tools/test_dev_cancel.py failed\n"
            "FileNotFoundError: [Errno 2] No such file or directory: 'job.json'\n"
        )
        kinds = {issue.kind for issue in detect.scan_text(log)}
        self.assertIn("failed_command", kinds)
        self.assertNotIn("missing_dependency", kinds)

    def test_shell_missing_executable_is_still_a_dependency(self) -> None:
        for output in (
            "bash: /opt/missing-tool: No such file or directory",
            "/usr/bin/env: 'python3': No such file or directory",
            "dash: 1: missing-tool: not found",
        ):
            kinds = {issue.kind for issue in detect.scan_events(self.payload(output))}
            self.assertIn("missing_dependency", kinds, output)

    def test_missing_module_and_command_are_still_dependencies(self) -> None:
        for output in (
            "bash: vitest: command not found",
            "ModuleNotFoundError: No module named 'missinglib'",
            "npm ERR! missing dependency: left-pad",
        ):
            kinds = {issue.kind for issue in detect.scan_events(self.payload(output))}
            self.assertIn("missing_dependency", kinds, output)

    def test_missing_regular_file_is_not_a_dependency(self) -> None:
        kinds = {
            issue.kind
            for issue in detect.scan_events(
                self.payload("cat: notes.txt: No such file or directory")
            )
        }
        self.assertIn("failed_command", kinds)
        self.assertNotIn("missing_dependency", kinds)


class ScanOffsetTests(unittest.TestCase):
    def test_scan_log_start_offset_ignores_previous_attempt(self) -> None:
        first = "✗ old command failed\nError: The user has specified a rule which prevents you from using this specific tool call.\n"
        second = "fake opencode run completed\n"
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "run.log"
            path.write_text(first + second, encoding="utf-8")
            self.assertIn("permission_rejection", {issue.kind for issue in detect.scan_log(path)})
            offset = len(first.encode("utf-8"))
            self.assertEqual(detect.scan_log(path, start_offset=offset), [])


class StructuredEventTests(unittest.TestCase):
    @staticmethod
    def payload(messages: list[dict]) -> dict:
        return {"info": {"id": "ses_test"}, "messages": messages}

    def test_successful_tool_output_is_not_scanned(self) -> None:
        payload = self.payload(
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
                                "output": "permission denied\ncommand not found\nopencode is not installed",
                            },
                        }
                    ],
                }
            ]
        )
        self.assertEqual(detect.scan_events(payload), [])

    def test_permission_error(self) -> None:
        payload = self.payload(
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
        self.assertIn("permission_rejection", {issue.kind for issue in detect.scan_events(payload)})

    def test_nonzero_exit_missing_dependency(self) -> None:
        payload = self.payload(
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
        self.assertIn("missing_dependency", {issue.kind for issue in detect.scan_events(payload)})

    def test_nonzero_exit_failed_command(self) -> None:
        payload = self.payload(
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
        self.assertIn("failed_command", {issue.kind for issue in detect.scan_events(payload)})

    def test_permission_rejection_recovered_by_later_success(self) -> None:
        payload = self.payload(
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
                                "input": {"command": "cat ~/.local/state/dev-control-plane/jobs/x/job.json"},
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
                                "input": {"command": "python3 tools/dev.py status --json"},
                            },
                        }
                    ],
                },
            ]
        )
        issues = detect.scan_events(payload)
        permission = [issue for issue in issues if issue.kind == "permission_rejection"]
        self.assertEqual(len(permission), 1)
        self.assertTrue(permission[0].recovered)
        self.assertEqual(permission[0].severity, "warning")
        self.assertIsNone(detect.highest_severity(issues))

    def test_permission_rejection_without_later_success_remains_blocked(self) -> None:
        payload = self.payload(
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
        issues = detect.scan_events(payload)
        permission = [issue for issue in issues if issue.kind == "permission_rejection"]
        self.assertEqual(len(permission), 1)
        self.assertFalse(permission[0].recovered)
        self.assertEqual(detect.highest_severity(issues), "blocked")

    def test_recovered_permission_does_not_hide_later_blocked_marker(self) -> None:
        payload = self.payload(
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
                {
                    "info": {"role": "assistant"},
                    "parts": [{"type": "text", "text": "BLOCKED: owner decision required"}],
                },
            ]
        )
        kinds = {issue.kind: issue for issue in detect.scan_events(payload)}
        self.assertTrue(kinds["permission_rejection"].recovered)
        self.assertEqual(kinds["blocked_marker"].severity, "blocked")

    def test_failed_command_recovered_by_same_operation(self) -> None:
        payload = self.payload(
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
                                "output": "skills/example/SKILL.md:58: trailing whitespace.",
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
                                "input": {"command": "git diff --check -- tools/example.py && echo CLEAN"},
                            },
                        }
                    ],
                },
            ]
        )
        issues = detect.scan_events(payload)
        failed = [issue for issue in issues if issue.kind == "failed_command"]
        self.assertEqual(len(failed), 1)
        self.assertTrue(failed[0].recovered)
        self.assertIsNone(detect.highest_severity(issues))

    def test_failed_command_not_recovered_by_unrelated_success(self) -> None:
        payload = self.payload(
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
        issues = detect.scan_events(payload)
        failed = [issue for issue in issues if issue.kind == "failed_command"]
        self.assertEqual(len(failed), 1)
        self.assertFalse(failed[0].recovered)
        self.assertEqual(detect.highest_severity(issues), "failed")

    def test_failed_command_before_success_is_not_recovered(self) -> None:
        payload = self.payload(
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
                                "input": {"command": "git diff --check"},
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
                                "metadata": {"exit": 2},
                                "output": "trailing whitespace",
                                "input": {"command": "git diff --check"},
                            },
                        }
                    ],
                },
            ]
        )
        failed = [issue for issue in detect.scan_events(payload) if issue.kind == "failed_command"]
        self.assertEqual(len(failed), 1)
        self.assertFalse(failed[0].recovered)

    def test_assistant_step_exhaustion(self) -> None:
        payload = self.payload(
            [
                {
                    "info": {"role": "assistant"},
                    "parts": [
                        {"type": "text", "text": "Reached the maximum number of steps for this agent"}
                    ],
                }
            ]
        )
        self.assertIn("step_exhaustion", {issue.kind for issue in detect.scan_events(payload)})

    def test_user_text_is_not_scanned(self) -> None:
        payload = self.payload(
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
        self.assertEqual(detect.scan_events(payload), [])

    def test_since_filter_ignores_previous_attempt_events(self) -> None:
        payload = self.payload(
            [
                {
                    "info": {"role": "assistant", "time": {"created": 1000}},
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
                    "info": {"role": "assistant", "time": {"created": 5000}},
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
        self.assertIn("permission_rejection", {issue.kind for issue in detect.scan_events(payload)})
        self.assertEqual(detect.scan_events(payload, since_ms=2000), [])

    def test_scan_session_without_id_is_unavailable(self) -> None:
        self.assertIsNone(detect.scan_session(None))


class GuardCheckWarnTests(unittest.TestCase):
    """Check-mode guard WARN is informational, not a failed command.

    Job ``20261101T103720Z-fix-workflow-v3-failure-detectio-57bae68c`` called
    ``opencode_guard.py check`` twice while its own OpenCode process was running.
    The guard returned its documented exit ``10`` (``EXIT_WARN``) because the
    job's own session occupied the one-session slot and load was above the
    warning threshold. RAM and disk were available and the process was the job's
    own child, so this was not a failed command. A real refusal, guard error or
    ordinary non-zero command must still fail.
    """

    COMMAND = (
        "python3 /home/iffi/dev-workspace/control-plane/tools/opencode_guard.py check"
    )
    WARN_OUTPUT = (
        "opencode-guard: WARN\n"
        "  RAM: 7.41 GiB available of 11.69 GiB; swap 0.00 GiB\n"
        "  load: 6.74 5.37 4.25\n"
        "  disk: 140.02 GiB available\n"
        "  heavyweight OpenCode: 1 (maximum 1)\n"
        "    pid 677298 rss 424 MiB: opencode run --agent opencode-development "
        "--model deepseek/deepseek-flash --title 'Fix Workflow v3 false FAILED "
        "classification; failed_command detector' 'RAM and disk were available'\n"
        "  Qortium (read-only): pid 299485 rss 3325 MiB\n"
        "  WARN: 5-minute load average 5.37 exceeds the 5.00 warning threshold\n"
    )

    @staticmethod
    def payload(command: str, output: str, exit_code: int) -> dict:
        return {
            "info": {"id": "ses_test"},
            "messages": [
                {
                    "info": {"role": "assistant"},
                    "parts": [
                        {
                            "type": "tool",
                            "tool": "bash",
                            "state": {
                                "status": "completed",
                                "metadata": {"exit": exit_code},
                                "output": output,
                                "input": {"command": command},
                            },
                        }
                    ],
                }
            ],
        }

    def test_check_mode_warn_exit_is_informational(self) -> None:
        issues = detect.scan_events(
            self.payload(self.COMMAND, self.WARN_OUTPUT, 10)
        )
        self.assertEqual(issues, [])

    def test_compound_check_command_with_options_is_informational(self) -> None:
        command = (
            "cd /home/iffi/dev-workspace/control-plane && "
            "python3 tools/opencode_guard.py check --refuse-ram-gib 1.5"
        )
        issues = detect.scan_events(
            self.payload(command, self.WARN_OUTPUT, 10)
        )
        self.assertEqual(issues, [])

    def test_console_check_mode_warn_block_is_informational(self) -> None:
        log = f"✗ {self.COMMAND} failed\n{self.WARN_OUTPUT}"
        self.assertEqual(detect.scan_text(log), [])

    def test_check_mode_refuse_is_still_a_failure(self) -> None:
        output = (
            "opencode-guard: REFUSE\n"
            "  RAM: 0.82 GiB available of 11.69 GiB; swap 0.00 GiB\n"
            "  REFUSE: available RAM 0.82 GiB is below the 1.50 GiB refusal threshold\n"
        )
        issues = detect.scan_events(self.payload(self.COMMAND, output, 20))
        self.assertEqual(
            {issue.kind for issue in issues},
            {"failed_command"},
        )
        self.assertEqual(detect.highest_severity(issues), "failed")

    def test_check_mode_guard_error_is_still_a_failure(self) -> None:
        output = "opencode-guard: ERROR\ncannot read /proc/meminfo\n"
        issues = detect.scan_events(self.payload(self.COMMAND, output, 1))
        self.assertEqual(detect.highest_severity(issues), "failed")

    def test_console_check_mode_refuse_is_still_a_failure(self) -> None:
        log = (
            f"✗ {self.COMMAND} failed\n"
            "opencode-guard: REFUSE\n"
            "  REFUSE: 5-minute load average is above the refusal threshold\n"
        )
        self.assertEqual(detect.highest_severity(detect.scan_text(log)), "failed")

    def test_check_mode_warn_without_status_line_is_not_excused(self) -> None:
        issues = detect.scan_events(
            self.payload(
                self.COMMAND,
                "  RAM: 7.41 GiB available\n  disk: 140.02 GiB available\n",
                10,
            )
        )
        self.assertEqual(detect.highest_severity(issues), "failed")

    def test_guard_check_compound_with_real_command_is_not_excused(self) -> None:
        command = f"{self.COMMAND}; npm test"
        issues = detect.scan_events(
            self.payload(command, self.WARN_OUTPUT + "FAILED (failures=1)\n", 10)
        )
        self.assertEqual(detect.highest_severity(issues), "failed")

    def test_run_mode_exit_10_is_not_informational(self) -> None:
        command = "python3 tools/opencode_guard.py run -- opencode run --agent x"
        issues = detect.scan_events(
            self.payload(command, self.WARN_OUTPUT, 10)
        )
        self.assertEqual(detect.highest_severity(issues), "failed")

    def test_ordinary_nonzero_exit_10_is_not_informational(self) -> None:
        issues = detect.scan_events(
            self.payload("python3 tools/check_something.py", "opencode-guard: WARN\n", 10)
        )
        self.assertEqual(detect.highest_severity(issues), "failed")


class OwnerChangeAttributionTests(unittest.TestCase):
    """A whole-tree whitespace check must not turn owner dirt into a job failure.

    Job ``20261101T100446Z-fix-telegram-monitor-p3-p4-inter-126de083`` passed
    every acceptance criterion and verified its completion contract, but a
    whole-tree ``git diff --check`` reported a pre-existing owner edit in
    ``skills/qortium/qdn-resource-discovery/SKILL.md``. The attribution below
    removes only that owner-only whitespace result; real task whitespace and
    every other failed command still fail.
    """

    OWNER = "skills/qortium/qdn-resource-discovery/SKILL.md"
    TASK = "tools/devjob/detect.py"

    @staticmethod
    def payload(command: str, output: str, exit_code: int = 2) -> dict:
        return {
            "info": {"id": "ses_test"},
            "messages": [
                {
                    "info": {"role": "assistant"},
                    "parts": [
                        {
                            "type": "tool",
                            "tool": "bash",
                            "state": {
                                "status": "completed",
                                "metadata": {"exit": exit_code},
                                "output": output,
                                "input": {"command": command},
                            },
                        }
                    ],
                }
            ],
        }

    def test_owner_only_whitespace_check_is_a_warning(self) -> None:
        payload = self.payload(
            "git diff --check",
            f"{self.OWNER}:58: trailing whitespace.\n+Live read-only evidence \n",
        )
        issues = detect.scan_events(payload, owner_paths=[self.OWNER])
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].kind, "failed_command")
        self.assertEqual(issues[0].severity, "warning")
        self.assertIn("only pre-existing owner changes", issues[0].message)
        self.assertFalse(issues[0].recovered)
        self.assertIsNone(detect.highest_severity(issues))

    def test_owner_attribution_is_not_global_suppression(self) -> None:
        payload = self.payload(
            "git diff --check",
            f"{self.OWNER}:58: trailing whitespace.\n",
        )
        # Without the recorded owner path the same evidence remains a failure.
        unowned = detect.scan_events(payload)
        self.assertEqual(detect.highest_severity(unowned), "failed")

    def test_task_whitespace_check_remains_failed(self) -> None:
        payload = self.payload(
            "git diff --check",
            f"{self.TASK}:12: trailing whitespace.\n+bad \n",
        )
        issues = detect.scan_events(payload, owner_paths=[self.OWNER])
        self.assertEqual(detect.highest_severity(issues), "failed")
        self.assertFalse(issues[0].recovered)

    def test_mixed_owner_and_task_whitespace_remains_failed(self) -> None:
        payload = self.payload(
            "git diff --check",
            f"{self.OWNER}:58: trailing whitespace.\n"
            f"{self.TASK}:12: trailing whitespace.\n",
        )
        issues = detect.scan_events(payload, owner_paths=[self.OWNER])
        self.assertEqual(detect.highest_severity(issues), "failed")

    def test_owner_paths_do_not_suppress_other_failed_commands(self) -> None:
        payload = self.payload(
            "python3 -m unittest discover -s tools -q",
            f"{self.OWNER}:58: trailing whitespace.\nFAILED (failures=1)\n",
            exit_code=1,
        )
        issues = detect.scan_events(payload, owner_paths=[self.OWNER])
        self.assertEqual(detect.highest_severity(issues), "failed")

    def test_unparsed_git_diff_check_error_remains_failed(self) -> None:
        payload = self.payload(
            "git diff --check",
            f"fatal: not a git repository\n{self.OWNER}:58: trailing whitespace.\n",
        )
        issues = detect.scan_events(payload, owner_paths=[self.OWNER])
        self.assertEqual(detect.highest_severity(issues), "failed")

    def test_console_owner_only_whitespace_check_is_a_warning(self) -> None:
        log = (
            "✗ git diff --check failed\n"
            f"{self.OWNER}:58: trailing whitespace.\n"
            "+Live read-only evidence \n"
        )
        issues = detect.scan_text(log, owner_paths=[self.OWNER])
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].severity, "warning")
        self.assertIsNone(detect.highest_severity(issues))
        self.assertEqual(detect.highest_severity(detect.scan_text(log)), "failed")

    def test_console_task_whitespace_check_remains_failed(self) -> None:
        log = (
            "✗ git diff --check failed\n"
            f"{self.TASK}:12: trailing whitespace.\n"
            "+bad \n"
        )
        issues = detect.scan_text(log, owner_paths=[self.OWNER])
        self.assertEqual(detect.highest_severity(issues), "failed")

    def test_owner_directory_prefix_is_attributed(self) -> None:
        owner = "skills/shared/browser-thumbnail-generation/"
        payload = self.payload(
            "git diff --check",
            "skills/shared/browser-thumbnail-generation/SKILL.md:4: "
            "new blank line at EOF.\n",
            exit_code=2,
        )
        issues = detect.scan_events(payload, owner_paths=[owner])
        self.assertEqual(issues[0].severity, "warning")


class SessionExportTests(unittest.TestCase):
    def test_large_export_uses_temp_file_and_parses(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bin_dir = root / "bin"
            bin_dir.mkdir()
            payload = {
                "messages": [
                    {
                        "info": {"role": "assistant"},
                        "parts": [
                            {
                                "type": "tool",
                                "tool": "bash",
                                "state": {
                                    "status": "completed",
                                    "metadata": {"exit": 0},
                                    "output": "x" * 300_000,
                                },
                            }
                        ],
                    }
                ]
            }
            fake = bin_dir / "opencode"
            fake.write_text(
                "#!/usr/bin/env python3\nimport json\nprint(json.dumps(%r))\n" % payload,
                encoding="utf-8",
            )
            fake.chmod(0o755)
            env = os.environ.copy()
            env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
            with mock.patch.dict(os.environ, env, clear=False):
                issues = detect.scan_session("ses_test", cwd=root)
        self.assertEqual(issues, [])

    def test_unavailable_export_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bin_dir = root / "bin"
            bin_dir.mkdir()
            fake = bin_dir / "opencode"
            fake.write_text("#!/usr/bin/env python3\nimport sys\nsys.exit(3)\n", encoding="utf-8")
            fake.chmod(0o755)
            env = os.environ.copy()
            env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
            with mock.patch.dict(os.environ, env, clear=False):
                self.assertIsNone(detect.scan_session("ses_test", cwd=root))


class SeverityTests(unittest.TestCase):
    def test_blocked_wins_over_failed(self) -> None:
        issues = [
            detect.Issue("failed_command", "failed", "x", 0, "x"),
            detect.Issue("permission_rejection", "blocked", "x", 0, "x"),
        ]
        self.assertEqual(detect.highest_severity(issues), "blocked")


def main() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
