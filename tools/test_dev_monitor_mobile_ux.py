#!/usr/bin/env python3
"""Mobile-first start flow, job listing, log download, continuation and summary tests."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

from devjob import acceptance_profiles  # noqa: E402
from devmonitor import summary  # noqa: E402
from devmonitor.admission import AdmissionManager  # noqa: E402
from devmonitor.config import with_overrides  # noqa: E402
from devmonitor.control import ControlManager, ControlError, derive_title  # noqa: E402
from devmonitor.documents import DocumentLibrary  # noqa: E402
from devmonitor.jobs import JobFacade  # noqa: E402
from devmonitor.lifecycle import LifecycleNotifier  # noqa: E402
from devmonitor.projects import Registry  # noqa: E402
from devmonitor.router import Router  # noqa: E402
from devmonitor.state import MonitorState  # noqa: E402
from devmonitor_test_support import (  # noqa: E402
    CHAT_ID,
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

DESCRIPTION = "Fix the overnight settings save bug without changing unrelated screens."
JOB_ID = "20261102T060000Z-mobile-job-abcdef12"


def find_button(markup, text_fragment: str) -> str:
    for row in (markup or {}).get("inline_keyboard", []):
        for item in row:
            if text_fragment.lower() in item.get("text", "").lower():
                return item["callback_data"]
    raise AssertionError(f"button not found: {text_fragment}")


class MobileBase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="qdm-mobile-")
        self.root = Path(self.temporary.name)
        self.projects = self.root / "projects"
        self.projects.mkdir()
        self.project_repo = init_project_repo(self.projects / "Demo")
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
        self.profile_path = write_acceptance_profile(
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
            mode="control",
            docs_roots=[self.docs],
            repo_roots=[self.projects],
        )
        self.config = with_overrides(self.config, registry_path=self.registry_file)
        self.state = MonitorState(self.root / "monitor" / "monitor.db")
        self.api = FakeApi()
        self.registry = Registry(self.registry_file, (self.projects,))
        self.documents = DocumentLibrary.from_sources(
            self.config.docs_roots, self.registry.load(force=True)
        )
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

    def tearDown(self) -> None:
        self.state.close()
        self.temporary.cleanup()

    def next_id(self) -> int:
        self.update_id += 1
        return self.update_id

    def send(self, text: str) -> None:
        self.router.handle(message_update(self.next_id(), text))

    def click(self, callback_data: str) -> None:
        self.router.handle(callback_update(self.next_id(), callback_data))

    def invocations(self) -> list[dict]:
        path = self.state_root / "fake_invocations.jsonl"
        if not path.is_file():
            return []
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def select_project(self) -> None:
        self.router.handle(message_update(self.next_id(), "/start_job"))
        self.router.handle(
            callback_update(
                self.next_id(), find_button(self.api.sent[-1]["markup"], "demo/project")
            )
        )

    def add_job(self, **overrides) -> dict:
        job = make_job(
            JOB_ID,
            title=(
                "Fix overnight settings save regression without touching unrelated screens"
            ),
            repo=str(self.project_repo),
            attempts=2,
            **overrides,
        )
        write_fake_jobs(self.state_root, [job])
        return job


class MobileStartFlowTests(MobileBase):
    def test_start_flow_asks_only_project_description_and_runtime(self) -> None:
        self.select_project()
        self.assertIn("What should be changed or fixed?", self.api.edited[-1]["text"])
        self.assertNotIn("acceptance criteria", self.api.edited[-1]["text"].lower())
        self.send(DESCRIPTION)
        runtime_text = self.api.sent[-1]["text"]
        self.assertIn("Choose maximum runtime", runtime_text)
        for label in ("1h", "2h", "4h", "8h"):
            self.assertTrue(find_button(self.api.sent[-1]["markup"], label))
        self.click(find_button(self.api.sent[-1]["markup"], "2h"))
        preview = self.api.edited[-1]["text"]
        self.assertIn("Acceptance profile: test verified profile", preview)
        self.assertIn("Auto-loaded context files:", preview)
        self.assertIn("Build", preview)
        confirm = find_button(self.api.edited[-1]["markup"], "Confirm: Create job")
        self.click(confirm)
        record = self.invocations()[0]
        self.assertEqual(record["args"][record["args"].index("--timeout") + 1], "7200s")
        self.assertNotIn("--branch", record["args"])
        self.assertEqual(
            record["args"][record["args"].index("--title") + 1],
            derive_title(DESCRIPTION),
        )
        self.assertIn("Auto-discovered project context", record["stdin"])
        self.assertIn("AGENTS.md", record["stdin"])

    def test_project_local_profile_takes_precedence(self) -> None:
        workflow = self.project_repo / ".workflow"
        workflow.mkdir()
        (workflow / "acceptance.json").write_text(
            json.dumps(
                {
                    "version": 1,
                    "commands": [
                        {"label": "Local check", "command": "python3 -m unittest"}
                    ],
                    "manual": [],
                    "docs": [],
                    "skills": [],
                }
            ),
            encoding="utf-8",
        )
        self.select_project()
        self.send(DESCRIPTION)
        self.click(find_button(self.api.sent[-1]["markup"], "1h"))
        preview = self.api.edited[-1]["text"]
        self.assertIn("project profile .workflow/acceptance.json", preview)
        self.click(find_button(self.api.edited[-1]["markup"], "Confirm: Create job"))
        args = self.invocations()[0]["args"]
        self.assertEqual(
            [args[index + 1] for index, item in enumerate(args) if item == "--criterion"],
            ["Local check::python3 -m unittest"],
        )

    def test_missing_profile_fails_closed_before_cli(self) -> None:
        self.profile_path.unlink()
        self.select_project()
        self.send(DESCRIPTION)
        self.click(find_button(self.api.sent[-1]["markup"], "2h"))
        self.assertIn("no verified acceptance profile", self.api.edited[-1]["text"])
        self.assertEqual(self.invocations(), [])

    def test_invalid_profile_fails_closed(self) -> None:
        self.profile_path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "profiles": {
                        "demo/project": {
                            "commands": [
                                {"label": "Broken", "command": "python3 -m pytest"}
                            ],
                            "docs": ["missing-doc.md"],
                            "skills": [],
                        }
                    },
                }
            ),
            encoding="utf-8",
        )
        self.select_project()
        self.send(DESCRIPTION)
        self.click(find_button(self.api.sent[-1]["markup"], "2h"))
        self.assertIn("Request failed", self.api.edited[-1]["text"])
        self.assertIn("does not exist", self.api.edited[-1]["text"])
        self.assertEqual(self.invocations(), [])


class JobsListingTests(MobileBase):
    def test_button_uses_readable_title_not_job_id(self) -> None:
        self.add_job()
        self.send("/jobs")
        buttons = [
            item["text"]
            for row in self.api.sent[-1]["markup"]["inline_keyboard"]
            for item in row
        ]
        job_button = next(text for text in buttons if "RUNNING" in text)
        self.assertIn("Fix overnight settings save", job_button)
        self.assertNotIn(JOB_ID[:8], job_button)

    def test_listing_shows_project_attempt_runtime_and_date(self) -> None:
        self.add_job()
        self.send("/jobs")
        text = self.api.sent[-1]["text"]
        self.assertIn("demo/project", text)
        self.assertIn("attempt 2", text)
        self.assertIn("active", text)
        self.assertIn("total", text)
        self.assertIn("2026-10-31 12:00Z", text)

    def test_job_status_separates_active_attempt_from_total(self) -> None:
        self.add_job()
        self.send(f"/job {JOB_ID}")
        text = self.api.sent[-1]["text"]
        self.assertIn("Runtime: active attempt", text)
        self.assertIn("total wall-clock", text)


class LogCallbackTests(MobileBase):
    def setUp(self) -> None:
        super().setUp()
        self.add_job()
        directory = self.state_root / "jobs" / JOB_ID
        (directory / "run.log").write_text("run line\n", encoding="utf-8")
        (directory / "worker.log").write_text("worker line\n", encoding="utf-8")

    def test_log_preview_then_download_uses_supported_callbacks(self) -> None:
        for kind, preview in (("Worker log", "worker"), ("Run log", "run")):
            with self.subTest(kind=kind):
                self.send(f"/job {JOB_ID}")
                self.click(find_button(self.api.sent[-1]["markup"], preview))
                self.assertIn(f"{preview} log", self.api.edited[-1]["text"].lower())
                download = find_button(self.api.edited[-1]["markup"], "Download log")
                self.click(download)
                self.assertTrue(self.api.documents)
                self.assertIn(f"-{preview}.redacted.log", self.api.documents[-1]["filename"])
                self.assertNotIn("unknown job action", self.api.edited[-1]["text"].lower())


class ContinuationTests(MobileBase):
    def test_success_job_continuation_uses_plain_language_and_keeps_guard(self) -> None:
        job = make_job(
            "20261102T050000Z-success-job-12345678",
            state="SUCCESS",
            title="Completed settings work",
            repo=str(self.project_repo),
            notifications_enabled=False,
        )
        write_fake_jobs(self.state_root, [job])
        self.send(f"/resume {job['id']}")
        preview = self.api.sent[-1]["text"]
        self.assertNotIn("Force rerun", preview)
        self.assertIn("Allow another attempt", preview)
        self.assertTrue(find_button(self.api.sent[-1]["markup"], "Allow new attempt: off"))
        toggle = find_button(self.api.sent[-1]["markup"], "Allow new attempt: off")
        self.click(toggle)
        self.assertIn("Options: allow another attempt after success", self.api.edited[-1]["text"])
        self.click(find_button(self.api.edited[-1]["markup"], "Confirm resume"))
        self.assertIn("Allow another attempt after success", self.api.edited[-1]["text"])
        self.click(find_button(self.api.edited[-1]["markup"], "Confirm: Resume job"))
        args = self.invocations()[0]["args"]
        self.assertIn("--force", args)

    def test_success_job_without_toggle_stays_refused(self) -> None:
        job = make_job(
            "20261102T050000Z-success-job-87654321",
            state="SUCCESS",
            title="Completed settings work",
            repo=str(self.project_repo),
            notifications_enabled=False,
        )
        write_fake_jobs(self.state_root, [job])
        self.send(f"/resume {job['id']}")
        self.click(find_button(self.api.sent[-1]["markup"], "Confirm resume"))
        self.assertIn("already succeeded", self.api.edited[-1]["text"])
        self.assertEqual(self.invocations(), [])


class JobActionButtonTests(MobileBase):
    def _open_labels(self, state: str, *, drop_worker_alive: bool = False) -> list[str]:
        job = make_job(
            f"20261102T060000Z-action-{state.lower()}-abcdef12",
            state=state,
            title=f"{state} action job",
            repo=str(self.project_repo),
            notifications_enabled=False,
        )
        if drop_worker_alive:
            # Raw dev start/resume output does not include the computed field.
            job.pop("worker_alive", None)
        write_fake_jobs(self.state_root, [job])
        self.send(f"/job {job['id']}")
        return [
            item["text"]
            for row in self.api.sent[-1]["markup"]["inline_keyboard"]
            for item in row
        ]

    def test_running_job_shows_cancel_and_never_resume(self) -> None:
        for drop_worker_alive in (False, True):
            with self.subTest(drop_worker_alive=drop_worker_alive):
                labels = self._open_labels(
                    "RUNNING", drop_worker_alive=drop_worker_alive
                )
                self.assertIn("Cancel job", labels)
                self.assertNotIn("Resume", labels)
                self.assertIn("Queue instruction", labels)

    def test_terminal_states_show_resume_and_never_cancel(self) -> None:
        for state in ("SUCCESS", "FAILED", "BLOCKED", "CANCELLED", "TIMEOUT"):
            with self.subTest(state=state):
                labels = self._open_labels(state)
                self.assertIn("Resume", labels)
                self.assertNotIn("Cancel job", labels)
                self.assertIn("Queue instruction", labels)


class LifecycleJobActionTests(MobileBase):
    def _raw_running_job(self) -> dict:
        job = make_job(
            "20261102T060000Z-lifecycle-actions-12345678",
            state="RUNNING",
            title="Lifecycle action job",
            repo=str(self.project_repo),
            notifications_enabled=False,
        )
        # This is the shape returned by dev start/resume before status_payload.
        job.pop("worker_alive", None)
        write_fake_jobs(self.state_root, [job])
        return job

    def _sent_labels(self) -> list[str]:
        return [
            item["text"]
            for row in self.api.sent[-1]["markup"]["inline_keyboard"]
            for item in row
        ]

    def test_started_notification_uses_cancel_for_raw_running_job(self) -> None:
        job = self._raw_running_job()
        self.notifier.notify_started(job, project_id="demo/project")
        labels = self._sent_labels()
        self.assertIn("Cancel job", labels)
        self.assertNotIn("Resume", labels)
        self.assertIn("Queue instruction", labels)

    def test_resumed_notification_uses_cancel_for_raw_running_job(self) -> None:
        job = self._raw_running_job()
        self.notifier.notify_resumed(job)
        labels = self._sent_labels()
        self.assertIn("Cancel job", labels)
        self.assertNotIn("Resume", labels)
        self.assertIn("Queue instruction", labels)


class CancellationSafetyTests(MobileBase):
    def _running_job(self, *, attempts: int = 1) -> dict:
        job = make_job(
            "20261102T060000Z-cancel-safety-abcdef12",
            state="RUNNING",
            title="Cancel safety job",
            repo=str(self.project_repo),
            attempts=attempts,
            notifications_enabled=False,
        )
        write_fake_jobs(self.state_root, [job])
        return job

    def _cancel_invocations(self) -> list[dict]:
        return [item for item in self.invocations() if item["args"][:1] == ["cancel"]]

    def test_confirm_replay_invokes_cancel_once(self) -> None:
        job = self._running_job()
        self.send(f"/cancel {job['id']}")
        confirm = find_button(
            self.api.sent[-1]["markup"], "Confirm: Cancel running job"
        )
        self.click(confirm)
        self.click(confirm)
        self.assertEqual(len(self._cancel_invocations()), 1)
        self.assertIn("expired or already used", self.api.edited[-1]["text"])

    def test_stale_confirmation_cannot_cancel_a_later_attempt(self) -> None:
        job = self._running_job(attempts=1)
        self.send(f"/cancel {job['id']}")
        confirm = find_button(
            self.api.sent[-1]["markup"], "Confirm: Cancel running job"
        )
        # Simulate the same job being resumed to attempt #2 before the stale
        # confirmation is pressed.
        write_fake_jobs(self.state_root, [self._running_job(attempts=2)])
        self.click(confirm)
        self.assertIn("earlier attempt", self.api.edited[-1]["text"])
        self.assertEqual(self._cancel_invocations(), [])

    def test_stale_job_button_cannot_cancel_a_finished_job(self) -> None:
        job = self._running_job()
        self.send(f"/job {job['id']}")
        cancel = find_button(self.api.sent[-1]["markup"], "Cancel job")
        finished = dict(job)
        finished["state"] = "CANCELLED"
        finished["worker_alive"] = False
        expected = "2026-11-02T06:10:00Z"
        finished["ended_at"] = expected
        write_fake_jobs(self.state_root, [finished])
        self.click(cancel)
        self.assertIn("not RUNNING", self.api.edited[-1]["text"])
        self.assertEqual(self._cancel_invocations(), [])


class ResultSummaryTests(MobileBase):
    def _record(self, *, manual_verified: bool = False, state: str = "SUCCESS") -> dict:
        verification = {
            "AC1": {"verified": True, "exit_code": 0},
        }
        criteria = [
            {"id": "AC1", "kind": "command", "label": "Build", "command": "true"}
        ]
        if manual_verified:
            criteria.append(
                {"id": "AC2", "kind": "manual", "label": "Owner verifies the bug"}
            )
            verification["AC2"] = {"verified": True}
        return {
            "id": JOB_ID,
            "state": state,
            "git": {"diffstat": " src/settings.ts | 3 ++-"},
            "acceptance_criteria": criteria,
            "verification": verification,
            "completion_contract": {
                "configured": True,
                "state": "VERIFIED" if state == "SUCCESS" else "FAILED",
                "checks": [
                    {"id": "commit", "status": "passed", "detail": "commit verified"},
                    {"id": "push", "status": "passed", "detail": "push verified"},
                    {
                        "id": "remote_sha",
                        "status": "passed",
                        "detail": "remote SHA abcdef123456",
                    },
                ],
            },
        }

    def test_technical_success_is_not_functional_proof(self) -> None:
        record = self._record()
        payload = {
            "id": JOB_ID,
            "state": "SUCCESS",
            "completion_contract": record["completion_contract"],
            "issues": [],
        }
        text = summary.summary_text(payload, record, project="demo/project")
        self.assertIn("Technical completion: VERIFIED", text)
        self.assertIn("Functional outcome: NOT VERIFIED", text)
        self.assertIn("do not prove", text)
        self.assertIn("GitHub delivery: verified", text)
        self.assertIn("Tests: 1 verified", text)

    def test_manual_acceptance_can_verify_functional_outcome(self) -> None:
        record = self._record(manual_verified=True)
        payload = {
            "id": JOB_ID,
            "state": "SUCCESS",
            "completion_contract": record["completion_contract"],
            "issues": [],
        }
        text = summary.summary_text(payload, record)
        self.assertIn("Functional outcome: VERIFIED", text)
        self.assertIn("owner/manual acceptance", text)

    def test_unresolved_issue_remains_explicit(self) -> None:
        record = self._record()
        payload = {
            "id": JOB_ID,
            "state": "SUCCESS",
            "completion_contract": record["completion_contract"],
            "issues": [
                {
                    "severity": "HIGH",
                    "kind": "runtime",
                    "message": "intermittent failure still reproduced",
                }
            ],
        }
        text = summary.summary_text(payload, record)
        self.assertIn("Functional outcome: UNRESOLVED", text)
        self.assertIn("intermittent failure", text)

    def test_job_view_includes_result_summary(self) -> None:
        record = self._record()
        job = make_job(
            JOB_ID,
            state="SUCCESS",
            title="Settings bug",
            repo=str(self.project_repo),
            notifications_enabled=False,
        )
        job["completion_contract"] = record["completion_contract"]
        job["acceptance_criteria"] = record["acceptance_criteria"]
        job["verification"] = record["verification"]
        job["git"] = record["git"]
        job["issues"] = []
        write_fake_jobs(self.state_root, [job])
        self.send(f"/job {JOB_ID}")
        text = self.api.sent[-1]["text"]
        self.assertIn("Result summary", text)
        self.assertIn("Technical completion: VERIFIED", text)
        self.assertIn("Functional outcome: NOT VERIFIED", text)
        self.assertIn("Report", text)


class AcceptanceProfileUnitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="qdm-profiles-")
        self.root = Path(self.temporary.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.registry = self.root / "PROJECT-REGISTRY.md"
        self.registry.write_text("# registry\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_missing_profile_is_an_error(self) -> None:
        with self.assertRaises(acceptance_profiles.ProfileError):
            acceptance_profiles.resolve_profile(
                project_id="demo/project",
                platform="Qortal",
                repo=self.repo,
                registry_path=self.registry,
            )

    def test_unsafe_context_path_is_refused(self) -> None:
        (self.repo / ".workflow").mkdir()
        (self.repo / ".workflow" / "acceptance.json").write_text(
            json.dumps(
                {
                    "commands": [{"label": "Check", "command": "true"}],
                    "docs": ["../outside.md"],
                }
            ),
            encoding="utf-8",
        )
        with self.assertRaises(acceptance_profiles.ProfileError):
            acceptance_profiles.resolve_profile(
                project_id="demo/project",
                platform="Qortal",
                repo=self.repo,
                registry_path=self.registry,
            )

    def test_context_includes_control_plane_and_platform_instructions(self) -> None:
        profile = acceptance_profiles.resolve_profile(
            project_id="control-plane/control-plane",
            platform="Control plane",
            repo=TOOLS.parent,
            registry_path=TOOLS.parent / "PROJECT-REGISTRY.md",
        )
        context = acceptance_profiles.discover_context(profile, platform="Control plane")
        paths = {str(item.path) for item in context}
        self.assertIn(str(TOOLS.parent / "AGENTS.md"), paths)
        self.assertIn(str(TOOLS.parent / "WORKFLOW.md"), paths)
        self.assertIn(str(TOOLS.parent / "skills" / "README.md"), paths)

    def test_central_profiles_match_current_project_scripts(self) -> None:
        from devjob import project_policy

        profiles = acceptance_profiles._read_json(
            TOOLS.parent / "acceptance-profiles.json"
        )["profiles"]
        projects = {
            item.project_id: item
            for item in project_policy.parse_registry(TOOLS.parent / "PROJECT-REGISTRY.md")
        }
        for project_id, entry in profiles.items():
            project = projects.get(project_id)
            self.assertIsNotNone(project, project_id)
            assert project is not None
            package = project.repo_path / "package.json"
            if not package.is_file():
                continue
            scripts = set(
                json.loads(package.read_text(encoding="utf-8")).get("scripts", {})
            )
            for command in entry.get("commands") or []:
                text = command if isinstance(command, str) else command.get("command", "")
                if text.startswith("npm run "):
                    self.assertIn(text.split()[2], scripts, (project_id, text))
                elif text == "npm test":
                    self.assertIn("test", scripts, project_id)

    def test_log_menu_callbacks_are_supported(self) -> None:
        from devmonitor import menus
        from devmonitor.router import SAFE_CALLBACK_LABELS

        markup = menus.log_menu("abc123", "run")
        callback = markup["inline_keyboard"][0][0]["callback_data"]
        self.assertEqual(callback, "j:abc123:lr")
        download = markup["inline_keyboard"][1][0]["callback_data"]
        self.assertEqual(download, "j:abc123:dlr")
        self.assertIn(download.split(":")[0], SAFE_CALLBACK_LABELS)

    def test_central_profile_commands_are_explicit(self) -> None:
        data = json.loads(
            (TOOLS.parent / "acceptance-profiles.json").read_text(encoding="utf-8")
        )
        for project_id, entry in data["profiles"].items():
            with self.subTest(project_id=project_id):
                self.assertTrue(entry.get("commands"))
                for command in entry["commands"]:
                    self.assertTrue(command.get("label"))
                    self.assertTrue(command.get("command"))

    def test_derive_title_is_readable_and_bounded(self) -> None:
        self.assertEqual(derive_title("  ## Fix the save bug  "), "Fix the save bug")
        long = "word " * 80
        title = derive_title(long, limit=40)
        self.assertLessEqual(len(title), 43)
        self.assertTrue(title.endswith("..."))
        with self.assertRaises(ControlError):
            derive_title("   ")


if __name__ == "__main__":
    unittest.main()
