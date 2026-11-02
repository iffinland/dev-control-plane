#!/usr/bin/env python3
"""P2 interactive start/resume control tests using fake Telegram and fake dev."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

from devmonitor.admission import AdmissionManager  # noqa: E402
from devmonitor.config import with_overrides  # noqa: E402
from devmonitor.control import ControlManager  # noqa: E402
from devmonitor.documents import DocumentLibrary  # noqa: E402
from devmonitor.jobs import JobFacade  # noqa: E402
from devmonitor.lifecycle import LifecycleNotifier  # noqa: E402
from devmonitor.passphrase import hash_passphrase  # noqa: E402
from devmonitor.projects import Registry  # noqa: E402
from devmonitor.router import Router  # noqa: E402
from devmonitor.state import MonitorState  # noqa: E402
from devmonitor_test_support import (  # noqa: E402
    CHAT_ID,
    OTHER_USER,
    USER_ID,
    FakeApi,
    callback_update,
    init_project_repo,
    install_fake_dev,
    make_config,
    make_job,
    message_update,
    write_acceptance_profile,
    write_fake_jobs,
)

PROMPT = "Implement the requested P2 behavior exactly."
CRITERIA = "Build::python3 -m pytest -q\nmanual: Owner reviews the UI"
HISTORICAL_READ_ONLY_AUDIT = (
    "Perform a comprehensive read-only audit of NodeFM Station.\n"
    "Inspect the current source code, Git history, existing tests and documentation.\n"
    "Run safe, applicable tests and build checks.\n"
    "Preserve all existing owner changes. Do not modify application source, "
    "publish QDN resources, commit, push or perform wallet transactions."
)


def find_button(markup, text_fragment: str) -> str:
    for row in (markup or {}).get("inline_keyboard", []):
        for item in row:
            if text_fragment.lower() in item.get("text", "").lower():
                return item["callback_data"]
    raise AssertionError(f"button not found: {text_fragment}")


class ControlBase(unittest.TestCase):
    mode = "control"
    monitor_extra: dict | None = None

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="qdm-control-")
        self.root = Path(self.temporary.name)
        self.projects = self.root / "projects"
        self.projects.mkdir()
        self.project_repo = init_project_repo(self.projects / "Demo")
        self.other_repo = self.projects / "Other"
        self.other_repo.mkdir()
        self.docs = self.root / "docs"
        self.docs.mkdir()
        self.registry_file = self.root / "PROJECT-REGISTRY.md"
        self.registry_file.write_text(
            "# Project registry\n\n## Registered projects\n\n"
            "| ID | Platform | Verified local path | Project-level `AGENTS.md` | Canonical context | Central report root | Git remote | GitHub repository | Development branch pattern | Automatic push |\n"
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
            f"| `demo/project` | Qortal | `{self.project_repo}` | Yes | Pending | `{self.docs}/` | "
            "`origin` | `demo/project` | `agent/*` | `yes` |\n",
            encoding="utf-8",
        )
        write_acceptance_profile(
            self.registry_file,
            "demo/project",
            [
                {
                    "label": "Build",
                    "command": "python3 -m pytest -q",
                    "timeout_seconds": 600,
                }
            ],
        )
        self.state_root = self.root / "state"
        self.fake_dev = install_fake_dev(self.root)
        self.config = make_config(
            self.root,
            mode=self.mode,
            docs_roots=[self.docs],
            repo_roots=[self.projects],
            monitor_extra=self.monitor_extra,
        )
        self.config = with_overrides(self.config, registry_path=self.registry_file)
        self.state = MonitorState(self.root / "monitor" / "monitor.db")
        self.api = FakeApi()
        self.registry = Registry(self.registry_file, (self.projects,))
        self.documents = DocumentLibrary.from_sources(
            self.config.docs_roots, self.registry.load(force=True)
        )
        self.jobs = JobFacade(self.state_root, dev_script=self.fake_dev)
        self.admission = AdmissionManager(
            self.config.state_dir, self.jobs, self.registry
        )
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

    def tearDown(self) -> None:
        self.state.close()
        self.temporary.cleanup()

    def next_id(self) -> int:
        self.update_id += 1
        return self.update_id

    def invocations(self) -> list[dict]:
        path = self.state_root / "fake_invocations.jsonl"
        if not path.is_file():
            return []
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def begin_start(self) -> str:
        self.router.handle(message_update(self.next_id(), "/start_job"))
        markup = self.api.sent[-1]["markup"]
        callback = find_button(markup, "demo/project")
        self.router.handle(callback_update(self.next_id(), callback))
        return callback.split(":")[1]

    def send_text(self, value: str) -> None:
        self.router.handle(message_update(self.next_id(), value))

    def send_description(self, value: str = PROMPT) -> None:
        self.send_text(value)

    def choose_runtime(self, label: str = "2h", *, continue_to_preview: bool = True) -> None:
        callback = find_button(self.api.sent[-1]["markup"], label)
        self.router.handle(callback_update(self.next_id(), callback))
        if continue_to_preview:
            cont = find_button(self.api.edited[-1]["markup"], "Continue")
            self.router.handle(callback_update(self.next_id(), cont))

    def advance_to_preview(self) -> str:
        self.begin_start()
        self.send_description()
        self.choose_runtime("2h")
        return find_button(self.api.edited[-1]["markup"], "Confirm: Create job")

    def confirm(self, callback_data: str) -> None:
        self.router.handle(callback_update(self.next_id(), callback_data))


class ReadOnlyControlTests(ControlBase):
    mode = "read_only"

    def test_start_is_refused_and_cli_is_never_invoked(self) -> None:
        self.router.handle(message_update(1, "/start_job"))
        self.assertIn("read-only mode", self.api.sent[-1]["text"])
        self.assertEqual(self.invocations(), [])


class StartWizardTests(ControlBase):
    def test_full_start_wizard_invokes_fixed_argv_and_sends_started(self) -> None:
        confirm = self.advance_to_preview()
        self.confirm(confirm)
        records = self.invocations()
        self.assertEqual(len(records), 1)
        args = records[0]["args"]
        self.assertEqual(args[0], "start")
        self.assertIn("--repo", args)
        self.assertEqual(args[args.index("--repo") + 1], str(self.project_repo.resolve()))
        self.assertEqual(
            args[args.index("--title") + 1],
            "Implement the requested P2 behavior exactly.",
        )
        self.assertEqual(args[args.index("--prompt-file") + 1], "-")
        self.assertEqual(args[args.index("--project") + 1], "demo/project")
        self.assertEqual(args[args.index("--registry") + 1], str(self.registry_file))
        self.assertIn("--no-notify", args)
        self.assertIn("--json", args)
        self.assertEqual(
            [args[index + 1] for index, item in enumerate(args) if item == "--criterion"],
            ["Build::python3 -m pytest -q"],
        )
        self.assertEqual(
            [args[index + 1] for index, item in enumerate(args) if item == "--manual-criterion"],
            [],
        )
        self.assertEqual(args[args.index("--timeout") + 1], "7200s")
        self.assertEqual(args[args.index("--agent") + 1], "opencode-development")
        self.assertEqual(args[args.index("--model") + 1], "deepseek/deepseek-flash")
        self.assertTrue(records[0]["stdin"].startswith(PROMPT))
        self.assertIn("Auto-discovered project context", records[0]["stdin"])
        self.assertIn("AGENTS.md", records[0]["stdin"])
        self.assertTrue(any("STARTED" in item["text"] for item in self.api.sent))
        self.assertTrue(any("Job started" in item["text"] for item in self.api.edited))

    def test_obvious_project_mismatch_is_refused_before_start(self) -> None:
        second = init_project_repo(
            self.projects / "Second",
            remote="upstream",
            remote_url="https://github.com/demo/second.git",
        )
        self.registry_file.write_text(
            "# Project registry\n\n## Registered projects\n\n"
            "| ID | Platform | Verified local path | Project-level `AGENTS.md` | Canonical context | Central report root | Git remote | GitHub repository | Development branch pattern | Automatic push |\n"
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
            f"| `demo/project` | Qortal | `{self.project_repo}` | Yes | Pending | `{self.docs}/` | "
            "`origin` | `demo/project` | `agent/*` | `yes` |\n"
            f"| `demo/second` | Qortal | `{second}` | Yes | Pending | `{self.docs}/` | "
            "`upstream` | `demo/second` | `agent/*` | `yes` |\n",
            encoding="utf-8",
        )
        write_acceptance_profile(self.registry_file, "demo/second")
        self.registry = Registry(self.registry_file, (self.projects,))
        self.control.registry = self.registry
        self.router.registry = self.registry
        for description in (
            "Fix https://github.com/demo/second/pull/1",
            f"Fix the login flow in {second}",
        ):
            with self.subTest(description=description):
                self.begin_start()
                self.send_text(description)
                self.choose_runtime("2h")
                text = self.api.edited[-1]["text"]
                self.assertIn("demo/second", text)
                self.assertNotIn("Confirm job start", text)
                self.assertEqual(self.invocations(), [])

    def test_read_only_audit_toggle_is_passed_explicitly(self) -> None:
        self.begin_start()
        self.send_description("Audit the repository without changing it")
        toggle = find_button(self.api.sent[-1]["markup"], "Read-only audit")
        self.router.handle(callback_update(self.next_id(), toggle))
        self.assertIn("Read-only audit: on", self.api.edited[-1]["text"])
        runtime = find_button(self.api.edited[-1]["markup"], "1h")
        self.router.handle(callback_update(self.next_id(), runtime))
        cont = find_button(self.api.edited[-1]["markup"], "Continue")
        self.router.handle(callback_update(self.next_id(), cont))
        preview = self.api.edited[-1]["text"]
        self.assertIn("read-only audit", preview.lower())
        confirm = find_button(self.api.edited[-1]["markup"], "Confirm: Create job")
        self.confirm(confirm)
        args = self.invocations()[0]["args"]
        self.assertIn("--read-only", args)
        self.assertNotIn("--authorize-push", args)

    def test_explicit_read_only_audit_request_preselects_the_toggle(self) -> None:
        """The historical NodeFM prompt was started as a delivery job by mistake.

        An explicit read-only audit plus a no-modification directive now
        pre-selects read-only mode in the Telegram wizard, while remaining
        visible and owner-overridable.
        """

        self.begin_start()
        self.send_description(HISTORICAL_READ_ONLY_AUDIT)
        self.assertIn("Read-only audit: on", self.api.sent[-1]["text"])
        self.assertIn("Read-only audit: on", json.dumps(self.api.sent[-1]["markup"]))
        self.choose_runtime("2h")
        self.assertIn("read-only audit", self.api.edited[-1]["text"].lower())
        confirm = find_button(self.api.edited[-1]["markup"], "Confirm: Create job")
        self.confirm(confirm)
        args = self.invocations()[0]["args"]
        self.assertIn("--read-only", args)
        self.assertNotIn("--authorize-push", args)

    def test_owner_can_override_inferred_read_only_mode(self) -> None:
        self.begin_start()
        self.send_description(HISTORICAL_READ_ONLY_AUDIT)
        toggle = find_button(self.api.sent[-1]["markup"], "Read-only audit")
        self.router.handle(callback_update(self.next_id(), toggle))
        self.assertIn("Read-only audit: off", self.api.edited[-1]["text"])
        runtime = find_button(self.api.edited[-1]["markup"], "2h")
        self.router.handle(callback_update(self.next_id(), runtime))
        cont = find_button(self.api.edited[-1]["markup"], "Continue")
        self.router.handle(callback_update(self.next_id(), cont))
        confirm = find_button(self.api.edited[-1]["markup"], "Confirm: Create job")
        self.confirm(confirm)
        args = self.invocations()[0]["args"]
        self.assertNotIn("--read-only", args)

    def test_start_uses_cli_default_contract_without_weakening_overrides(self) -> None:
        confirm = self.advance_to_preview()
        self.confirm(confirm)
        args = self.invocations()[0]["args"]
        self.assertNotIn("--contract-file", args)
        self.assertNotIn("--authorize-push", args)
        self.assertNotIn("--authorize-merge", args)
        self.assertNotIn("--authorize-protected-branch", args)
        # The CLI resolves the same project-scoped policy independently.
        self.assertEqual(args[args.index("--project") + 1], "demo/project")
        self.assertEqual(args[args.index("--registry") + 1], str(self.registry_file))
        self.assertIn("--json", args)

    def test_second_project_uses_its_own_delivery_policy(self) -> None:
        second = init_project_repo(
            self.projects / "Second",
            remote="upstream",
            remote_url="https://github.com/demo/second.git",
        )
        self.registry_file.write_text(
            "# Project registry\n\n## Registered projects\n\n"
            "| ID | Platform | Verified local path | Project-level `AGENTS.md` | Canonical context | Central report root | Git remote | GitHub repository | Development branch pattern | Automatic push |\n"
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
            f"| `demo/project` | Qortal | `{self.project_repo}` | Yes | Pending | `{self.docs}/` | "
            "`origin` | `demo/project` | `agent/*` | `yes` |\n"
            f"| `demo/second` | Qortal | `{second}` | Yes | Pending | `{self.docs}/` | "
            "`upstream` | `demo/second` | `agent/*` | `yes` |\n",
            encoding="utf-8",
        )
        write_acceptance_profile(self.registry_file, "demo/second")
        self.registry = Registry(self.registry_file, (self.projects,))
        self.control.registry = self.registry
        self.router.registry = self.registry
        self.router.handle(message_update(1, "/start_job"))
        callback = find_button(self.api.sent[-1]["markup"], "demo/second")
        self.router.handle(callback_update(self.next_id(), callback))
        self.send_text(PROMPT)
        self.choose_runtime("2h")
        confirm = find_button(self.api.edited[-1]["markup"], "Confirm: Create job")
        self.confirm(confirm)
        args = self.invocations()[0]["args"]
        self.assertEqual(args[args.index("--project") + 1], "demo/second")
        self.assertEqual(args[args.index("--repo") + 1], str(second.resolve()))
        self.assertEqual(args[args.index("--registry") + 1], str(self.registry_file))

    def test_invalid_project_policy_is_not_start_eligible(self) -> None:
        self.registry_file.write_text(
            "# Project registry\n\n## Registered projects\n\n"
            "| ID | Platform | Verified local path | Project-level `AGENTS.md` | Canonical context | Central report root | Git remote | GitHub repository | Development branch pattern | Automatic push |\n"
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
            f"| `demo/project` | Qortal | `{self.project_repo}` | Yes | Pending | `{self.docs}/` | "
            "`origin` | `different/project` | `agent/*` | `yes` |\n",
            encoding="utf-8",
        )
        self.registry = Registry(self.registry_file, (self.projects,))
        self.control.registry = self.registry
        self.router.registry = self.registry
        self.router.handle(message_update(1, "/start_job"))
        self.assertIn("No registered project", self.api.sent[-1]["text"])
        self.assertEqual(self.invocations(), [])

    def test_duplicate_confirmation_callback_creates_one_job(self) -> None:
        confirm = self.advance_to_preview()
        self.confirm(confirm)
        self.confirm(confirm)
        self.assertEqual(len(self.invocations()), 1)
        self.assertIn("expired or already used", self.api.edited[-1]["text"])

    def test_missing_task_description_is_refused_before_cli(self) -> None:
        self.begin_start()
        self.send_text("   ")
        self.assertIn("Input rejected", self.api.sent[-1]["text"])
        self.assertEqual(self.invocations(), [])

    def test_advanced_flow_preserves_explicit_criteria_and_branch(self) -> None:
        self.begin_start()
        self.send_text(PROMPT)
        advanced = find_button(self.api.sent[-1]["markup"], "Advanced options")
        self.router.handle(callback_update(self.next_id(), advanced))
        self.send_text(CRITERIA)
        self.send_text("90m")
        self.send_text("agent/test/advanced")
        confirm = find_button(self.api.sent[-1]["markup"], "Confirm: Create job")
        self.confirm(confirm)
        args = self.invocations()[0]["args"]
        self.assertEqual(args[args.index("--timeout") + 1], "5400s")
        self.assertEqual(args[args.index("--branch") + 1], "agent/test/advanced")
        self.assertEqual(
            [args[index + 1] for index, item in enumerate(args) if item == "--criterion"],
            ["Build::python3 -m pytest -q"],
        )
        self.assertEqual(
            [args[index + 1] for index, item in enumerate(args) if item == "--manual-criterion"],
            ["Owner reviews the UI"],
        )

    def test_tampered_project_index_is_refused(self) -> None:
        self.router.handle(message_update(1, "/start_job"))
        wizard = find_button(self.api.sent[-1]["markup"], "demo/project").split(":")[1]
        self.router.handle(callback_update(2, f"w:{wizard}:p:9"))
        self.assertIn("Request failed", self.api.edited[-1]["text"])
        self.assertEqual(self.invocations(), [])

    def test_blocked_preflight_sends_no_started(self) -> None:
        (self.state_root).mkdir(parents=True, exist_ok=True)
        (self.state_root / "fake_start_state").write_text("BLOCKED", encoding="utf-8")
        confirm = self.advance_to_preview()
        self.confirm(confirm)
        self.assertFalse(any("STARTED" in item["text"] for item in self.api.sent))
        self.assertIn("did not enter RUNNING", self.api.edited[-1]["text"])
        self.assertIn("BLOCKED", self.api.edited[-1]["text"])

    def test_same_project_active_job_blocks_second_start(self) -> None:
        write_fake_jobs(
            self.state_root,
            [
                make_job(
                    "20261031T120000Z-existing-job-11111111",
                    repo=str(self.project_repo),
                    title="Existing",
                )
            ],
        )
        confirm = self.advance_to_preview()
        self.confirm(confirm)
        self.assertIn("already has an active job", self.api.edited[-1]["text"])
        self.assertEqual(self.invocations(), [])

    def test_global_guard_blocks_start_in_another_project(self) -> None:
        write_fake_jobs(
            self.state_root,
            [
                make_job(
                    "20261031T120000Z-other-job-22222222",
                    repo=str(self.other_repo),
                    title="Other project job",
                )
            ],
        )
        confirm = self.advance_to_preview()
        self.confirm(confirm)
        self.assertIn("global execution guard is busy", self.api.edited[-1]["text"])
        self.assertEqual(self.invocations(), [])


class StartConfigurationRegressionTests(ControlBase):
    """Runtime and read-only are independent settings on one configuration step."""

    def open_configuration(self, description: str = PROMPT) -> None:
        self.begin_start()
        self.send_description(description)

    def assert_on_configuration(
        self,
        markup,
        text: str,
        *,
        runtime: str | None,
        read_only: bool,
    ) -> None:
        self.assertIn("Choose maximum runtime", text)
        if runtime is not None:
            self.assertIn(f"Selected runtime: {runtime}", text)
        self.assertIn(f"Read-only audit: {'on' if read_only else 'off'}", text)
        self.assertNotIn("Confirm job start", text)
        find_button(markup, "Continue")
        find_button(markup, "Read-only audit")
        find_button(markup, "Back")
        find_button(markup, "Cancel")

    def test_every_runtime_option_stays_on_configuration_then_reaches_exact_confirmation(
        self,
    ) -> None:
        choices = (
            ("1h", "Maximum runtime: 1h00m00s"),
            ("2h", "Maximum runtime: 2h00m00s"),
            ("4h", "Maximum runtime: 4h00m00s"),
            ("8h", "Maximum runtime: 8h00m00s"),
        )
        self.open_configuration()
        config_markup = self.api.sent[-1]["markup"]
        read_only = False
        for index, (label, preview_runtime) in enumerate(choices):
            self.confirm(find_button(config_markup, label))
            self.assert_on_configuration(
                self.api.edited[-1]["markup"],
                self.api.edited[-1]["text"],
                runtime=label,
                read_only=read_only,
            )

            # The read-only toggle is independent of the runtime selection.
            self.confirm(find_button(self.api.edited[-1]["markup"], "Read-only audit"))
            read_only = not read_only
            self.assert_on_configuration(
                self.api.edited[-1]["markup"],
                self.api.edited[-1]["text"],
                runtime=label,
                read_only=read_only,
            )

            self.confirm(find_button(self.api.edited[-1]["markup"], "Continue"))
            preview = self.api.edited[-1]["text"]
            self.assertIn("Confirm job start", preview)
            self.assertIn("Project: demo/project", preview)
            self.assertIn(f"Title: {PROMPT}", preview)
            self.assertIn(preview_runtime, preview)
            self.assertIn(
                f"Read-only audit: {'on' if read_only else 'off'}", preview
            )
            old_confirm = find_button(
                self.api.edited[-1]["markup"], "Confirm: Create job"
            )

            # Back restores the same configuration and invalidates the preview.
            self.confirm(find_button(self.api.edited[-1]["markup"], "Back"))
            self.assert_on_configuration(
                self.api.edited[-1]["markup"],
                self.api.edited[-1]["text"],
                runtime=label,
                read_only=read_only,
            )
            config_markup = self.api.edited[-1]["markup"]
            self.confirm(old_confirm)
            self.assertIn("expired or already used", self.api.edited[-1]["text"])
            self.assertEqual(self.invocations(), [])

        # The last confirmed preview starts exactly the settings still visible.
        self.confirm(find_button(config_markup, "Continue"))
        final_preview = self.api.edited[-1]["text"]
        self.assertIn("Maximum runtime: 8h00m00s", final_preview)
        self.assertIn(
            f"Read-only audit: {'on' if read_only else 'off'}", final_preview
        )
        self.confirm(find_button(self.api.edited[-1]["markup"], "Confirm: Create job"))
        records = self.invocations()
        self.assertEqual(len(records), 1)
        args = records[0]["args"]
        self.assertEqual(args[args.index("--timeout") + 1], "28800s")
        if read_only:
            self.assertIn("--read-only", args)
        else:
            self.assertNotIn("--read-only", args)

    def test_runtime_then_repeated_read_only_toggles_preserve_both_and_start_exact_mode(
        self,
    ) -> None:
        self.open_configuration()
        self.confirm(find_button(self.api.sent[-1]["markup"], "2h"))
        read_only = False
        for _ in range(5):
            self.confirm(find_button(self.api.edited[-1]["markup"], "Read-only audit"))
            read_only = not read_only
            self.assert_on_configuration(
                self.api.edited[-1]["markup"],
                self.api.edited[-1]["text"],
                runtime="2h",
                read_only=read_only,
            )

        self.confirm(find_button(self.api.edited[-1]["markup"], "Continue"))
        preview = self.api.edited[-1]["text"]
        self.assertIn("Maximum runtime: 2h00m00s", preview)
        self.assertIn(f"Read-only audit: {'on' if read_only else 'off'}", preview)
        self.confirm(find_button(self.api.edited[-1]["markup"], "Confirm: Create job"))
        args = self.invocations()[0]["args"]
        self.assertEqual(args[args.index("--timeout") + 1], "7200s")
        self.assertIn("--read-only", args)

    def test_read_only_then_runtime_preserves_both_and_starts_exact_mode(self) -> None:
        self.open_configuration()
        self.confirm(find_button(self.api.sent[-1]["markup"], "Read-only audit"))
        self.assert_on_configuration(
            self.api.edited[-1]["markup"],
            self.api.edited[-1]["text"],
            runtime=None,
            read_only=True,
        )
        self.confirm(find_button(self.api.edited[-1]["markup"], "4h"))
        self.assert_on_configuration(
            self.api.edited[-1]["markup"],
            self.api.edited[-1]["text"],
            runtime="4h",
            read_only=True,
        )
        self.confirm(find_button(self.api.edited[-1]["markup"], "Continue"))
        preview = self.api.edited[-1]["text"]
        self.assertIn("Maximum runtime: 4h00m00s", preview)
        self.assertIn("Read-only audit: on", preview)
        self.confirm(find_button(self.api.edited[-1]["markup"], "Confirm: Create job"))
        args = self.invocations()[0]["args"]
        self.assertEqual(args[args.index("--timeout") + 1], "14400s")
        self.assertIn("--read-only", args)

    def test_back_from_configuration_returns_to_description_and_preserves_settings(
        self,
    ) -> None:
        self.open_configuration()
        self.confirm(find_button(self.api.sent[-1]["markup"], "2h"))
        self.confirm(find_button(self.api.edited[-1]["markup"], "Read-only audit"))
        self.confirm(find_button(self.api.edited[-1]["markup"], "Back"))
        self.assertIn("What should be changed or fixed?", self.api.edited[-1]["text"])

        self.send_description("Updated task description")
        self.assert_on_configuration(
            self.api.sent[-1]["markup"],
            self.api.sent[-1]["text"],
            runtime="2h",
            read_only=True,
        )
        self.confirm(find_button(self.api.sent[-1]["markup"], "Continue"))
        preview = self.api.edited[-1]["text"]
        self.assertIn("Title: Updated task description", preview)
        self.assertIn("Maximum runtime: 2h00m00s", preview)
        self.assertIn("Read-only audit: on", preview)

    def test_stale_runtime_and_read_only_callbacks_cannot_advance_or_mutate_preview(
        self,
    ) -> None:
        self.open_configuration()
        config_markup = self.api.sent[-1]["markup"]
        self.confirm(find_button(config_markup, "2h"))
        config_markup = self.api.edited[-1]["markup"]
        self.confirm(find_button(config_markup, "Continue"))
        self.assertIn("Confirm job start", self.api.edited[-1]["text"])
        confirm = find_button(self.api.edited[-1]["markup"], "Confirm: Create job")

        for stale in ("4h", "Read-only audit"):
            self.confirm(find_button(config_markup, stale))
            self.assertIn("Request failed", self.api.edited[-1]["text"])
            self.assertNotIn("Create job", json.dumps(self.api.edited[-1]["markup"]))
            self.assertEqual(self.invocations(), [])

        # The still-current preview keeps the original 2h/off settings.
        self.confirm(confirm)
        args = self.invocations()[0]["args"]
        self.assertEqual(args[args.index("--timeout") + 1], "7200s")
        self.assertNotIn("--read-only", args)

    def test_cancel_invalidates_the_preview_confirmation(self) -> None:
        self.open_configuration()
        self.confirm(find_button(self.api.sent[-1]["markup"], "1h"))
        self.confirm(find_button(self.api.edited[-1]["markup"], "Continue"))
        old_confirm = find_button(self.api.edited[-1]["markup"], "Confirm: Create job")
        self.send_text("/cancel")
        self.assertIn("Wizard cancelled", self.api.sent[-1]["text"])
        self.confirm(old_confirm)
        self.assertIn("expired or already used", self.api.edited[-1]["text"])
        self.assertEqual(self.invocations(), [])

    def test_duplicate_continue_and_confirm_submissions_create_one_job(self) -> None:
        self.open_configuration()
        self.confirm(find_button(self.api.sent[-1]["markup"], "2h"))
        cont = find_button(self.api.edited[-1]["markup"], "Continue")
        self.confirm(cont)
        confirm = find_button(self.api.edited[-1]["markup"], "Confirm: Create job")
        self.confirm(cont)
        self.assertIn("Request failed", self.api.edited[-1]["text"])
        rows = self.state.connection.execute(
            "SELECT COUNT(*) AS count FROM confirmations WHERE action = 'start_job'"
        ).fetchone()
        self.assertEqual(int(rows["count"]), 1)
        self.assertEqual(self.invocations(), [])
        self.confirm(confirm)
        self.confirm(confirm)
        self.assertEqual(len(self.invocations()), 1)
        self.assertIn("expired or already used", self.api.edited[-1]["text"])


class ResumeTests(ControlBase):
    def _terminal_job(self) -> dict:
        job = make_job(
            "20261031T120000Z-terminal-job-33333333",
            state="FAILED",
            title="Terminal job",
            repo=str(self.project_repo),
            notifications_enabled=True,
            notifications=[{"state": "FAILED", "sent": True, "reason": "sent"}],
        )
        write_fake_jobs(self.state_root, [job])
        return job

    def test_resume_wizard_invokes_resume_and_sends_resumed(self) -> None:
        job = self._terminal_job()
        self.router.handle(message_update(1, f"/resume {job['id']}"))
        self.assertIn("Resume job", self.api.sent[-1]["text"])
        confirm_preview = find_button(self.api.sent[-1]["markup"], "Confirm resume")
        self.confirm(confirm_preview)
        self.assertIn("Confirm resume", self.api.edited[-1]["text"])
        confirm = find_button(self.api.edited[-1]["markup"], "Confirm: Resume job")
        self.confirm(confirm)
        records = self.invocations()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["args"][0], "resume")
        self.assertEqual(records[0]["args"][1], job["id"])
        self.assertIn("--json", records[0]["args"])
        self.assertTrue(any("RESUMED" in item["text"] for item in self.api.sent))
        self.assertTrue(any("Job resumed" in item["text"] for item in self.api.edited))

    def test_running_live_job_resume_is_refused(self) -> None:
        job = make_job(
            "20261031T120000Z-running-job-44444444",
            repo=str(self.project_repo),
            title="Running job",
        )
        write_fake_jobs(self.state_root, [job])
        self.router.handle(message_update(1, f"/resume {job['id']}"))
        self.assertIn("RUNNING", self.api.sent[-1]["text"])
        self.assertEqual(self.invocations(), [])

    def test_success_without_force_is_refused(self) -> None:
        job = make_job(
            "20261031T120000Z-success-job-55555555",
            state="SUCCESS",
            repo=str(self.project_repo),
            notifications_enabled=True,
            notifications=[{"state": "SUCCESS", "sent": True, "reason": "sent"}],
        )
        write_fake_jobs(self.state_root, [job])
        self.router.handle(message_update(1, f"/resume {job['id']}"))
        confirm_preview = find_button(self.api.sent[-1]["markup"], "Confirm resume")
        self.confirm(confirm_preview)
        self.assertIn("already succeeded", self.api.edited[-1]["text"])
        self.assertEqual(self.invocations(), [])


class PassphraseTests(ControlBase):
    def setUp(self) -> None:
        self.passphrase = "correct horse battery staple"
        self.monitor_extra = {
            "control_passphrase_hash": hash_passphrase(self.passphrase, salt=b"0123456789abcdef")
        }
        super().setUp()

    def test_control_requires_unlock_and_lock_relocks(self) -> None:
        self.router.handle(message_update(1, "/start_job"))
        self.assertIn("locked", self.api.sent[-1]["text"])
        self.assertEqual(self.invocations(), [])

        self.router.handle(message_update(2, "/unlock wrong passphrase"))
        self.assertIn("Unlock failed", self.api.sent[-1]["text"])

        self.router.handle(message_update(3, f"/unlock {self.passphrase}"))
        self.assertIn("Control unlocked", self.api.sent[-1]["text"])

        self.router.handle(message_update(4, "/start_job"))
        self.assertIn("Start a development job", self.api.sent[-1]["text"])

        self.router.handle(message_update(5, "/lock"))
        self.router.handle(message_update(6, "/start_job"))
        self.assertIn("locked", self.api.sent[-1]["text"])

    def test_passphrase_never_appears_in_audit(self) -> None:
        self.router.handle(message_update(1, f"/unlock {self.passphrase}"))
        rows = self.state.connection.execute("SELECT detail_redacted FROM audit").fetchall()
        for row in rows:
            self.assertNotIn(self.passphrase, row["detail_redacted"])


class ConfirmationOwnershipTests(ControlBase):
    def test_confirmation_from_another_user_cannot_trigger_a_job(self) -> None:
        confirm = self.advance_to_preview()
        nonce = confirm.split(":")[1]
        self.router.handle(callback_update(self.next_id(), f"x:{nonce}:y", user_id=OTHER_USER))
        self.assertEqual(self.invocations(), [])
        self.assertIn("Access denied", self.api.answered[-1]["text"])


if __name__ == "__main__":
    unittest.main()
