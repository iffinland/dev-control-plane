#!/usr/bin/env python3
"""Tests for the executable Workflow v3 completion contract."""

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

from devjob import contract, evidence, runner  # noqa: E402

EVIDENCE = """# Task

## Task-start contract

- Skills loaded: `skills/shared/app-bootstrap/SKILL.md`, freshness last checked 2026-11-01.
- Documentation read: `WORKFLOW.md` and `docs/operations/DEV-WORKFLOW-V3.md`.
- Capability harvest: updated a reusable skill.
- Documentation update: updated `WORKFLOW.md`.
"""


class GitRepo:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.env = os.environ.copy()
        self.env.update(
            {
                "GIT_AUTHOR_NAME": "Test",
                "GIT_AUTHOR_EMAIL": "test@example.invalid",
                "GIT_COMMITTER_NAME": "Test",
                "GIT_COMMITTER_EMAIL": "test@example.invalid",
                "GIT_CONFIG_NOSYSTEM": "1",
            }
        )

    def git(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["git", "-C", str(self.root), *args],
            capture_output=True,
            text=True,
            env=self.env,
            check=False,
        )

    def write(self, relative: str, text: str) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def commit(self, message: str = "commit") -> str:
        self.git("add", "-A")
        result = self.git("commit", "-m", message)
        if result.returncode != 0:
            raise AssertionError(result.stderr)
        return self.git("rev-parse", "HEAD").stdout.strip()


def make_repo(tmp: Path, branch: str = "agent/test/job") -> tuple[GitRepo, str]:
    repo = GitRepo(tmp / "repo")
    repo.root.mkdir()
    repo.git("init")
    repo.git("checkout", "-b", branch)
    repo.write("README.md", "baseline\n")
    base = repo.commit("baseline")
    return repo, base


def spec_for(base: str, **overrides) -> dict:
    spec = {
        "version": 1,
        "branch": "agent/test/job",
        "base_sha": base,
        "evidence_files": ["TASK.md"],
        "require": {
            "skill_discovery": True,
            "freshness": True,
            "documentation_loading": True,
            "capability_harvest": True,
            "documentation_updates": True,
            "clean_tree": True,
            "commit": True,
            "push": False,
        },
        "authorization": {"push": False},
    }
    spec.update(overrides)
    return spec


def push_remote(repo: GitRepo, branch: str = "agent/test/job") -> str:
    bare = repo.root.parent / "remote.git"
    subprocess.run(["git", "init", "--bare", str(bare)], check=True, env=repo.env)
    repo.git("remote", "add", "dev-control-plane", str(bare))
    result = repo.git("push", "-u", "dev-control-plane", branch)
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    return str(bare)


def structured_evidence(
    job_id: str,
    *,
    fill: bool = True,
    job_id_line: str | None = None,
) -> str:
    text = evidence.build_template(
        job_id=job_id,
        title="test job",
        repo="/tmp/repo",
        branch="agent/test/job",
        base_sha="a" * 40,
        project_id="test/project",
        contract_source="default",
        initialized_at="2026-11-01T00:00:00Z",
    )
    if job_id_line is not None:
        text = text.replace(f"- job_id: {job_id}", f"- job_id: {job_id_line}")
    if fill:
        values = {
            "skill_discovery": "Loaded skills/shared/app-bootstrap/SKILL.md; platform shared, last checked 2026-11-01.",
            "freshness": "Checked contract.py revision at the base SHA; compatible.",
            "documentation_loading": "Read docs/operations/DEV-WORKFLOW-V3.md and WORKFLOW.md.",
            "capability_harvest": "Capability harvest: project-specific; no reusable update needed.",
            "documentation_updates": "Documentation update: none needed for this fixture.",
        }
        for field, value in values.items():
            text = text.replace(f"- {field}: UNRECORDED", f"- {field}: {value}")
    return text


def checks_by_id(result: dict) -> dict:
    return {item["id"]: item for item in result.get("checks") or []}


