#!/usr/bin/env python3
"""Regression tests for the canonical project-scoped delivery policy."""

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

from devjob import contract, project_policy  # noqa: E402

EVIDENCE = """# Task

- Skills loaded: `skills/shared/workflow-v3-completion-contract/SKILL.md`,
  freshness last checked 2026-11-01.
- Documentation read: `WORKFLOW.md`, `PROJECT-REGISTRY.md`.
- Capability harvest: project-specific; no reusable update needed.
- Documentation update: updated the delivery-policy runbook.
"""


class GitRepo:
    def __init__(self, root: Path, *, branch: str = "agent/test/job") -> None:
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
        self.write("TASK.md", EVIDENCE)
        self.write("README.md", "baseline\n")
        self.commit("baseline")

    def git(self, *args: str) -> subprocess.CompletedProcess[str]:
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

    def add_remote(self, name: str, url: str) -> None:
        result = self.git("remote", "add", name, url)
        if result.returncode != 0:
            raise AssertionError(result.stderr)


def registry_text(rows: list[dict]) -> str:
    lines = [
        "# Project registry",
        "",
        "## Registered projects",
        "",
        "| ID | Platform | Verified local path | Project-level `AGENTS.md` | Canonical context | Central report root | Git remote | GitHub repository | Development branch pattern | Automatic push |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| `{project_id}` | Qortal | `{repo}` | No | Pending | `{docs}/` | "
            "`{remote}` | `{github}` | `{pattern}` | `{push}` |".format(
                project_id=row["project_id"],
                repo=row["repo"],
                docs=row.get("docs", row["repo"]),
                remote=row.get("remote", "origin"),
                github=row.get("github", "test/project"),
                pattern=row.get("pattern", "agent/*"),
                push=row.get("push", "yes"),
            )
        )
    return "\n".join(lines) + "\n"


def push_remote(repo: GitRepo, remote: str, branch: str = "agent/test/job") -> None:
    result = repo.git("push", "-u", remote, branch)
    if result.returncode != 0:
        raise AssertionError(result.stderr)


class DeliveryPolicyResolutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="delivery-policy-")
        self.root = Path(self.temporary.name)
        self.registry = self.root / "PROJECT-REGISTRY.md"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_multiple_projects_resolve_their_own_remote(self) -> None:
        first = GitRepo(self.root / "first")
        first.add_remote("origin", "https://github.com/owner/first.git")
        second = GitRepo(self.root / "second")
        second.add_remote("upstream", "git@github.com:owner/second.git")
        self.registry.write_text(
            registry_text(
                [
                    {
                        "project_id": "demo/first",
                        "repo": first.root,
                        "remote": "origin",
                        "github": "owner/first",
                    },
                    {
                        "project_id": "demo/second",
                        "repo": second.root,
                        "remote": "upstream",
                        "github": "owner/second",
                    },
                ]
            ),
            encoding="utf-8",
        )
        one = project_policy.resolve(first.root, registry_path=self.registry)
        two = project_policy.resolve(second.root, registry_path=self.registry)
        self.assertEqual(one.remote, "origin")
        self.assertEqual(one.github_repository, "owner/first")
        self.assertEqual(two.remote, "upstream")
        self.assertEqual(two.github_repository, "owner/second")

    def test_unregistered_repository_is_rejected(self) -> None:
        first = GitRepo(self.root / "first")
        first.add_remote("origin", "https://github.com/owner/first.git")
        self.registry.write_text(
            registry_text(
                [{"project_id": "demo/first", "repo": first.root, "github": "owner/first"}]
            ),
            encoding="utf-8",
        )
        other = GitRepo(self.root / "other")
        other.add_remote("origin", "https://github.com/owner/other.git")
        with self.assertRaises(project_policy.DeliveryPolicyError) as context:
            project_policy.resolve(other.root, registry_path=self.registry)
        self.assertIn("not a registered project", str(context.exception))

    def test_missing_policy_columns_are_rejected(self) -> None:
        repo = GitRepo(self.root / "repo")
        repo.add_remote("origin", "https://github.com/owner/repo.git")
        self.registry.write_text(
            "# Project registry\n\n## Registered projects\n\n"
            "| ID | Platform | Verified local path | Project-level `AGENTS.md` | Canonical context | Central report root |\n"
            "| --- | --- | --- | --- | --- | --- |\n"
            f"| `demo/repo` | Qortal | `{repo.root}` | No | Pending | `{repo.root}/` |\n",
            encoding="utf-8",
        )
        with self.assertRaises(project_policy.DeliveryPolicyError) as context:
            project_policy.resolve(repo.root, registry_path=self.registry)
        self.assertIn("delivery policy", str(context.exception))

    def test_missing_remote_is_rejected(self) -> None:
        repo = GitRepo(self.root / "repo")
        repo.add_remote("origin", "https://github.com/owner/repo.git")
        self.registry.write_text(
            registry_text(
                [
                    {
                        "project_id": "demo/repo",
                        "repo": repo.root,
                        "remote": "upstream",
                        "github": "owner/repo",
                    }
                ]
            ),
            encoding="utf-8",
        )
        with self.assertRaises(project_policy.DeliveryPolicyError) as context:
            project_policy.resolve(repo.root, registry_path=self.registry)
        self.assertIn("not configured", str(context.exception))

    def test_remote_repository_mismatch_is_rejected(self) -> None:
        repo = GitRepo(self.root / "repo")
        repo.add_remote("origin", "https://github.com/owner/different.git")
        self.registry.write_text(
            registry_text(
                [{"project_id": "demo/repo", "repo": repo.root, "github": "owner/expected"}]
            ),
            encoding="utf-8",
        )
        with self.assertRaises(project_policy.DeliveryPolicyError) as context:
            project_policy.resolve(repo.root, registry_path=self.registry)
        self.assertIn("expected owner/expected", str(context.exception))

    def test_non_github_remote_is_rejected(self) -> None:
        repo = GitRepo(self.root / "repo")
        repo.add_remote("origin", str(self.root / "local.git"))
        self.registry.write_text(
            registry_text([{"project_id": "demo/repo", "repo": repo.root}]),
            encoding="utf-8",
        )
        with self.assertRaises(project_policy.DeliveryPolicyError) as context:
            project_policy.resolve(repo.root, registry_path=self.registry)
        self.assertIn("GitHub repository", str(context.exception))

    def test_invalid_branch_pattern_is_rejected(self) -> None:
        repo = GitRepo(self.root / "repo")
        repo.add_remote("origin", "https://github.com/owner/repo.git")
        self.registry.write_text(
            registry_text(
                [
                    {
                        "project_id": "demo/repo",
                        "repo": repo.root,
                        "github": "owner/repo",
                        "pattern": "main*",
                    }
                ]
            ),
            encoding="utf-8",
        )
        with self.assertRaises(project_policy.DeliveryPolicyError) as context:
            project_policy.resolve(repo.root, registry_path=self.registry)
        self.assertIn("agent/*", str(context.exception))

    def test_ambiguous_repository_rows_are_rejected(self) -> None:
        repo = GitRepo(self.root / "repo")
        repo.add_remote("origin", "https://github.com/owner/repo.git")
        self.registry.write_text(
            registry_text(
                [
                    {"project_id": "demo/one", "repo": repo.root, "github": "owner/repo"},
                    {"project_id": "demo/two", "repo": repo.root, "github": "owner/repo"},
                ]
            ),
            encoding="utf-8",
        )
        with self.assertRaises(project_policy.DeliveryPolicyError) as context:
            project_policy.resolve(repo.root, registry_path=self.registry)
        self.assertIn("multiple registered projects", str(context.exception))

    def test_automatic_push_only_for_agent_branches(self) -> None:
        repo = GitRepo(self.root / "repo")
        repo.add_remote("origin", "https://github.com/owner/repo.git")
        self.registry.write_text(
            registry_text(
                [{"project_id": "demo/repo", "repo": repo.root, "github": "owner/repo"}]
            ),
            encoding="utf-8",
        )
        policy = project_policy.resolve(repo.root, registry_path=self.registry)
        self.assertTrue(policy.automatic_push_allowed("agent/feature"))
        self.assertTrue(policy.matches_branch("agent/project/task"))
        self.assertFalse(policy.automatic_push_allowed("main"))
        self.assertFalse(policy.automatic_push_allowed("feature/foo"))
        self.assertFalse(policy.automatic_push_allowed("HEAD"))

    def test_automatic_push_can_be_disabled(self) -> None:
        repo = GitRepo(self.root / "repo")
        repo.add_remote("origin", "https://github.com/owner/repo.git")
        self.registry.write_text(
            registry_text(
                [
                    {
                        "project_id": "demo/repo",
                        "repo": repo.root,
                        "github": "owner/repo",
                        "push": "no",
                    }
                ]
            ),
            encoding="utf-8",
        )
        policy = project_policy.resolve(repo.root, registry_path=self.registry)
        self.assertFalse(policy.automatic_push_allowed("agent/feature"))
        self.assertTrue(policy.matches_branch("agent/feature"))


class DeliveryContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="delivery-contract-")
        self.root = Path(self.temporary.name)
        self.repo = GitRepo(self.root / "repo")
        self.bare = self.root / "remote.git"
        subprocess.run(
            ["git", "init", "--bare", str(self.bare)],
            check=True,
            env=self.repo.env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        # Keep the configured remote GitHub-shaped while routing all Git
        # transport to the disposable bare repository.
        self.repo.add_remote("origin", "https://github.com/owner/repo.git")
        self.repo.git("config", f"url.{self.bare}.insteadOf", "https://github.com/owner/repo.git")
        self.registry = self.root / "PROJECT-REGISTRY.md"
        self.registry.write_text(
            registry_text(
                [{"project_id": "demo/repo", "repo": self.repo.root, "github": "owner/repo"}]
            ),
            encoding="utf-8",
        )
        self.policy = project_policy.resolve(self.repo.root, registry_path=self.registry)
        self.base = self.repo.git("rev-parse", "HEAD").stdout.strip()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def spec(self, *, push: bool = True, require_push: bool = True) -> dict:
        spec = {
            "version": 1,
            "branch": "agent/test/job",
            "base_sha": self.base,
            "remote": self.policy.remote,
            "evidence_files": ["TASK.md"],
            "require": {
                "skill_discovery": True,
                "freshness": True,
                "documentation_loading": True,
                "capability_harvest": True,
                "documentation_updates": True,
                "clean_tree": True,
                "commit": True,
                "no_merge_commits": True,
                "push": require_push,
            },
            "authorization": {"push": push},
            "delivery_policy": self.policy.snapshot(),
        }
        return spec

    def test_verified_policy_and_matching_remote(self) -> None:
        self.repo.write("delivery.txt", "done\n")
        self.repo.commit("deliver")
        push_remote(self.repo, "origin")
        result = contract.evaluate({"repo": str(self.repo.root)}, self.spec())
        self.assertEqual(result["state"], "VERIFIED", result)
        checks = {item["id"]: item for item in result["checks"]}
        self.assertEqual(checks["delivery_policy"]["status"], "verified")
        self.assertEqual(checks["branch_policy"]["status"], "verified")
        self.assertEqual(checks["remote_sha"]["status"], "verified")

    def test_contract_remote_must_match_policy(self) -> None:
        self.repo.write("delivery.txt", "done\n")
        self.repo.commit("deliver")
        spec = self.spec(push=False, require_push=False)
        spec["remote"] = "dev-control-plane"
        result = contract.evaluate({"repo": str(self.repo.root)}, spec)
        self.assertIn("delivery_policy", result["failed_checks"])

    def test_unauthorized_branch_does_not_get_automatic_push(self) -> None:
        self.repo.git("checkout", "-b", "feature/not-agent")
        self.repo.write("delivery.txt", "done\n")
        self.repo.commit("deliver")
        spec = self.spec(push=False)
        spec["branch"] = "feature/not-agent"
        result = contract.evaluate({"repo": str(self.repo.root)}, spec)
        self.assertEqual(result["state"], "PENDING", result)
        self.assertIn("branch_policy", result["pending_checks"])
        self.assertIn("remote_sha", result["pending_checks"])

    def test_explicit_push_on_unauthorized_branch_fails(self) -> None:
        self.repo.git("checkout", "-b", "main")
        self.repo.write("delivery.txt", "done\n")
        self.repo.commit("deliver")
        spec = self.spec(push=True)
        spec["branch"] = "main"
        spec["authorization"]["protected_branch"] = True
        result = contract.evaluate({"repo": str(self.repo.root)}, spec)
        self.assertIn("branch_policy", result["failed_checks"])

    def test_failed_push_reports_remote_sha_failure(self) -> None:
        self.repo.write("delivery.txt", "done\n")
        self.repo.commit("deliver")
        # Do not push: the remote branch is absent.
        result = contract.evaluate({"repo": str(self.repo.root)}, self.spec())
        self.assertIn("remote_sha", result["failed_checks"])

    def test_prepare_contract_rejects_conflicting_remote(self) -> None:
        spec = self.spec(push=False, require_push=True)
        spec["remote"] = "dev-control-plane"
        with self.assertRaises(contract.ContractError):
            contract.prepare_contract(
                spec,
                branch="agent/test/job",
                base_sha=self.base,
                remote=self.policy.remote,
                delivery_policy=self.policy,
                require_delivery_policy=True,
            )

    def test_prepare_contract_requires_policy_for_new_jobs(self) -> None:
        with self.assertRaises(contract.ContractError):
            contract.prepare_contract(
                None,
                branch="agent/test/job",
                base_sha=self.base,
                require_delivery_policy=True,
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
