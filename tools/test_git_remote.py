#!/usr/bin/env python3
"""Regressions for the shared non-interactive GitHub remote probe.

The fake SSH transport below behaves like a real SSH connection for Git's
upload-pack/receive-pack protocol while mapping GitHub to a local bare
repository. That proves the real admission and completion paths, including the
environment they build, without network access or private credentials.
"""

from __future__ import annotations

import os
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from devjob import branch_prepare, contract, git_remote, project_policy  # noqa: E402

FAKE_SSH = r'''#!/usr/bin/env python3
import os
import re
import shutil
import sys

host = sys.argv[-2] if len(sys.argv) >= 2 else ""
command = sys.argv[-1] if sys.argv else ""
mode = os.environ.get("FAKE_SSH_MODE", "ok")
fail_once = os.environ.get("FAKE_SSH_FAIL_ONCE")
if mode == "auth":
    print("git@github.com: Permission denied (publickey).", file=sys.stderr)
    sys.exit(255)
if mode == "hostkey":
    print("Host key verification failed.", file=sys.stderr)
    sys.exit(255)
if mode == "transient":
    print("ssh: connect to host github.com port 22: Connection timed out", file=sys.stderr)
    sys.exit(255)
if mode == "transient-reset":
    print(
        "Connection reset by 192.0.2.4 port 22\\n"
        "fatal: Could not read from remote repository.\\n\\n"
        "Please make sure you have the correct access rights\\n"
        "and the repository exists.",
        file=sys.stderr,
    )
    sys.exit(255)
if mode in {"transient-once", "transient-reset-once"} and fail_once and not os.path.exists(fail_once):
    open(fail_once, "w", encoding="utf-8").write("failed once\\n")
    if mode == "transient-reset-once":
        print(
            "Connection reset by 192.0.2.4 port 22\\n"
            "fatal: Could not read from remote repository.",
            file=sys.stderr,
        )
    else:
        print("ssh: connect to host github.com port 22: Connection timed out", file=sys.stderr)
    sys.exit(255)
match = re.match(r"(git-upload-pack|git-receive-pack) '([^']+)'", command)
if not match:
    print("fake-ssh: unexpected command " + command, file=sys.stderr)
    sys.exit(255)
bare = os.environ.get("FAKE_SSH_BARE", "")
tool = shutil.which(match.group(1))
if not tool:
    print("fake-ssh: tool not found", file=sys.stderr)
    sys.exit(255)
os.execv(tool, [tool, bare])
'''


class FakeSshRepo:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.bare = root / "remote.git"
        self.work = root / "work"
        self.script = root / "fake-ssh.py"
        self.script.write_text(FAKE_SSH, encoding="utf-8")
        os.chmod(self.script, 0o700)
        self.env = os.environ.copy()
        self.env.update(
            {
                "GIT_AUTHOR_NAME": "Test",
                "GIT_AUTHOR_EMAIL": "test@example.invalid",
                "GIT_COMMITTER_NAME": "Test",
                "GIT_COMMITTER_EMAIL": "test@example.invalid",
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_TERMINAL_PROMPT": "0",
                "GIT_SSH_COMMAND": str(self.script),
                "FAKE_SSH_BARE": str(self.bare),
            }
        )
        self.git(None, "init", "--bare", "-b", "main", str(self.bare))
        self.git(None, "init", "-b", "main", str(self.work))
        (self.work / "README.md").write_text("baseline\n", encoding="utf-8")
        self.git(self.work, "add", "-A")
        self.git(self.work, "commit", "-m", "baseline")
        self.git(
            self.work,
            "remote",
            "add",
            "origin",
            "git@github.com:owner/repo.git",
        )
        self.git(self.work, "push", "origin", "main")

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

    def head(self) -> str:
        return self.git(self.work, "rev-parse", "HEAD").stdout.strip()


class GitRemoteProbeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.repo = FakeSshRepo(Path(self.temp.name))

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_valid_ssh_remote_passes_admission_probe(self) -> None:
        with mock.patch.dict(os.environ, self.repo.env, clear=False):
            probe = git_remote.probe_remote(
                self.repo.work, "origin", expected_repository="owner/repo"
            )
        self.assertEqual(probe.github_repository, "owner/repo")
        self.assertEqual(probe.heads.get("main"), self.repo.head())

    def test_broken_authentication_fails_safely(self) -> None:
        self.repo.env["FAKE_SSH_MODE"] = "auth"
        with mock.patch.dict(os.environ, self.repo.env, clear=False):
            with self.assertRaises(git_remote.RemoteProbeError) as context:
                git_remote.probe_remote(
                    self.repo.work,
                    "origin",
                    expected_repository="owner/repo",
                    sleep=lambda _seconds: None,
                )
        self.assertEqual(context.exception.kind, "auth")
        message = str(context.exception)
        self.assertIn("GitHub delivery is unavailable", message)
        self.assertNotIn("git@github.com", message)
        self.assertNotIn("owner/repo", message)

    def test_transient_transport_failure_is_retried_once(self) -> None:
        self.repo.env["FAKE_SSH_MODE"] = "transient-once"
        self.repo.env["FAKE_SSH_FAIL_ONCE"] = str(Path(self.temp.name) / "once")
        with mock.patch.dict(os.environ, self.repo.env, clear=False):
            probe = git_remote.probe_remote(
                self.repo.work,
                "origin",
                expected_repository="owner/repo",
                sleep=lambda _seconds: None,
            )
        self.assertEqual(probe.heads.get("main"), self.repo.head())

    def test_connection_reset_with_generic_git_wording_is_not_auth(self) -> None:
        """A reset must not be reported as an authentication failure.

        Git appends ``fatal: Could not read from remote repository`` to both an
        authentication failure and a network reset. The historical Telegram
        admission failure showed the auth wording even though the same SSH key
        worked interactively.
        """

        self.repo.env["FAKE_SSH_MODE"] = "transient-reset"
        with mock.patch.dict(os.environ, self.repo.env, clear=False):
            with self.assertRaises(git_remote.RemoteProbeError) as context:
                git_remote.probe_remote(
                    self.repo.work,
                    "origin",
                    expected_repository="owner/repo",
                    sleep=lambda _seconds: None,
                )
        self.assertEqual(context.exception.kind, "transport")
        self.assertIn("transport", str(context.exception))
        self.assertNotIn("authentication", str(context.exception))

    def test_connection_reset_is_retried_through_real_admission_probe(self) -> None:
        self.repo.env["FAKE_SSH_MODE"] = "transient-reset-once"
        self.repo.env["FAKE_SSH_FAIL_ONCE"] = str(Path(self.temp.name) / "reset-once")
        with mock.patch.dict(os.environ, self.repo.env, clear=False):
            prepared = branch_prepare.prepare(
                self.repo.work,
                project_policy.resolve(
                    self.repo.work,
                    registry_path=self._registry_for_admission(),
                ),
                job_id="20261102T000000Z-reset-probe",
                lock=False,
            )
        self.assertTrue(prepared.created)
        self.assertTrue(prepared.branch.startswith("agent/"))

    def _registry_for_admission(self) -> Path:
        registry = Path(self.temp.name) / "PROJECT-REGISTRY.md"
        registry.write_text(
            "# Registry\n\n## Registered projects\n\n"
            "| ID | Platform | Verified local path | Project-level `AGENTS.md` | "
            "Canonical context | Central report root | Git remote | GitHub repository | "
            "Development branch pattern | Automatic push |\n"
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
            f"| `owner/repo` | Generic | `{self.repo.work}` | No | - | - | "
            "`origin` | `owner/repo` | `agent/*` | `yes` |\n",
            encoding="utf-8",
        )
        return registry

    def test_host_key_failure_is_not_reported_as_authentication(self) -> None:
        self.repo.env["FAKE_SSH_MODE"] = "hostkey"
        with mock.patch.dict(os.environ, self.repo.env, clear=False):
            with self.assertRaises(git_remote.RemoteProbeError) as context:
                git_remote.probe_remote(
                    self.repo.work,
                    "origin",
                    expected_repository="owner/repo",
                    sleep=lambda _seconds: None,
                )
        self.assertEqual(context.exception.kind, "host_key")
        self.assertIn("host key", str(context.exception).lower())
        self.assertIn("not disabled", str(context.exception))

    def test_git_timeout_uses_timeout_kind(self) -> None:
        completed = subprocess.CompletedProcess(["git"], 124, "", "git ls-remote timed out after 60 seconds")
        with mock.patch("devjob.git_remote.subprocess.run", return_value=completed):
            result = git_remote.run_git(self.repo.work, "ls-remote", "--heads", "origin")
        self.assertEqual(result.returncode, 124)
        self.assertEqual(git_remote.classify_failure(result.stderr, result.returncode), "timeout")

    def test_completion_remote_sha_uses_the_same_environment(self) -> None:
        self.repo.git(self.repo.work, "checkout", "-b", "agent/owner/job")
        (self.repo.work / "work.txt").write_text("work\n", encoding="utf-8")
        self.repo.git(self.repo.work, "add", "-A")
        self.repo.git(self.repo.work, "commit", "-m", "work")
        self.repo.git(self.repo.work, "push", "origin", "agent/owner/job")
        spec = {
            "version": 1,
            "branch": "agent/owner/job",
            "remote": "origin",
            "delivery_policy": {
                "project_id": "owner/repo",
                "remote": "origin",
                "github_repository": "owner/repo",
                "branch_pattern": "agent/*",
                "automatic_push": True,
            },
            "authorization": {"push": True},
        }
        with mock.patch.dict(os.environ, self.repo.env, clear=False):
            check = contract._push_check(
                self.repo.work, spec, "agent/owner/job", {"push": True}
            )
        self.assertEqual(check["status"], "verified", check)

    def test_completion_remote_sha_failure_is_bounded_and_safe(self) -> None:
        self.repo.env["FAKE_SSH_MODE"] = "auth"
        spec = {
            "version": 1,
            "branch": "agent/owner/job",
            "remote": "origin",
            "delivery_policy": {
                "project_id": "owner/repo",
                "remote": "origin",
                "github_repository": "owner/repo",
                "branch_pattern": "agent/*",
                "automatic_push": True,
            },
            "authorization": {"push": True},
        }
        with mock.patch.dict(os.environ, self.repo.env, clear=False):
            check = contract._push_check(
                self.repo.work, spec, "agent/owner/job", {"push": True}
            )
        self.assertEqual(check["status"], "failed")
        self.assertIn("auth failure", check["detail"])


class BranchPreparationSshTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.repo = FakeSshRepo(Path(self.temp.name))
        self.registry = Path(self.temp.name) / "PROJECT-REGISTRY.md"
        self.registry.write_text(
            "# Registry\n\n## Registered projects\n\n"
            "| ID | Platform | Verified local path | Project-level `AGENTS.md` | "
            "Canonical context | Central report root | Git remote | GitHub repository | "
            "Development branch pattern | Automatic push |\n"
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n"
            f"| `owner/repo` | Generic | `{self.repo.work}` | No | - | - | "
            "`origin` | `owner/repo` | `agent/*` | `yes` |\n",
            encoding="utf-8",
        )
        self.policy = project_policy.resolve(self.repo.work, registry_path=self.registry)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_admission_uses_real_ssh_probe_and_creates_agent_branch(self) -> None:
        with mock.patch.dict(os.environ, self.repo.env, clear=False):
            prepared = branch_prepare.prepare(
                self.repo.work, self.policy, job_id="20261102T000000Z-test-job"
            )
        self.assertTrue(prepared.created)
        self.assertTrue(prepared.branch.startswith("agent/"))
        self.assertEqual(self.repo.git(self.repo.work, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip(), prepared.branch)


if __name__ == "__main__":
    unittest.main()