class CompletionContractTests(unittest.TestCase):
    def test_read_only_contract_verifies_only_when_nothing_was_committed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo, base = make_repo(Path(directory))
            spec = {"base_sha": base, "read_only": True, "authorization": {}}
            checks = {item["id"]: item for item in contract._commit_checks(repo.root, spec)}
            self.assertEqual(checks["commit"]["status"], "verified")
            push = contract._push_check(repo.root, spec, "agent/test/job", {})
            self.assertEqual(push["status"], "verified")
            self.assertIn("no push", push["detail"])
            repo.write("unexpected.txt", "changed\n")
            repo.commit("read-only job must not commit")
            checks = {item["id"]: item for item in contract._commit_checks(repo.root, spec)}
            self.assertEqual(checks["commit"]["status"], "failed")
            self.assertIn("must not change", checks["commit"]["detail"])

    def test_read_only_cannot_authorize_push(self) -> None:
        spec = {
            "version": 1,
            "base_sha": "0" * 40,
            "read_only": True,
            "authorization": {"push": True},
        }
        with self.assertRaises(contract.ContractError):
            contract.prepare_contract(
                spec,
                branch="agent/test/job",
                base_sha="0" * 40,
                read_only=True,
            )

    def test_verified_contract_with_authorized_push(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo, base = make_repo(Path(directory))
            repo.write("TASK.md", EVIDENCE)
            repo.write("src/change.txt", "ok\n")
            commit = repo.commit("implement")
            push_remote(repo)
            spec = spec_for(
                base,
                require={
                    "skill_discovery": True,
                    "freshness": True,
                    "documentation_loading": True,
                    "capability_harvest": True,
                    "documentation_updates": True,
                    "clean_tree": True,
                    "commit": True,
                    "push": True,
                },
                authorization={"push": True},
                allowed_paths=["TASK.md", "src/"],
                remote="dev-control-plane",
            )
            job = {"repo": str(repo.root)}
            result = contract.evaluate(job, spec)
            self.assertEqual(result["state"], "VERIFIED", result)
            self.assertEqual(result["branch"], "agent/test/job")
            self.assertEqual(commit, repo.git("rev-parse", "HEAD").stdout.strip())
            self.assertEqual(checks_by_id(result)["remote_sha"]["status"], "verified")

    def test_missing_task_start_evidence_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo, base = make_repo(Path(directory))
            repo.write("TASK.md", "# Task\n\nNo process evidence.\n")
            repo.write("src/change.txt", "ok\n")
            repo.commit("implement")
            result = contract.evaluate({"repo": str(repo.root)}, spec_for(base))
            self.assertEqual(result["state"], "FAILED")
            failed = set(result["failed_checks"])
            self.assertIn("skill_discovery", failed)
            self.assertIn("freshness", failed)
            self.assertIn("capability_harvest", failed)

    def test_uncommitted_change_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo, base = make_repo(Path(directory))
            repo.write("TASK.md", EVIDENCE)
            repo.commit("implement")
            repo.write("leftover.txt", "uncommitted\n")
            result = contract.evaluate({"repo": str(repo.root)}, spec_for(base))
            self.assertIn("clean_tree", result["failed_checks"])

    def test_declared_owner_dirty_paths_are_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo, base = make_repo(Path(directory))
            repo.write("TASK.md", EVIDENCE)
            repo.commit("implement")
            repo.write("owner/work.md", "preserved owner change\n")
            spec = spec_for(base, allowed_dirty_paths=["owner/"])
            result = contract.evaluate({"repo": str(repo.root)}, spec)
            self.assertNotIn("clean_tree", result["failed_checks"])

    def test_protected_branch_without_authorization_is_pending(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo, base = make_repo(Path(directory), branch="main")
            repo.write("TASK.md", EVIDENCE)
            repo.commit("implement")
            spec = spec_for(base, branch="main")
            result = contract.evaluate({"repo": str(repo.root)}, spec)
            self.assertEqual(result["state"], "PENDING", result)
            self.assertIn("protected_branch", result["pending_checks"])

    def test_push_without_authorization_is_pending(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo, base = make_repo(Path(directory))
            repo.write("TASK.md", EVIDENCE)
            repo.commit("implement")
            spec = spec_for(
                base,
                require={**spec_for(base)["require"], "push": True},
            )
            result = contract.evaluate({"repo": str(repo.root)}, spec)
            self.assertEqual(result["state"], "PENDING")
            self.assertIn("remote_sha", result["pending_checks"])

    def test_remote_sha_mismatch_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo, base = make_repo(Path(directory))
            repo.write("TASK.md", EVIDENCE)
            repo.commit("implement")
            push_remote(repo)
            repo.write("src/change.txt", "later\n")
            repo.commit("more local work")
            spec = spec_for(
                base,
                require={**spec_for(base)["require"], "push": True},
                authorization={"push": True},
                remote="dev-control-plane",
            )
            result = contract.evaluate({"repo": str(repo.root)}, spec)
            self.assertIn("remote_sha", result["failed_checks"])

    def test_merge_commit_without_authorization_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo, base = make_repo(Path(directory))
            repo.write("TASK.md", EVIDENCE)
            repo.commit("implement")
            repo.git("checkout", "-b", "feature")
            repo.write("feature.txt", "feature\n")
            repo.commit("feature")
            repo.git("checkout", "agent/test/job")
            result = repo.git("merge", "--no-ff", "feature", "-m", "merge feature")
            self.assertEqual(result.returncode, 0, result.stderr)
            contract_result = contract.evaluate({"repo": str(repo.root)}, spec_for(base))
            self.assertIn("no_merge_commits", contract_result["failed_checks"])

    def test_secret_bearing_path_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo, base = make_repo(Path(directory))
            repo.write("TASK.md", EVIDENCE)
            repo.write(".env", "TOKEN=not-a-real-token\n")
            repo.commit("implement")
            result = contract.evaluate({"repo": str(repo.root)}, spec_for(base))
            self.assertIn("sensitive_paths", result["failed_checks"])

    def test_out_of_scope_path_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo, base = make_repo(Path(directory))
            repo.write("TASK.md", EVIDENCE)
            repo.write("unrelated/file.txt", "scope\n")
            repo.commit("implement")
            spec = spec_for(base, allowed_paths=["TASK.md", "src/"])
            result = contract.evaluate({"repo": str(repo.root)}, spec)
            self.assertIn("scoped_paths", result["failed_checks"])

    def test_parse_dirty_paths_preserves_truncated_first_path(self) -> None:
        # The historical whole-output .strip() removed the leading status column
        # of the first porcelain record.
        stripped = "M skills/README.md\n M other/file.md\n?? new-dir/"
        self.assertEqual(
            contract.parse_dirty_paths(stripped),
            ["skills/README.md", "other/file.md", "new-dir/"],
        )
        nuls = " M skills/README.md\0 M other/file.md\0?? new-dir/\0"
        self.assertEqual(
            contract.parse_dirty_paths(nuls),
            ["skills/README.md", "other/file.md", "new-dir/"],
        )
        renamed = "R  old/name.md -> new/name.md"
        self.assertEqual(contract.parse_dirty_paths(renamed), ["new/name.md"])

    def test_git_snapshot_records_first_dirty_path_exactly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo, _base = make_repo(Path(directory))
            repo.write("skills/README.md", "baseline\n")
            repo.commit("track skills readme")
            repo.write("skills/README.md", "modified\n")
            snapshot = runner.git_snapshot(repo.root)
            self.assertEqual(
                contract.parse_dirty_paths(snapshot["status"]), ["skills/README.md"]
            )

    def test_initialized_evidence_template_fails_until_filled(self) -> None:
        job_id = "20261101T000000Z-evidence-test-abcdef12"
        with tempfile.TemporaryDirectory() as directory:
            repo, base = make_repo(Path(directory))
            repo.write("TASK.md", structured_evidence(job_id, fill=False))
            repo.commit("unfilled evidence")
            job = {"id": job_id, "repo": str(repo.root), "evidence_initialized": True}
            result = contract.evaluate(job, spec_for(base))
            self.assertEqual(result["state"], "FAILED")
            self.assertEqual(checks_by_id(result)["evidence_identity"]["status"], "verified")
            for check in evidence.REQUIRED_FIELDS:
                self.assertIn(check, result["failed_checks"])

    def test_filled_job_specific_evidence_verifies(self) -> None:
        job_id = "20261101T000000Z-evidence-test-abcdef12"
        with tempfile.TemporaryDirectory() as directory:
            repo, base = make_repo(Path(directory))
            repo.write("TASK.md", structured_evidence(job_id))
            repo.commit("filled evidence")
            job = {"id": job_id, "repo": str(repo.root), "evidence_initialized": True}
            result = contract.evaluate(job, spec_for(base))
            self.assertEqual(result["state"], "VERIFIED", result)
            identity = checks_by_id(result)["evidence_identity"]
            self.assertEqual(identity["status"], "verified")

    def test_evidence_for_another_job_fails(self) -> None:
        job_id = "20261101T000000Z-evidence-test-abcdef12"
        with tempfile.TemporaryDirectory() as directory:
            repo, base = make_repo(Path(directory))
            repo.write(
                "TASK.md",
                structured_evidence(
                    job_id, job_id_line="20261101T000000Z-another-job-ffffffff"
                ),
            )
            repo.commit("wrong job evidence")
            job = {"id": job_id, "repo": str(repo.root), "evidence_initialized": True}
            result = contract.evaluate(job, spec_for(base))
            self.assertEqual(result["state"], "FAILED")
            self.assertIn("evidence_identity", result["failed_checks"])
            for check in evidence.REQUIRED_FIELDS:
                self.assertIn(check, result["failed_checks"])

    def test_removing_initialized_evidence_block_fails(self) -> None:
        job_id = "20261101T000000Z-evidence-test-abcdef12"
        with tempfile.TemporaryDirectory() as directory:
            repo, base = make_repo(Path(directory))
            repo.write("TASK.md", EVIDENCE)
            repo.commit("free text evidence")
            job = {"id": job_id, "repo": str(repo.root), "evidence_initialized": True}
            result = contract.evaluate(job, spec_for(base))
            self.assertEqual(result["state"], "FAILED")
            self.assertIn("evidence_identity", result["failed_checks"])
            for check in evidence.REQUIRED_FIELDS:
                self.assertIn(check, result["failed_checks"])

    def test_legacy_truncated_owner_path_is_repaired_narrowly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo, base = make_repo(Path(directory))
            repo.write("TASK.md", EVIDENCE)
            repo.write("skills/README.md", "baseline\n")
            repo.commit("evidence and tracked skill")
            repo.write("skills/README.md", "owner change\n")
            spec = spec_for(
                base,
                allowed_dirty_paths=["kills/README.md"],
                forbidden_paths=["kills/README.md"],
            )
            result = contract.evaluate({"repo": str(repo.root)}, spec)
            self.assertNotIn("clean_tree", result["failed_checks"])
            self.assertEqual(
                result["dirty_path_repairs"],
                [
                    {
                        "field": "allowed_dirty_paths",
                        "from": "kills/README.md",
                        "to": "skills/README.md",
                    },
                    {
                        "field": "forbidden_paths",
                        "from": "kills/README.md",
                        "to": "skills/README.md",
                    },
                ],
            )

    def test_new_contract_does_not_repair_unexpected_paths(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo, base = make_repo(Path(directory))
            repo.write("TASK.md", EVIDENCE)
            repo.write("skills/README.md", "baseline\n")
            repo.commit("evidence and tracked skill")
            repo.write("skills/README.md", "unexpected\n")
            spec = spec_for(
                base,
                allowed_dirty_paths=["kills/README.md"],
                dirty_paths_parser=contract.DIRTY_PATHS_PARSER_VERSION,
            )
            result = contract.evaluate({"repo": str(repo.root)}, spec)
            self.assertIn("clean_tree", result["failed_checks"])
            self.assertEqual(result["dirty_path_repairs"], [])

    def test_evaluate_state_contract_failure_and_pending(self) -> None:
        job = {
            "acceptance_criteria": [
                {"id": "AC1", "kind": "command", "required": True}
            ]
        }
        verification = {"AC1": {"verified": True}}
        state, blocker = runner.evaluate_state(
            job, 0, [], verification, {"state": "FAILED"}
        )
        self.assertEqual(state, "FAILED")
        self.assertIn("completion contract", blocker or "")
        state, blocker = runner.evaluate_state(
            job, 0, [], verification, {"state": "PENDING"}
        )
        self.assertEqual(state, "BLOCKED")
        self.assertIn("owner authorization", blocker or "")

    def test_load_contract_rejects_invalid_shape(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "contract.json"
            path.write_text(json.dumps({"version": 1, "allowed_paths": "docs/"}), encoding="utf-8")
            with self.assertRaises(contract.ContractError):
                contract.load_contract(path)
            path.write_text("{not json", encoding="utf-8")
            with self.assertRaises(contract.ContractError):
                contract.load_contract(path)

    def test_default_contract_requires_every_mandatory_check(self) -> None:
        spec = contract.build_default_contract(
            branch="agent/test/job",
            base_sha="a" * 40,
            dirty_paths=["owner/file.md", "owner/"],
            authorization={"push": True},
        )
        for check in contract.MANDATORY_REQUIREMENTS:
            self.assertTrue(spec["require"][check], check)
        self.assertEqual(spec["evidence_files"], ["TASK.md"])
        self.assertEqual(spec["allowed_dirty_paths"], ["owner/file.md", "owner/"])
        self.assertEqual(spec["forbidden_paths"], ["owner/file.md", "owner/"])
        self.assertTrue(spec["authorization"]["push"])

    def test_prepare_contract_never_disables_mandatory_checks(self) -> None:
        weak = {
            "version": 1,
            "evidence_files": ["TASK.md"],
            "require": {"push": False},
        }
        with self.assertRaises(contract.ContractError):
            contract.prepare_contract(
                weak,
                branch="agent/test/job",
                base_sha="a" * 40,
            )

    def test_prepare_contract_keeps_explicit_constraints_and_adds_defaults(self) -> None:
        explicit = {
            "version": 1,
            "evidence_files": ["TASK.md", "STATUS.json"],
            "allowed_paths": ["src/"],
            "require": {"commit": True},
        }
        prepared, source = contract.prepare_contract(
            explicit,
            branch="agent/test/job",
            base_sha="a" * 40,
            dirty_paths=["owner/file.md"],
        )
        self.assertEqual(source, "file")
        self.assertEqual(prepared["evidence_files"], ["TASK.md", "STATUS.json"])
        self.assertEqual(prepared["allowed_paths"], ["src/"])
        self.assertIn("owner/file.md", prepared["allowed_dirty_paths"])
        for check in contract.MANDATORY_REQUIREMENTS:
            self.assertTrue(prepared["require"][check], check)

    def test_load_contract_rejects_weakening(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "contract.json"
            path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "evidence_files": ["TASK.md"],
                        "require": {"capability_harvest": False},
                    }
                ),
                encoding="utf-8",
            )
            with self.assertRaises(contract.ContractError):
                contract.load_contract(path)
            path.write_text(
                json.dumps({"version": 1, "evidence_files": []}),
                encoding="utf-8",
            )
            with self.assertRaises(contract.ContractError):
                contract.load_contract(path)

    def test_legacy_job_without_contract_stays_backwards_compatible(self) -> None:
        job = {
            "acceptance_criteria": [
                {"id": "AC1", "kind": "command", "required": True}
            ]
        }
        verification = {"AC1": {"verified": True}}
        self.assertIsNone(runner.verify_contract(job))
        state, blocker = runner.evaluate_state(job, 0, [], verification, None)
        self.assertEqual(state, "SUCCESS", blocker)

    def test_new_job_without_evaluated_contract_cannot_succeed(self) -> None:
        job = {
            "acceptance_criteria": [
                {"id": "AC1", "kind": "command", "required": True}
            ],
            "completion_contract_required": True,
        }
        verification = {"AC1": {"verified": True}}
        state, blocker = runner.evaluate_state(job, 0, [], verification, None)
        self.assertEqual(state, "FAILED")
        self.assertIn("mandatory completion contract", blocker or "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
