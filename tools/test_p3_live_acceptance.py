#!/usr/bin/env python3
"""Regression tests for the isolated P3 Telegram live acceptance harness.

Every test uses temporary directories and a fake Telegram API. No test contacts
Telegram, starts an OpenCode session, sends a message, signals a process or
touches the production registry, live monitor state or the Qortium node.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

from devmonitor.acceptance import (  # noqa: E402
    DEFAULT_INSTRUCTION,
    EVIDENCE_FILENAME,
    SYNTHETIC_MARKER,
    SYNTHETIC_PROJECT_ID,
    AcceptanceError,
    LiveAcceptanceHarness,
)
from devmonitor.config import load_monitor_config  # noqa: E402
from devmonitor_test_support import (  # noqa: E402
    FakeApi,
    callback_update,
    init_project_repo,
    message_update,
)


def find_button(markup, text_fragment: str) -> str:
    for row in (markup or {}).get("inline_keyboard", []):
        for item in row:
            if text_fragment.lower() in item.get("text", "").lower():
                return item["callback_data"]
    raise AssertionError(f"button not found: {text_fragment}")


def find_callback(markup, prefix: str) -> str:
    for row in (markup or {}).get("inline_keyboard", []):
        for item in row:
            data = str(item.get("callback_data") or "")
            if data.startswith(prefix):
                return data
    raise AssertionError(f"callback not found: {prefix}")


class HarnessBase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="qdm-p3live-")
        self.root = Path(self.temporary.name)
        (self.root / "live-state").mkdir()
        self.source = self.root / "source"
        self.source.mkdir()
        self.source_repo = init_project_repo(self.source / "Demo")
        self.source_docs = self.source / "docs"
        self.source_docs.mkdir()
        self.source_registry = self.source / "PROJECT-REGISTRY.md"
        self.source_registry.write_text(
            "# Project registry\n\n## Registered projects\n\n"
            "| ID | Platform | Verified local path | Project-level `AGENTS.md` | Canonical context | Central report root | Git remote | GitHub repository | Development branch pattern | Automatic push |\n"
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
            f"| `demo/project` | Qortal | `{self.source_repo}` | Yes | Pending | `{self.source_docs}/` | "
            "`origin` | `demo/project` | `agent/*` | `yes` |\n",
            encoding="utf-8",
        )
        self.source_config = self._write_source_config()
        self.work = self.root / "work"
        self.work.mkdir()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _write_source_config(
        self, *, mode: str = "control", queue: bool = True, mode_bits: int = 0o600
    ) -> Path:
        path = self.source / "telegram.json"
        path.write_text(
            json.dumps(
                {
                    "enabled": False,
                    "bot_token": "123456789:" + "A" * 30,
                    "chat_id": "2002",
                    "events": ["SUCCESS", "FAILED", "BLOCKED", "TIMEOUT", "CANCELLED"],
                    "monitor": {
                        "mode": mode,
                        "authorized_user_ids": [1001],
                        "allowed_chat_ids": [2002],
                        "require_private_chat": True,
                        "agent_allowlist": ["opencode-development"],
                        "model_allowlist": ["deepseek/deepseek-flash"],
                        "registry_path": str(self.source_registry),
                        "docs_roots": [str(self.source_docs)],
                        "allowed_repo_roots": [str(self.source)],
                        "queue_owner_messages": queue,
                    },
                }
            ),
            encoding="utf-8",
        )
        os.chmod(path, mode_bits)
        return path

    def prepare(self, **kwargs) -> LiveAcceptanceHarness:
        return LiveAcceptanceHarness.prepare(
            self.work,
            source_config=self.source_config,
            live_state_dir=self.root / "live-state",
            monitor_running_func=lambda _path: False,
            **kwargs,
        )


class PrepareTests(HarnessBase):
    def test_prepare_creates_isolated_fixture_and_preserves_sources(self) -> None:
        config_hash = self.source_config.read_bytes()
        registry_hash = self.source_registry.read_bytes()
        harness = self.prepare()

        self.assertTrue((self.work / ".p3-live-acceptance").is_file())
        manifest = json.loads((self.work / "manifest.json").read_text(encoding="utf-8"))
        self.assertTrue(manifest["synthetic"])
        self.assertEqual(manifest["job_id"], harness.job_id)
        self.assertEqual(manifest["project_id"], SYNTHETIC_PROJECT_ID)
        self.assertEqual(manifest["source"]["registry"], str(self.source_registry.resolve()))
        self.assertFalse(manifest["isolation"]["production_registry_modified"])

        # The production config and registry are byte-for-byte unchanged.
        self.assertEqual(self.source_config.read_bytes(), config_hash)
        self.assertEqual(self.source_registry.read_bytes(), registry_hash)

        # The temporary registry contains only the synthetic project.
        temp_registry = Path(manifest["paths"]["registry"]).read_text(encoding="utf-8")
        self.assertIn(SYNTHETIC_PROJECT_ID, temp_registry)
        self.assertNotIn("demo/project", temp_registry)
        self.assertNotIn(str(self.source_repo), temp_registry)

        # The temporary repository is a real, isolated Git checkout.
        repo = Path(manifest["paths"]["repo"])
        self.assertNotEqual(repo, self.source_repo)
        remote = subprocess.run(
            ["git", "-C", str(repo), "config", "--get", "remote.origin.url"],
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(remote.stdout.strip(), "https://github.com/synthetic/p3-live-acceptance.git")
        self.assertTrue((repo / "README.md").is_file())

        # The temporary monitor config points only at isolated paths.
        temp_config = json.loads(Path(manifest["paths"]["config"]).read_text(encoding="utf-8"))
        monitor = temp_config["monitor"]
        self.assertEqual(monitor["mode"], "control")
        self.assertEqual(monitor["registry_path"], manifest["paths"]["registry"])
        self.assertEqual(monitor["allowed_repo_roots"], [str(Path(manifest["paths"]["repo"]).parent)])
        self.assertEqual(monitor["docs_roots"], [manifest["paths"]["docs"]])
        self.assertEqual(oct(Path(manifest["paths"]["config"]).stat().st_mode & 0o777), "0o600")

        job = json.loads(
            (Path(manifest["paths"]["job_state"]) / "jobs" / harness.job_id / "job.json").read_text()
        )
        self.assertEqual(job["state"], "RUNNING")
        self.assertTrue(job["synthetic"])
        self.assertEqual(job["synthetic_marker"], SYNTHETIC_MARKER)
        self.assertNotEqual(job["state"], "SUCCESS")
        self.assertFalse(job["notifications_enabled"])

    def test_prepare_refuses_when_live_monitor_is_running(self) -> None:
        with self.assertRaises(AcceptanceError):
            LiveAcceptanceHarness.prepare(
                self.work,
                source_config=self.source_config,
                live_state_dir=self.root / "live-state",
                monitor_running_func=lambda _path: True,
            )
        self.assertFalse((self.work / "manifest.json").exists())

    def test_prepare_refuses_read_only_mode(self) -> None:
        self.source_config = self._write_source_config(mode="read_only")
        with self.assertRaises(AcceptanceError):
            self.prepare()

    def test_prepare_refuses_disabled_queue(self) -> None:
        self.source_config = self._write_source_config(queue=False)
        with self.assertRaises(AcceptanceError):
            self.prepare()

    def test_prepare_refuses_insecure_source_config(self) -> None:
        self.source_config = self._write_source_config(mode_bits=0o644)
        with self.assertRaises(AcceptanceError):
            self.prepare()

    def test_prepare_refuses_production_state_as_work_dir(self) -> None:
        from devjob import store

        target = store.state_root() / "p3-live-acceptance-test"
        with self.assertRaises(AcceptanceError):
            LiveAcceptanceHarness.prepare(
                target,
                source_config=self.source_config,
                live_state_dir=self.root / "live-state",
                monitor_running_func=lambda _path: False,
            )
        self.assertFalse(target.exists())


class FakeWorkerTests(HarnessBase):
    def _run_fake(self, harness: LiveAcceptanceHarness, *args: str, stdin: str | None = None):
        manifest = harness.manifest
        env = dict(os.environ)
        env["DEV_CONTROL_PLANE_STATE"] = manifest["paths"]["job_state"]
        return subprocess.run(
            [sys.executable, manifest["paths"]["fake_dev"], *args],
            input=stdin,
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )

    def test_fake_worker_cancels_without_success_and_without_signals(self) -> None:
        harness = self.prepare()
        result = self._run_fake(harness, "cancel", harness.job_id, "--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["cancel_status"], "cancelled")
        self.assertIn("no process signalled", payload["detail"])
        job = json.loads(
            (Path(harness.manifest["paths"]["job_state"]) / "jobs" / harness.job_id / "job.json").read_text()
        )
        self.assertEqual(job["state"], "CANCELLED")
        self.assertNotEqual(job["state"], "SUCCESS")
        source = Path(__file__).resolve().parent / "devmonitor" / "acceptance.py"
        self.assertNotIn("os.kill", source.read_text(encoding="utf-8"))

    def test_fake_worker_resume_records_instruction_and_never_succeeds(self) -> None:
        harness = self.prepare()
        self.assertEqual(self._run_fake(harness, "cancel", harness.job_id, "--json").returncode, 0)
        body = f"{DEFAULT_INSTRUCTION}\n"
        result = self._run_fake(
            harness, "resume", harness.job_id, "--prompt-file", "-", "--json", stdin=body
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        resumed = json.loads(result.stdout)
        self.assertEqual(resumed["state"], "RUNNING")
        self.assertNotEqual(resumed["state"], "SUCCESS")
        invocations = Path(harness.manifest["paths"]["job_state"]) / "fake_invocations.jsonl"
        records = [json.loads(line) for line in invocations.read_text().splitlines()]
        self.assertTrue(any(SYNTHETIC_MARKER in str(item.get("stdin")) for item in records))

    def test_fake_worker_refuses_a_non_synthetic_job(self) -> None:
        harness = self.prepare()
        jobs_path = Path(harness.manifest["paths"]["job_state"]) / "fake_jobs.json"
        jobs = json.loads(jobs_path.read_text())
        jobs[harness.job_id]["synthetic"] = False
        jobs_path.write_text(json.dumps(jobs))
        result = self._run_fake(harness, "cancel", harness.job_id, "--json")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("non-synthetic", result.stderr)


class FullFlowTests(HarnessBase):
    def _load_and_build(self, harness: LiveAcceptanceHarness):
        config = harness._load_config()
        api = FakeApi()
        service, state, config, recording, router, jobs = harness._build_service(
            config, api=api
        )
        return api, service, state, config, recording, router, jobs

    def _feed(self, service, api: FakeApi, update: dict) -> None:
        api.updates = [[update]]
        service.run(max_iterations=1)

    def _last_markup(self, api: FakeApi) -> dict:
        candidates = [item for item in api.sent if item.get("markup")]
        candidates += [item for item in api.edited if item.get("markup")]
        if not candidates:
            raise AssertionError("no markup was sent")
        latest = max(candidates, key=lambda item: int(item.get("message_id") or 0))
        return latest["markup"]

    def _write_evidence(self, harness: LiveAcceptanceHarness) -> Path:
        path = Path(harness.manifest["paths"]["telegram_evidence"])
        payload = json.loads(path.read_text())
        payload.update(
            {
                "operator": "Regression Test Operator",
                "started_at_utc": "2026-11-01T12:00:00Z",
                "finished_at_utc": "2026-11-01T12:05:00Z",
                "no_success_observed": True,
                "production_untouched": True,
                "qortium_unchanged": True,
                "notes": "Offline fake-API regression test.",
            }
        )
        path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return path

    def test_live_flow_queue_and_cancel_produces_verifiable_evidence(self) -> None:
        harness = self.prepare()
        api, service, state, config, recording, router, jobs = self._load_and_build(harness)
        try:
            self._feed(service, api, message_update(1, "/jobs"))
            job_callback = find_callback(self._last_markup(api), "j:")
            self._feed(service, api, callback_update(2, job_callback))
            job_view = self._last_markup(api)
            self.assertTrue(any("Queue instruction" in item.get("text", "") for row in job_view["inline_keyboard"] for item in row))
            self.assertTrue(any("Cancel job" in item.get("text", "") for row in job_view["inline_keyboard"] for item in row))

            queue_callback = find_button(job_view, "Queue instruction")
            self._feed(service, api, callback_update(3, queue_callback))
            self.assertTrue(
                any("Queue an owner instruction" in item["text"] for item in api.edited)
            )
            self._feed(service, api, message_update(4, DEFAULT_INSTRUCTION))
            self.assertTrue(
                any("Instruction queued" in item["text"] for item in api.sent + api.edited)
            )

            # Re-open the job to reach the live job menu after queueing.
            self._feed(service, api, message_update(5, f"/job {harness.job_id}"))
            cancel_callback = find_button(self._last_markup(api), "Cancel job")
            self._feed(service, api, callback_update(6, cancel_callback))
            self.assertTrue(
                any("Cancel this running job?" in item["text"] for item in api.edited)
            )
            confirm = find_button(api.edited[-1]["markup"], "Confirm: Cancel running job")
            self._feed(service, api, callback_update(7, confirm))
            self.assertTrue(
                any("Cancel result: cancelled" in item["text"] for item in api.edited)
            )
            job = json.loads(
                (Path(harness.manifest["paths"]["job_state"]) / "jobs" / harness.job_id / "job.json").read_text()
            )
            self.assertEqual(job["state"], "CANCELLED")
        finally:
            state.close()

        evidence = self._write_evidence(harness)
        report = harness.verify(evidence)
        self.assertTrue(report["ok"])
        self.assertTrue(report["synthetic"])
        self.assertEqual(report["final_state"], "CANCELLED")
        self.assertEqual(report["instruction_state"], "queued")
        self.assertIn("Queue instruction", report["telegram"]["buttons"])
        self.assertIn("Cancel job", report["telegram"]["buttons"])
        self.assertIn("Confirm: Cancel running job", report["telegram"]["callbacks"])
        self.assertGreaterEqual(len(report["telegram"]["message_ids"]), 1)
        self.assertTrue(Path(harness.manifest["paths"]["report"]).is_file())

    def test_live_monitor_offset_is_read_only_and_required(self) -> None:
        import sqlite3

        harness = self.prepare()
        live_state = Path(harness.manifest["source"]["live_state_dir"])
        database = live_state / "monitor.db"
        connection = sqlite3.connect(database)
        try:
            connection.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            connection.execute("INSERT INTO meta(key, value) VALUES('update_offset', '42')")
            connection.commit()
        finally:
            connection.close()
        self.assertEqual(harness._live_monitor_offset(), 42)
        before = database.read_bytes()
        self.assertEqual(harness._live_monitor_offset(), 42)
        self.assertEqual(database.read_bytes(), before)
        database.unlink()
        with self.assertRaises(AcceptanceError):
            harness._live_monitor_offset()

    def test_run_refuses_without_explicit_live_confirmation(self) -> None:
        harness = self.prepare()
        with self.assertRaises(AcceptanceError):
            harness.run()
        journal = Path(harness.manifest["paths"]["journal"]).read_text(encoding="utf-8")
        self.assertEqual(journal, "")

    def test_verify_rejects_unrecorded_evidence(self) -> None:
        harness = self.prepare()
        api, service, state, config, recording, router, jobs = self._load_and_build(harness)
        try:
            self._feed(service, api, message_update(1, "/jobs"))
            job_callback = find_callback(self._last_markup(api), "j:")
            self._feed(service, api, callback_update(2, job_callback))
            queue_callback = find_button(self._last_markup(api), "Queue instruction")
            self._feed(service, api, callback_update(3, queue_callback))
            self._feed(service, api, message_update(4, DEFAULT_INSTRUCTION))
            self._feed(service, api, message_update(5, f"/job {harness.job_id}"))
            cancel_callback = find_button(self._last_markup(api), "Cancel job")
            self._feed(service, api, callback_update(6, cancel_callback))
            confirm = find_button(api.edited[-1]["markup"], "Confirm: Cancel running job")
            self._feed(service, api, callback_update(7, confirm))
        finally:
            state.close()
        with self.assertRaises(AcceptanceError):
            harness.verify(Path(harness.manifest["paths"]["telegram_evidence"]))

    def test_verify_rejects_success_state_and_non_synthetic_jobs(self) -> None:
        harness = self.prepare()
        evidence = self._write_evidence(harness)
        # A synthetic SUCCESS is never acceptable.
        job_path = Path(harness.manifest["paths"]["job_state"]) / "jobs" / harness.job_id / "job.json"
        job = json.loads(job_path.read_text())
        job["state"] = "SUCCESS"
        job_path.write_text(json.dumps(job))
        with self.assertRaises(AcceptanceError):
            harness.verify(evidence)

        # A non-synthetic job record is never acceptable.
        job["state"] = "CANCELLED"
        job_path.write_text(json.dumps(job))
        other = Path(harness.manifest["paths"]["job_state"]) / "jobs" / "real-job" / "job.json"
        other.parent.mkdir(parents=True)
        other.write_text(json.dumps({"id": "real-job", "state": "SUCCESS"}))
        with self.assertRaises(AcceptanceError):
            harness.verify(evidence)

    def test_verify_rejects_changed_source_config(self) -> None:
        harness = self.prepare()
        self._write_evidence(harness)
        self.source_config.write_text(self.source_config.read_text() + "\n", encoding="utf-8")
        os.chmod(self.source_config, 0o600)
        with self.assertRaises(AcceptanceError):
            harness.verify()

    def test_cleanup_requires_marker_and_removes_only_the_fixture(self) -> None:
        harness = self.prepare()
        self.assertTrue(self.work.is_dir())
        harness.cleanup()
        self.assertFalse(self.work.exists())
        self.assertTrue(self.source_config.is_file())
        self.assertTrue(self.source_registry.is_file())

        # A directory without the marker is refused.
        stray = self.root / "stray"
        stray.mkdir()
        with self.assertRaises(AcceptanceError):
            LiveAcceptanceHarness.load(stray, monitor_running_func=lambda _path: False)


if __name__ == "__main__":
    unittest.main()
