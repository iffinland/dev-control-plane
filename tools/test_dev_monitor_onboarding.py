#!/usr/bin/env python3
"""Telegram new-project onboarding end-to-end regressions."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from devmonitor import control as control_module  # noqa: E402
from devmonitor.admission import AdmissionManager  # noqa: E402
from devmonitor.config import with_overrides  # noqa: E402
from devmonitor.control import ControlManager  # noqa: E402
from devmonitor.documents import DocumentLibrary  # noqa: E402
from devmonitor.jobs import JobFacade  # noqa: E402
from devmonitor.lifecycle import LifecycleNotifier  # noqa: E402
from devmonitor.projects import Registry  # noqa: E402
from devmonitor.router import Router  # noqa: E402
from devmonitor.state import MonitorState  # noqa: E402
from devmonitor_test_support import (  # noqa: E402
    CHAT_ID,
    USER_ID,
    FakeApi,
    callback_update,
    install_fake_dev,
    make_config,
    message_update,
)


def find_button(markup, text_fragment: str) -> str:
    for row in (markup or {}).get("inline_keyboard", []):
        for item in row:
            if text_fragment.lower() in item.get("text", "").lower():
                return item["callback_data"]
    raise AssertionError(f"button not found: {text_fragment}")


class OnboardingRouterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="qdm-onboard-")
        self.root = Path(self.temporary.name)
        self.projects = self.root / "projects"
        self.projects.mkdir()
        self.docs = self.root / "docs"
        self.docs.mkdir()
        self.registry_file = self.root / "PROJECT-REGISTRY.md"
        self.registry_file.write_text(
            "# Project registry\n\n## Registered projects\n\n"
            "| ID | Platform | Verified local path | Project-level `AGENTS.md` | "
            "Canonical context | Central report root | Git remote | GitHub repository | "
            "Development branch pattern | Automatic push |\n"
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n",
            encoding="utf-8",
        )
        self.state_root = self.root / "state"
        self.fake_dev = install_fake_dev(self.root)
        self.config = make_config(
            self.root,
            mode="control",
            docs_roots=[self.docs],
            repo_roots=[self.projects],
        )
        self.config = with_overrides(self.config, registry_path=self.registry_file)
        self.state = MonitorState(self.root / "monitor" / "monitor.db")
        self.api = FakeApi()
        self.registry = Registry(self.registry_file, (self.projects,))
        self.documents = DocumentLibrary.from_sources(self.config.docs_roots, [])
        self.jobs = JobFacade(self.state_root, dev_script=self.fake_dev)
        self.admission = AdmissionManager(self.config.state_dir, self.jobs, self.registry)
        self.notifier = LifecycleNotifier(
            self.config, self.state, self.jobs, self.api, self.registry
        )
        self.control = ControlManager(
            self.config,
            self.state,
            self.jobs,
            self.registry,
            self.admission,
            notifier=self.notifier,
        )
        self.router = Router(
            self.config,
            self.state,
            self.api,
            self.jobs,
            self.registry,
            self.documents,
            control=self.control,
            admission=self.admission,
            notifier=self.notifier,
        )
        self.update_id = 1
        self._prepare_remote()

    def tearDown(self) -> None:
        self.state.close()
        self.temporary.cleanup()

    def _prepare_remote(self) -> None:
        self.bare = self.root / "remote.git"
        self.source = self.root / "source"
        env = os.environ.copy()
        env.update(
            {
                "GIT_AUTHOR_NAME": "Test",
                "GIT_AUTHOR_EMAIL": "test@example.invalid",
                "GIT_COMMITTER_NAME": "Test",
                "GIT_COMMITTER_EMAIL": "test@example.invalid",
                "GIT_CONFIG_NOSYSTEM": "1",
            }
        )
        self.git_env = env
        self.git(None, "init", "--bare", "-b", "main", str(self.bare))
        self.git(None, "init", "-b", "main", str(self.source))
        (self.source / "package.json").write_text(
            json.dumps({"scripts": {"test": "echo ok", "lint": "echo lint"}}),
            encoding="utf-8",
        )
        (self.source / "README.md").write_text("Qortium app\n", encoding="utf-8")
        self.git(self.source, "add", "-A")
        self.git(self.source, "commit", "-m", "baseline")
        self.git(self.source, "remote", "add", "origin", str(self.bare))
        self.git(self.source, "push", "origin", "main")
        self.gitconfig = self.root / "gitconfig"
        self.gitconfig.write_text(
            f'[url "{self.bare}"]\n\tinsteadOf = https://github.com/owner/demo.git\n',
            encoding="utf-8",
        )

    def git(self, repo: Path | None, *args: str) -> subprocess.CompletedProcess[str]:
        command = ["git"]
        if repo is not None:
            command.extend(["-C", str(repo)])
        command.extend(args)
        result = subprocess.run(
            command, capture_output=True, text=True, env=self.git_env, check=False
        )
        if result.returncode != 0:
            raise AssertionError(result.stderr)
        return result

    def next_id(self) -> int:
        self.update_id += 1
        return self.update_id

    def _env(self) -> dict:
        env = os.environ.copy()
        env["GIT_CONFIG_GLOBAL"] = str(self.gitconfig)
        env["GIT_TERMINAL_PROMPT"] = "0"
        return env

    def test_new_project_button_is_control_only(self) -> None:
        self.router.handle(message_update(self.next_id(), "/menu"))
        markup = self.api.sent[-1]["markup"]
        self.assertEqual(find_button(markup, "new project"), "p:new")
        read_only = make_config(self.root, mode="read_only", repo_roots=[self.projects])
        read_only = with_overrides(read_only, registry_path=self.registry_file)
        other = Router(
            read_only,
            self.state,
            self.api,
            self.jobs,
            self.registry,
            self.documents,
        )
        other.handle(message_update(self.next_id(), "/menu"))
        self.assertNotIn("New project", json.dumps(self.api.sent[-1]["markup"]))

    def test_onboard_start_url_description_runtime_confirm_and_start(self) -> None:
        with mock.patch.dict(os.environ, self._env(), clear=False), mock.patch.object(
            control_module.onboarding, "DOCS_ROOT", self.docs
        ):
            self.router.handle(message_update(self.next_id(), "/newproject"))
            self.assertIn("GitHub repository URL", self.api.sent[-1]["text"])
            wizard_data = find_button(self.api.sent[-1]["markup"], "cancel")

            self.router.handle(
                message_update(self.next_id(), "https://github.com/owner/demo.git")
            )
            self.assertIn("owner/demo", self.api.sent[-1]["text"])
            self.router.handle(message_update(self.next_id(), "Fix the login flow"))
            self.assertIn("Choose maximum runtime", self.api.sent[-1]["text"])
            runtime = find_button(self.api.sent[-1]["markup"], "2h")
            self.assertTrue(runtime.startswith("w:"))
            self.assertTrue(wizard_data.startswith("w:"))

            self.router.handle(callback_update(self.next_id(), runtime))
            self.assertIn("Confirm new project", self.api.edited[-1]["text"])
            confirm = find_button(self.api.edited[-1]["markup"], "Confirm")
            self.assertTrue(confirm.startswith("x:"))

            self.router.handle(callback_update(self.next_id(), confirm))
            final = self.api.edited[-1]["text"]
            self.assertIn("Project onboarding", final)
            self.assertIn("qortium/demo", final)
            self.assertIn("First job", final)

        registry = self.registry_file.read_text(encoding="utf-8")
        self.assertIn("`qortium/demo`", registry)
        self.assertIn("`owner/demo`", registry)
        profiles = json.loads(
            (self.root / "acceptance-profiles.json").read_text(encoding="utf-8")
        )
        self.assertIn("qortium/demo", profiles["profiles"])
        self.assertTrue(profiles["profiles"]["qortium/demo"]["commands"])
        cloned = self.projects / "demo"
        self.assertTrue(cloned.is_dir())
        self.assertFalse((cloned / "EXECUTED").exists())

        invocations = [
            json.loads(line)
            for line in (self.state_root / "fake_invocations.jsonl").read_text(
                encoding="utf-8"
            ).splitlines()
            if line.strip()
        ]
        starts = [item for item in invocations if item["args"][:1] == ["start"]]
        self.assertEqual(len(starts), 1)
        args = starts[0]["args"]
        self.assertIn("--project", args)
        self.assertEqual(args[args.index("--project") + 1], "qortium/demo")
        self.assertIn("--criterion", args)
        self.assertIn("Fix the login flow", starts[0]["stdin"])

    def test_replayed_confirmation_does_not_start_twice(self) -> None:
        events: list[str] = []
        payload = {
            "wizard_id": "",
            "url": "https://github.com/owner/demo.git",
            "description": "Do the work",
            "title": "Do the work",
            "timeout_seconds": 3600,
        }
        original_onboard = control_module.onboarding.onboard

        def fake_onboard(**kwargs):
            result = original_onboard(**kwargs)
            events.append("onboard")
            return result

        with mock.patch.dict(os.environ, self._env(), clear=False), mock.patch.object(
            control_module.onboarding, "DOCS_ROOT", self.docs
        ), mock.patch.object(control_module.onboarding, "onboard", side_effect=fake_onboard):
            nonce = self.state.create_confirmation(USER_ID, CHAT_ID, "onboard_project", payload)
            update = callback_update(self.next_id(), f"x:{nonce}:y")
            self.router.handle(update)
            self.router.handle(update)
        self.assertEqual(events, ["onboard"])
        invocations = (self.state_root / "fake_invocations.jsonl").read_text(
            encoding="utf-8"
        )
        starts = [
            line
            for line in invocations.splitlines()
            if line and json.loads(line)["args"][:1] == ["start"]
        ]
        self.assertEqual(len(starts), 1)
        self.assertTrue(any("already used" in item["text"] for item in self.api.edited))

    def test_onboarding_refuses_existing_non_git_directory_without_start(self) -> None:
        target = self.projects / "demo"
        target.mkdir()
        (target / "owner.txt").write_text("keep\n", encoding="utf-8")
        with mock.patch.dict(os.environ, self._env(), clear=False), mock.patch.object(
            control_module.onboarding, "DOCS_ROOT", self.docs
        ):
            self.router.handle(message_update(self.next_id(), "/newproject"))
            self.router.handle(
                message_update(self.next_id(), "https://github.com/owner/demo.git")
            )
            self.router.handle(message_update(self.next_id(), "Do the work"))
            runtime = find_button(self.api.sent[-1]["markup"], "1h")
            self.router.handle(callback_update(self.next_id(), runtime))
            confirm = find_button(self.api.edited[-1]["markup"], "Confirm")
            self.router.handle(callback_update(self.next_id(), confirm))
        self.assertTrue(
            any("not a Git checkout" in item["text"] for item in self.api.edited)
            or any("not a Git checkout" in item["text"] for item in self.api.sent)
        )
        self.assertEqual((target / "owner.txt").read_text(encoding="utf-8"), "keep\n")
        self.assertNotIn("qortium/demo", self.registry_file.read_text(encoding="utf-8"))
        invocations = self.state_root / "fake_invocations.jsonl"
        self.assertFalse(
            invocations.is_file()
            and any(
                json.loads(line)["args"][:1] == ["start"]
                for line in invocations.read_text(encoding="utf-8").splitlines()
                if line
            )
        )


if __name__ == "__main__":
    unittest.main()
