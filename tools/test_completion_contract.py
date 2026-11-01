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

from devjob import contract, runner  # noqa: E402

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


def checks_by_id(result: dict) -> dict:
    return {item["id"]: item for item in result.get("checks") or []}


class CompletionContractTests(unittest.TestCase):
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

    def test_protected_branch_without_authorization_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo, base = make_repo(Path(directory), branch="main")
            repo.write("TASK.md", EVIDENCE)
            repo.commit("implement")
            spec = spec_for(base, branch="main")
            result = contract.evaluate({"repo": str(repo.root)}, spec)
            self.assertIn("protected_branch", result["failed_checks"])

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
