#!/usr/bin/env python3
"""Tests for the OpenCode profile installer.

The tests use a temporary target directory and never touch the owner's real
~/.config/opencode/agents directory.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
CONTROL_PLANE = TOOLS.parent
INSTALLER = TOOLS / "install_opencode_profiles.sh"
SOURCE = CONTROL_PLANE / "adapters/opencode/agents"
PROFILES = ("opencode-unattended.md", "opencode-development.md")


def run(*args: str, timeout: float = 30.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(INSTALLER), *args],
        cwd=CONTROL_PLANE,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )


class InstallerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="opencode-install-test-")
        self.target = Path(self.temp.name) / "agents"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_check_does_not_install(self) -> None:
        result = run("--check", "--target", str(self.target))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("PASS", result.stdout)
        self.assertIn("nothing installed", result.stdout)
        self.assertFalse(self.target.exists())

    def test_dry_run_does_not_install(self) -> None:
        result = run("--dry-run", "--target", str(self.target))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("would install", result.stdout)
        self.assertFalse(self.target.exists())

    def test_install_and_idempotent_rerun(self) -> None:
        result = run("--target", str(self.target))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for name in PROFILES:
            installed = self.target / name
            self.assertTrue(installed.is_file(), name)
            self.assertEqual(installed.read_bytes(), (SOURCE / name).read_bytes(), name)

        second = run("--target", str(self.target))
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        self.assertIn("unchanged:", second.stdout)

    def test_changed_target_is_backed_up(self) -> None:
        first = run("--target", str(self.target))
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        changed = self.target / "opencode-development.md"
        changed.write_text("owner-local edit\n", encoding="utf-8")

        second = run("--target", str(self.target))
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        self.assertIn("backup:", second.stdout)
        self.assertEqual(changed.read_bytes(), (SOURCE / "opencode-development.md").read_bytes())
        backups = list(self.target.glob("opencode-development.md.bak.*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(encoding="utf-8"), "owner-local edit\n")

    def test_unknown_argument_is_usage_error(self) -> None:
        result = run("--not-a-real-option")
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)


def main() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
