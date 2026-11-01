#!/usr/bin/env python3
"""Tests for OpenCode agent permission parsing and policy checks.

These tests do not start OpenCode, signal Qortium or touch the live node. They
exercise the same last-match wildcard model documented for OpenCode 1.19.5.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
CONTROL_PLANE = TOOLS.parent
DEV_AGENT = CONTROL_PLANE / "adapters/opencode/agents/opencode-development.md"
UNATTENDED_AGENT = CONTROL_PLANE / "adapters/opencode/agents/opencode-unattended.md"
VALIDATOR = TOOLS / "validate_agent_permissions.py"
sys.path.insert(0, str(TOOLS))

import validate_agent_permissions as permissions  # noqa: E402


class WildcardTests(unittest.TestCase):
    def test_star_and_question(self) -> None:
        self.assertTrue(permissions.wildcard_match("git push origin feature", "git push *"))
        self.assertTrue(permissions.wildcard_match("git push", "git push *"))
        self.assertFalse(permissions.wildcard_match("git pull", "git push *"))
        self.assertTrue(permissions.wildcard_match("a/b/c", "*"))
        self.assertTrue(permissions.wildcard_match("a1", "a?"))
        self.assertFalse(permissions.wildcard_match("a12", "a?"))

    def test_pattern_is_anchored(self) -> None:
        self.assertFalse(permissions.wildcard_match("echo git push", "git push *"))
        self.assertTrue(permissions.wildcard_match("sudo", "sudo *"))
        self.assertFalse(permissions.wildcard_match("not sudo", "sudo *"))

    def test_backslashes_are_normalized(self) -> None:
        self.assertTrue(permissions.wildcard_match("C:\\work\\file", "C:/work/*"))


class ParserTests(unittest.TestCase):
    def test_development_profile_parses(self) -> None:
        rules, permission = permissions.load_rules(DEV_AGENT)
        self.assertGreater(len(rules), 100)
        self.assertIn("bash", permission)
        self.assertGreater(len(permission["bash"]), 100)

    def test_last_matching_rule_wins(self) -> None:
        text = """---
mode: primary
permission:
  bash:
    "*": allow
    "danger *": deny
    "danger safe*": allow
