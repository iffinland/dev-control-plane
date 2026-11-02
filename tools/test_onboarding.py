#!/usr/bin/env python3
"""Regressions for safe automatic GitHub project onboarding."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from devjob import acceptance_profiles, onboarding, project_policy  # noqa: E402


REGISTRY = (
    "# Project registry\n\n## Registered projects\n\n"
    "| ID | Platform | Verified local path | Project-level `AGENTS.md` | "
    "Canonical context | Central report root | Git remote | GitHub repository | "
    "Development branch pattern | Automatic push |\n"
    "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
)


class OnboardingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.projects = self.root / "projects"
        self.docs = self.root / "docs"
        self.projects.mkdir()
        self.registry = self.root / "PROJECT-REGISTRY.md"
        self.registry.write_text(REGISTRY, encoding="utf-8")
        self.state = self.root / "state"
        self.bare = self.root / "remote.git"
        self.source = self.root / "source"
        self.env = os.environ.copy()
        self.env.update(
            {
                "GIT_AUTHOR_NAME": "Test",
                "GIT_AUTHOR_EMAIL": "test@example.invalid",
                "GIT_COMMITTER_NAME": "Test",
                "GIT_COMMITTER_EMAIL": "test@example.invalid",
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_TERMINAL_PROMPT": "0",
            }
        )
        self.git(None, "init", "--bare", "-b", "main", str(self.bare))
        self.git(None, "init", "-b", "main", str(self.source))
        (self.source / "README.md").write_text(
            "Qortium application with Qortal support\n", encoding="utf-8"
        )
        (self.source / "package.json").write_text(
            json.dumps(
                {
                    "name": "demo",
                    "scripts": {
                        "test": "node -e \"require('fs').writeFileSync('EXECUTED','yes')\"",
                        "lint": "echo lint",
                        "build": "echo build",
                    },
                }
            ),
            encoding="utf-8",
        )
        (self.source / "AGENTS.md").write_text("Project rules\n", encoding="utf-8")
        self.git(self.source, "add", "-A")
        self.git(self.source, "commit", "-m", "baseline")
        self.git(self.source, "remote", "add", "origin", str(self.bare))
        self.git(self.source, "push", "origin", "main")
        self.config = self.root / "gitconfig"
        self.config.write_text(
            f'[url "{self.bare}"]\n\tinsteadOf = https://github.com/owner/demo.git\n'
            f'[url "{self.bare}"]\n\tinsteadOf = git@github.com:owner/demo.git\n',
            encoding="utf-8",
        )
        self.env["GIT_CONFIG_GLOBAL"] = str(self.config)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def git(self, repo: Path | None, *args: str) -> subprocess.CompletedProcess[str]:
        command = ["git"]
        if repo is not None:
            command.extend(["-C", str(repo)])
        command.extend(args)
        result = subprocess.run(
            command, capture_output=True, text=True, env=self.env, check=False
        )
        if result.returncode != 0:
            raise AssertionError(result.stderr)
        return result

    def _onboard(self, url: str = "https://github.com/owner/demo.git", **kwargs):
        from unittest import mock

        with mock.patch.dict(os.environ, self.env, clear=False):
            return onboarding.onboard(
                url=url,
                registry_path=self.registry,
                projects_root=self.projects,
                docs_root=self.docs,
                state_root=self.state,
                **kwargs,
            )

    def test_url_forms_and_rejections(self) -> None:
        self.assertEqual(
            onboarding.parse_github_identity("https://github.com/owner/demo.git").repository,
            "owner/demo",
        )
        self.assertEqual(
            onboarding.parse_github_identity("git@github.com:owner/demo.git").repository,
            "owner/demo",
        )
        self.assertEqual(
            onboarding.parse_github_identity("ssh://git@github.com:22/owner/demo.git").repository,
            "owner/demo",
        )
        for bad in (
            "https://gitlab.com/owner/demo.git",
            "file:///tmp/demo.git",
            "/tmp/demo",
            "https://user" + ":" + "token@" + "github.com/owner/demo.git",
            "https://github.com/owner",
            "https://github.com/owner/demo/extra",
        ):
            with self.subTest(bad=bad):
                with self.assertRaises(onboarding.OnboardError):
                    onboarding.parse_github_identity(bad)

    def test_onboarding_clones_inspects_and_registers_without_executing_scripts(self) -> None:
        project = self._onboard()
        self.assertTrue(project.cloned)
        self.assertEqual(project.github_repository, "owner/demo")
        self.assertEqual(project.project_id, "qortium/demo")
        self.assertEqual(project.platform, "Qortium")
        self.assertTrue(project.repo_path.is_dir())
        self.assertFalse((project.repo_path / "EXECUTED").exists())
        self.assertIn("Test suite", [item["label"] for item in project.commands])
        self.assertIn("Lint", [item["label"] for item in project.commands])
        self.assertIn("Production build", [item["label"] for item in project.commands])
        self.assertFalse((project.repo_path / "EXECUTED").exists())

        text = self.registry.read_text(encoding="utf-8")
        self.assertIn("`qortium/demo`", text)
        self.assertIn("`owner/demo`", text)
        self.assertIn("`agent/*`", text)
        parsed = project_policy.parse_registry(self.registry)
        match = next(item for item in parsed if item.project_id == "qortium/demo")
        self.assertTrue(match.delivery.automatic_push == "yes")

        profiles = json.loads((self.root / "acceptance-profiles.json").read_text(encoding="utf-8"))
        self.assertIn("qortium/demo", profiles["profiles"])
        entry = profiles["profiles"]["qortium/demo"]
        self.assertTrue(entry["commands"])
        self.assertTrue((self.docs / "demo").is_dir())
        # The cloned project stays clean: no profile file is written into it.
        status = self.git(project.repo_path, "status", "--porcelain").stdout.strip()
        self.assertEqual(status, "")

    def test_duplicate_onboarding_reuses_registration(self) -> None:
        first = self._onboard()
        second = self._onboard()
        self.assertTrue(second.reused_registration)
        self.assertEqual(second.project_id, first.project_id)
        text = self.registry.read_text(encoding="utf-8")
        self.assertEqual(text.count("`qortium/demo`"), 1)

    def test_existing_non_git_target_is_never_overwritten(self) -> None:
        target = self.projects / "demo"
        target.mkdir()
        (target / "owner.txt").write_text("keep me\n", encoding="utf-8")
        with self.assertRaises(onboarding.OnboardError) as context:
            self._onboard()
        self.assertIn("not a Git checkout", str(context.exception))
        self.assertEqual((target / "owner.txt").read_text(encoding="utf-8"), "keep me\n")

    def test_existing_checkout_for_another_repository_is_refused(self) -> None:
        target = self.projects / "demo"
        self.git(None, "clone", str(self.bare), str(target))
        self.git(target, "remote", "set-url", "origin", "https://github.com/owner/other.git")
        with self.assertRaises(onboarding.OnboardError) as context:
            self._onboard()
        self.assertIn("will not be overwritten", str(context.exception))

    def test_existing_matching_checkout_is_registered_without_clone(self) -> None:
        target = self.projects / "demo"
        self.git(None, "clone", str(self.bare), str(target))
        self.git(target, "remote", "set-url", "origin", "https://github.com/owner/demo.git")
        project = self._onboard()
        self.assertFalse(project.cloned)
        self.assertEqual(project.project_id, "qortium/demo")

    def test_dry_run_reports_plan_without_clone_or_registration(self) -> None:
        project = self._onboard(apply=False)
        self.assertFalse(project.cloned)
        self.assertFalse(self.projects.joinpath("demo").exists())
        text = self.registry.read_text(encoding="utf-8")
        self.assertNotIn("qortium/demo", text)

    def test_repository_without_test_command_gets_manual_criterion(self) -> None:
        bare = self.root / "plain.git"
        source = self.root / "plain-source"
        self.git(None, "init", "--bare", "-b", "main", str(bare))
        self.git(None, "init", "-b", "main", str(source))
        (source / "notes.txt").write_text("hello\n", encoding="utf-8")
        self.git(source, "add", "-A")
        self.git(source, "commit", "-m", "baseline")
        self.git(source, "remote", "add", "origin", str(bare))
        self.git(source, "push", "origin", "main")
        config = self.root / "gitconfig-plain"
        config.write_text(
            f'[url "{bare}"]\n\tinsteadOf = https://github.com/owner/plain.git\n',
            encoding="utf-8",
        )
        self.env["GIT_CONFIG_GLOBAL"] = str(config)
        project = self._onboard("https://github.com/owner/plain.git")
        self.assertEqual(project.commands, ())
        self.assertTrue(project.manual)
        self.assertEqual(project.platform, "Generic")
        profile = acceptance_profiles.resolve_profile(
            project_id=project.project_id,
            platform=project.platform,
            repo=project.repo_path,
            registry_path=self.registry,
        )
        self.assertEqual(profile.command_criteria, ())
        self.assertTrue(profile.manual)


if __name__ == "__main__":
    unittest.main()
