#!/usr/bin/env python3
"""Focused regressions for automatic Workflow v3 branch preparation."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from devjob import branch_prepare, project_policy, store  # noqa: E402


class GitRepo:
    def __init__(self, root: Path, *, branch: str = "main") -> None:
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
        self.root.mkdir(parents=True)
        self.git("init")
        self.git("checkout", "-b", branch)
        self.write("README.md", "baseline\n")
        self.commit("baseline")

    def git(self, *args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(self.root), *args],
            capture_output=True,
            text=True,
            env=env or self.env,
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
        return self.head()

    def head(self, ref: str = "HEAD") -> str:
        return self.git("rev-parse", ref).stdout.strip()

    def branch(self) -> str:
        return self.git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()

    def add_remote(self, name: str, url: str) -> None:
        result = self.git("remote", "add", name, url)
        if result.returncode != 0:
            raise AssertionError(result.stderr)


def registry_text(repo: Path, *, github: str = "owner/repo") -> str:
    return (
        "# Project registry\n\n## Registered projects\n\n"
        "| ID | Platform | Verified local path | Project-level `AGENTS.md` | Canonical context | Central report root | Git remote | GitHub repository | Development branch pattern | Automatic push |\n"
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
        f"| `demo/repo` | Qortal | `{repo}` | No | Pending | `{repo.parent / 'docs'}/` | "
        f"`origin` | `{github}` | `agent/*` | `yes` |\n"
    )


class BranchPreparationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="branch-prepare-")
        self.root = Path(self.temporary.name)
        self.state = self.root / "state"
        self.state.mkdir()
        self.previous_state = os.environ.get("DEV_CONTROL_PLANE_STATE")
        os.environ["DEV_CONTROL_PLANE_STATE"] = str(self.state)
        self.registry = self.root / "PROJECT-REGISTRY.md"
        self.bare = self.root / "remote.git"
        subprocess.run(
            ["git", "init", "--bare", str(self.bare)],
            check=True,
            env=self._env(),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def tearDown(self) -> None:
        if self.previous_state is None:
            os.environ.pop("DEV_CONTROL_PLANE_STATE", None)
        else:
            os.environ["DEV_CONTROL_PLANE_STATE"] = self.previous_state
        self.temporary.cleanup()

    def _env(self) -> dict[str, str]:
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
        return env

    def make_repo(self, *, branch: str = "main") -> GitRepo:
        repo = GitRepo(self.root / "repo", branch=branch)
        repo.add_remote("origin", "https://github.com/owner/repo.git")
        repo.git(
            "config",
            "url." + str(self.bare) + ".insteadOf",
            "https://github.com/owner/repo.git",
        )
        self.registry.write_text(registry_text(repo.root), encoding="utf-8")
        return repo

    def policy(self, repo: GitRepo) -> project_policy.DeliveryPolicy:
        return project_policy.resolve(repo.root, registry_path=self.registry)

    def push(self, repo: GitRepo, branch: str) -> None:
        result = repo.git("push", "-u", "origin", branch)
        if result.returncode != 0:
            raise AssertionError(result.stderr)

    def test_protected_main_creates_job_scoped_branch_and_is_idempotent(self) -> None:
        repo = self.make_repo(branch="main")
        self.push(repo, "main")
        main_sha = repo.head("refs/heads/main")
        policy = self.policy(repo)
        job_id = "20261102T000000Z-demo-job-12345678"
        prepared = branch_prepare.prepare(repo.root, policy, job_id=job_id)
        expected = branch_prepare.branch_name("demo/repo", job_id)
        self.assertEqual(prepared.branch, expected)
        self.assertTrue(prepared.created)
        self.assertTrue(prepared.switched)
        self.assertFalse(prepared.reused)
        self.assertEqual(repo.branch(), expected)
        self.assertEqual(repo.head("refs/heads/main"), main_sha)
        self.assertTrue(expected.startswith("agent/"))

        again = branch_prepare.prepare(repo.root, policy, job_id=job_id)
        self.assertEqual(again.branch, expected)
        self.assertFalse(again.created)
        self.assertTrue(again.reused)
        self.assertEqual(repo.branch(), expected)

    def test_clean_development_branch_is_reused(self) -> None:
        repo = self.make_repo(branch="agent/demo/current")
        head = repo.head()
        prepared = branch_prepare.prepare(
            repo.root, self.policy(repo), job_id="20261102T000000Z-demo-job-aaaaaaaa"
        )
        self.assertEqual(prepared.branch, "agent/demo/current")
        self.assertTrue(prepared.reused)
        self.assertFalse(prepared.created)
        self.assertEqual(repo.branch(), "agent/demo/current")
        self.assertEqual(repo.head(), head)

    def test_dirty_protected_main_is_isolated_without_mutation(self) -> None:
        repo = self.make_repo(branch="main")
        self.push(repo, "main")
        main_sha = repo.head("refs/heads/main")
        owner_file = repo.write("owner-notes.txt", "unowned changes\n")
        prepared = branch_prepare.prepare(
            repo.root,
            self.policy(repo),
            job_id="20261102T000000Z-demo-job-bbbbbbbb",
        )
        # The owner checkout is untouched: same branch, same commit, same file.
        self.assertEqual(repo.branch(), "main")
        self.assertEqual(repo.head("refs/heads/main"), main_sha)
        self.assertEqual(owner_file.read_text(encoding="utf-8"), "unowned changes\n")
        self.assertEqual(
            repo.git("status", "--porcelain").stdout.strip(), "?? owner-notes.txt"
        )
        # The job runs in a clean linked worktree on the prepared branch.
        self.assertTrue(prepared.created)
        self.assertTrue(prepared.branch.startswith("agent/"))
        self.assertIsNotNone(prepared.worktree)
        worktree = Path(prepared.worktree or "")
        self.assertTrue(worktree.is_dir())
        self.assertNotEqual(worktree, repo.root)
        self.assertEqual(
            repo.git("-C", str(worktree), "rev-parse", "--abbrev-ref", "HEAD").stdout.strip(),
            prepared.branch,
        )
        self.assertEqual(
            repo.git("-C", str(worktree), "status", "--porcelain").stdout.strip(), ""
        )

    def test_dirty_dry_run_plans_isolation_without_creating_anything(self) -> None:
        repo = self.make_repo(branch="main")
        self.push(repo, "main")
        repo.write("owner-notes.txt", "unowned changes\n")
        prepared = branch_prepare.prepare(
            repo.root,
            self.policy(repo),
            job_id="20261102T000000Z-demo-job-dryrun00",
            apply=False,
        )
        self.assertTrue(prepared.branch.startswith("agent/"))
        self.assertIsNotNone(prepared.worktree)
        self.assertFalse(Path(prepared.worktree or "").exists())
        self.assertEqual(repo.branch(), "main")
        self.assertTrue((repo.root / "owner-notes.txt").is_file())

    def test_detached_head_fails_closed(self) -> None:
        repo = self.make_repo(branch="main")
        self.push(repo, "main")
        repo.git("checkout", "--detach")
        with self.assertRaises(branch_prepare.BranchPreparationError) as context:
            branch_prepare.prepare(
                repo.root,
                self.policy(repo),
                job_id="20261102T000000Z-demo-job-cccccccc",
            )
        self.assertIn("detached HEAD", str(context.exception))
        self.assertEqual(repo.branch(), "HEAD")

    def test_remote_repository_mismatch_is_refused(self) -> None:
        repo = self.make_repo(branch="main")
        self.push(repo, "main")
        policy = self.policy(repo)
        repo.git("remote", "set-url", "origin", "https://github.com/owner/other.git")
        with self.assertRaises(branch_prepare.BranchPreparationError) as context:
            branch_prepare.prepare(repo.root, policy, job_id="job-mismatch")
        self.assertIn("expected owner/repo", str(context.exception))
        self.assertEqual(repo.branch(), "main")

    def test_non_interactive_authentication_failure_is_refused(self) -> None:
        repo = self.make_repo(branch="main")
        self.push(repo, "main")
        policy = self.policy(repo)
        missing = self.root / "missing-remote.git"
        repo.git("config", "--unset-all", "url." + str(self.bare) + ".insteadOf")
        repo.git(
            "config",
            "url." + str(missing) + ".insteadOf",
            "https://github.com/owner/repo.git",
        )
        with self.assertRaises(branch_prepare.BranchPreparationError) as context:
            branch_prepare.prepare(repo.root, policy, job_id="job-auth")
        message = str(context.exception)
        self.assertIn("GitHub delivery is unavailable", message)
        self.assertNotIn(str(self.bare), message)
        self.assertEqual(repo.branch(), "main")

    def test_unpushed_commit_on_main_is_preserved_and_refused(self) -> None:
        repo = self.make_repo(branch="main")
        self.push(repo, "main")
        repo.write("local-only.txt", "historical work\n")
        local_sha = repo.commit("local main commit")
        with self.assertRaises(branch_prepare.BranchPreparationError) as context:
            branch_prepare.prepare(
                repo.root,
                self.policy(repo),
                job_id="20261102T000000Z-demo-job-dddddddd",
            )
        self.assertIn("unpushed", str(context.exception))
        self.assertEqual(repo.branch(), "main")
        self.assertEqual(repo.head(), local_sha)
        self.assertEqual(repo.head("refs/heads/main"), local_sha)
        self.assertTrue((repo.root / "local-only.txt").is_file())

    def test_requested_existing_branch_is_not_reused(self) -> None:
        repo = self.make_repo(branch="agent/demo/current")
        repo.git("checkout", "-b", "agent/demo/other")
        repo.write("other.txt", "other work\n")
        repo.commit("other work")
        repo.git("checkout", "agent/demo/current")
        with self.assertRaises(branch_prepare.BranchPreparationError) as context:
            branch_prepare.prepare(
                repo.root,
                self.policy(repo),
                job_id="job-requested",
                requested_branch="agent/demo/other",
            )
        self.assertIn("already exists", str(context.exception))
        self.assertEqual(repo.branch(), "agent/demo/current")

    def test_another_active_job_blocks_preparation(self) -> None:
        repo = self.make_repo(branch="main")
        self.push(repo, "main")
        job_id = "20261102T000000Z-demo-job-active"
        store.save_job(
            {
                "id": job_id,
                "state": "RUNNING",
                "repo": str(repo.root),
                "worker_pid": os.getpid(),
                "title": "active job",
            }
        )
        with mock.patch.object(branch_prepare.store, "worker_is_alive", return_value=True):
            with self.assertRaises(branch_prepare.BranchPreparationError) as context:
                branch_prepare.prepare(
                    repo.root,
                    self.policy(repo),
                    job_id="20261102T000000Z-demo-job-new",
                )
        self.assertIn("another active job", str(context.exception))
        self.assertEqual(repo.branch(), "main")

    def test_repository_lock_serializes_concurrent_preparation(self) -> None:
        repo = self.make_repo(branch="main")
        self.push(repo, "main")
        code = (
            "import sys, time\n"
            f"sys.path.insert(0, {str(TOOLS)!r})\n"
            "from pathlib import Path\n"
            "from devjob import branch_prepare\n"
            f"with branch_prepare.repo_lock(Path({str(repo.root)!r}), timeout=2):\n"
            "    print('locked', flush=True)\n"
            "    time.sleep(2)\n"
        )
        env = os.environ.copy()
        env["DEV_CONTROL_PLANE_STATE"] = str(self.state)
        holder = subprocess.Popen(
            [sys.executable, "-c", code],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            self.assertEqual(holder.stdout.readline().strip(), "locked")
            with self.assertRaises(branch_prepare.BranchPreparationError) as context:
                branch_prepare.prepare(
                    repo.root,
                    self.policy(repo),
                    job_id="20261102T000000Z-demo-job-locked",
                    lock_timeout=0.2,
                )
            self.assertIn("already preparing", str(context.exception))
            self.assertEqual(repo.branch(), "main")
        finally:
            holder.wait(timeout=10)

    def test_resume_switches_back_to_the_recorded_branch(self) -> None:
        repo = self.make_repo(branch="main")
        self.push(repo, "main")
        recorded = "agent/demo/task"
        repo.git("checkout", "-b", recorded)
        repo.write("task.txt", "task work\n")
        repo.commit("task work")
        repo.git("checkout", "main")
        prepared = branch_prepare.prepare(
            repo.root,
            self.policy(repo),
            job_id="20261102T000000Z-demo-job-resume",
            existing_branch=recorded,
            resume=True,
        )
        self.assertEqual(prepared.branch, recorded)
        self.assertTrue(prepared.switched)
        self.assertFalse(prepared.created)
        self.assertEqual(repo.branch(), recorded)

    def test_resume_keeps_dirty_work_on_the_recorded_branch(self) -> None:
        repo = self.make_repo(branch="agent/demo/task")
        head = repo.head()
        repo.write("unfinished.txt", "uncommitted agent work\n")
        prepared = branch_prepare.prepare(
            repo.root,
            self.policy(repo),
            job_id="20261102T000000Z-demo-job-dirty-resume",
            existing_branch="agent/demo/task",
            resume=True,
        )
        self.assertEqual(prepared.branch, "agent/demo/task")
        self.assertTrue(prepared.reused)
        self.assertEqual(repo.head(), head)
        self.assertTrue((repo.root / "unfinished.txt").is_file())

    def test_resume_missing_recorded_branch_fails_closed(self) -> None:
        repo = self.make_repo(branch="main")
        self.push(repo, "main")
        with self.assertRaises(branch_prepare.BranchPreparationError) as context:
            branch_prepare.prepare(
                repo.root,
                self.policy(repo),
                job_id="20261102T000000Z-demo-job-missing-branch",
                existing_branch="agent/demo/missing",
                resume=True,
            )
        self.assertIn("no longer exists", str(context.exception))
        self.assertEqual(repo.branch(), "main")


if __name__ == "__main__":
    unittest.main(verbosity=2)