---
"""
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "agent.md"
            path.write_text(text, encoding="utf-8")
            rules, _ = permissions.load_rules(path)
        self.assertEqual(permissions.evaluate("bash", "danger thing", rules), "deny")
        self.assertEqual(permissions.evaluate("bash", "danger safe thing", rules), "allow")
        self.assertEqual(permissions.evaluate("bash", "other", rules), "allow")

    def test_default_is_ask(self) -> None:
        self.assertEqual(permissions.evaluate("bash", "anything", []), "ask")


class DevelopmentPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rules, cls.permission = permissions.load_rules(DEV_AGENT)

    def test_policy_checks_pass(self) -> None:
        self.assertEqual(permissions.check(self.rules), [])

    def test_normal_development_is_allowed(self) -> None:
        for command in (
            "git commit -m 'work'",
            "git push origin feature/x",
            "gh pr create --fill",
            "ssh example-host uptime",
            "npm ci",
            "npm run build",
            "npm test",
            "qortal qdn publish --help",
            "curl -s http://127.0.0.1:24991/api/status",
        ):
            self.assertEqual(permissions.decide("bash", command, self.rules), "allow", command)

    def test_read_only_diagnostics_are_allowed(self) -> None:
        for command in (
            "systemctl status qortium",
            "systemctl --user status qortium",
            "journalctl -u qortium -n 100",
            "service qortium status",
            "ps -o pid,rss,args -p 299485",
            "tail -n 20 /home/iffi/qortium-preview/preview/run.log",
            "cat /home/iffi/qortium-preview/preview/settings-preview-local.json",
        ):
            self.assertEqual(permissions.decide("bash", command, self.rules), "allow", command)
        self.assertEqual(
            permissions.evaluate("read", "/home/iffi/qortium-preview/preview/run.log", self.rules),
            "allow",
        )
        self.assertEqual(
            permissions.evaluate("external_directory", "/home/iffi/qortium-preview/**", self.rules),
            "allow",
        )

    def test_workflow_tooling_and_qortium_diagnostics_are_allowed(self) -> None:
        for command in (
            "cat ~/.local/state/dev-control-plane/jobs/example/job.json",
            "cd ~/.local/state/dev-control-plane/monitor && python3 -c 'print(1)'",
            "cp -a ~/.local/state/dev-control-plane /tmp/opencode/state-copy",
            "grep -rn 'qortium-data' docs/operations",
            "python3 -c \"print('/home/iffi/qortium-data')\"",
            "tail -n 20 /home/iffi/qortium-preview/preview/run.log",
            "cat /home/iffi/qortium-preview/preview/settings-preview-local.json",
        ):
            self.assertEqual(permissions.decide("bash", command, self.rules), "allow", command)
        for path in (
            "/home/iffi/.local/state/dev-control-plane",
            "/home/iffi/.local/state/dev-control-plane/jobs/example/job.json",
            "/home/iffi/.opencode",
            "/home/iffi/.opencode/bin/opencode",
            "/tmp/opencode",
            "/home/iffi/dev-workspace",
            "/home/iffi/qortium-preview",
            "/home/iffi/qortium-data",
        ):
            self.assertEqual(
                permissions.evaluate("external_directory", path, self.rules), "allow", path
            )
        self.assertEqual(
            permissions.evaluate(
                "read", "/home/iffi/.local/state/dev-control-plane/jobs/example/job.json", self.rules
            ),
            "allow",
        )

    def test_hard_boundaries_are_denied(self) -> None:
        for command in (
            "sudo apt update",
            "/usr/bin/sudo apt update",
            "systemctl restart qortium",
            "systemctl --user stop qortium",
            "service qortium stop",
            "kill 299485",
            "pkill java",
            "killall java",
            "tmux kill-server",
            "git push --force origin feature",
            "git merge main",
            "gh pr merge 1",
            "apt install curl",
            "npm install -g example",
            "npm publish",
            "java -jar /home/iffi/qortium-preview/qortium.jar",
            "rm -rf /home/iffi/qortium-preview/preview",
            "mv /home/iffi/qortium-preview/preview/run.log /tmp/run.log",
            "chmod 777 /home/iffi/qortium-data/blockchain.data",
            "cat /home/iffi/qortium-data/wallet.json",
            "echo changed > /home/iffi/qortium-preview/preview/settings-preview-local.json",
            "journalctl --vacuum-size=1G",
            "hostnamectl set-hostname example",
            "ip link set eth0 up",
            "mount /dev/sda1 /mnt",
        ):
            self.assertEqual(permissions.decide("bash", command, self.rules), "deny", command)

    def test_file_boundaries(self) -> None:
        self.assertEqual(
            permissions.evaluate("edit", "/home/iffi/qortium-preview/preview/settings.json", self.rules),
            "deny",
        )
        self.assertEqual(
            permissions.evaluate("edit", "/home/iffi/qortium-data/blockchain.data", self.rules),
            "deny",
        )
        self.assertEqual(
            permissions.evaluate("edit", "/home/iffi/dev-workspace/projects/app/src/main.ts", self.rules),
            "allow",
        )
        self.assertEqual(
            permissions.evaluate("read", "/home/iffi/dev-workspace/projects/app/.env", self.rules),
            "deny",
        )
        self.assertEqual(
            permissions.evaluate("read", "/home/iffi/.ssh/id_ed25519", self.rules),
            "deny",
        )
        self.assertEqual(
            permissions.evaluate("read", "/home/iffi/qortium-data/wallet.json", self.rules),
            "deny",
        )
        self.assertEqual(
            permissions.evaluate(
                "edit", "/home/iffi/.local/state/dev-control-plane/jobs/example/job.json", self.rules
            ),
            "deny",
        )
        self.assertEqual(
            permissions.evaluate(
                "edit",
                "/home/iffi/.local/state/dev-control-plane/jobs/example/evidence/TASK.md",
                self.rules,
            ),
            "allow",
        )
        self.assertEqual(
            permissions.evaluate("edit", "/home/iffi/.opencode/bin/opencode", self.rules),
            "deny",
        )
        self.assertEqual(
            permissions.evaluate("external_directory", "/etc/passwd", self.rules),
            "deny",
        )
        self.assertEqual(
            permissions.evaluate("external_directory", "/home/iffi/.ssh/id_ed25519", self.rules),
            "deny",
        )
        self.assertEqual(
            permissions.evaluate(
                "external_directory", "/home/iffi/.gnupg/private-keys-v1.d", self.rules
            ),
            "deny",
        )
        self.assertEqual(
            permissions.evaluate(
                "external_directory", "/home/iffi/.local/share/opencode/auth.json", self.rules
            ),
            "deny",
        )

    def test_chained_commands_are_evaluated_individually(self) -> None:
        self.assertEqual(
            permissions.decide("bash", "systemctl status qortium; systemctl restart qortium", self.rules),
            "deny",
        )
        self.assertEqual(
            permissions.decide("bash", "git status && git push origin feature", self.rules),
            "allow",
        )

    def test_documented_wrapper_limitation(self) -> None:
        # These are intentionally allowed by string patterns. The tests record
        # the limitation so nobody mistakes the profile for an OS sandbox.
        for command in (
            "bash -c 'sudo apt update'",
            "sh -c 'systemctl restart qortium'",
            "env sudo systemctl stop qortium",
            "python3 -c \"import os; os.kill(299485, 9)\"",
            "ssh host 'sudo systemctl restart qortium'",
        ):
            self.assertEqual(permissions.decide("bash", command, self.rules), "allow", command)


class CliTests(unittest.TestCase):
    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(VALIDATOR), *args],
            cwd=CONTROL_PLANE,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_check(self) -> None:
        result = self.run_cli("--check")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS", result.stdout)

    def test_json_command(self) -> None:
        result = self.run_cli("--command", "git push origin feature", "--json")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        entry = next(iter(payload.values()))
        self.assertEqual(entry["action"], "allow")

    def test_matrix_has_no_bad_rows(self) -> None:
        result = self.run_cli("--matrix")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("BAD", result.stdout)

    def test_limitations_output_is_explicit(self) -> None:
        result = self.run_cli("--limitations")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("bash -c 'sudo apt update'", result.stdout)

    def test_check_rejects_unsafe_profile(self) -> None:
        text = """---
mode: primary
permission:
  "*": deny
  bash:
    "*": allow
  read: allow
  edit: allow
  external_directory:
    "*": allow
---
"""
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "unsafe.md"
            path.write_text(text, encoding="utf-8")
            result = self.run_cli("--profile", str(path), "--check")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("FAIL", result.stdout)

    def test_parse_error_is_usage_error(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "broken.md"
            path.write_text("not front matter\n", encoding="utf-8")
            result = self.run_cli("--profile", str(path), "--check")
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)

    def test_unattended_profile_still_denies_push_and_qortal(self) -> None:
        rules, _ = permissions.load_rules(UNATTENDED_AGENT)
        self.assertEqual(permissions.decide("bash", "git push origin feature", rules), "deny")
        self.assertEqual(permissions.decide("bash", "qortal qdn publish --help", rules), "deny")
        self.assertEqual(permissions.decide("bash", "qortium status", rules), "deny")


def main() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
