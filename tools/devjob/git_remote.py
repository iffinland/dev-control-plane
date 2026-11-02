"""Canonical non-interactive Git remote access for Workflow v3.

Both admission (``branch_prepare``) and the completion contract read the GitHub
remote. They must do so with the *same* environment rules, otherwise admission
can succeed while the post-run remote-SHA check fails, or a transient network
glitch is reported as an authentication failure.

The helpers here deliberately keep the owner's existing credentials and SSH
configuration. They never copy, print or add credentials, never rewrite a
remote URL and never disable host-key verification. They only:

* forbid terminal/GUI prompting;
* request SSH BatchMode when the owner has not configured an SSH command;
* retry once for a clearly transient transport error;
* classify failures without leaking the remote URL or raw Git stderr.
"""

from __future__ import annotations

import os
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from . import project_policy

DEFAULT_TIMEOUT_SECONDS = 60
DEFAULT_ATTEMPTS = 2
RETRY_DELAY_SECONDS = 0.5

_SSH_URL_RE = re.compile(r"^(?:ssh://|[^/@\s]+@[^/:\s]+:)")
# A transport reset can make Git append the generic "Could not read from remote
# repository" wording. That phrase is deliberately *not* an authentication
# marker on its own: checking it first turned a transient reset into a false
# "GitHub authentication failed" admission refusal with no retry.
_TRANSIENT_RE = re.compile(
    r"connection (?:timed out|reset|refused|closed)"
    r"|could not resolve host"
    r"|network is unreachable"
    r"|temporary failure in name resolution"
    r"|operation timed out"
    r"|timed out after"
    r"|early eof"
    r"|the remote end hung up"
    r"|kex_exchange_identification"
    r"|rpc failed"
    r"|ssl (?:connection|read) .*failed",
    re.IGNORECASE,
)
_TIMEOUT_RE = re.compile(r"\btimed out after\b", re.IGNORECASE)
_HOST_KEY_RE = re.compile(
    r"host key verification failed"
    r"|no (?:matching )?host key is known"
    r"|remote host identification has changed",
    re.IGNORECASE,
)
_AUTH_RE = re.compile(
    r"permission denied"
    r"|publickey"
    r"|authentication failed"
    r"|access denied"
    r"|invalid username or password"
    r"|terminal prompts disabled"
    r"|support for password authentication was removed",
    re.IGNORECASE,
)


class RemoteProbeError(RuntimeError):
    """A GitHub remote could not be inspected safely."""

    def __init__(self, kind: str, message: str) -> None:
        self.kind = kind
        super().__init__(message)


@dataclass(frozen=True)
class RemoteProbe:
    remote: str
    remote_url: str
    github_repository: str
    heads: dict[str, str]


def is_ssh_url(url: str) -> bool:
    return bool(_SSH_URL_RE.match(str(url or "").strip()))


def _configured_ssh_command(repo: Path | None) -> str:
    if repo is None:
        return ""
    result = run_git(repo, "config", "--get", "core.sshCommand", timeout=15)
    if result.returncode != 0:
        return ""
    return (result.stdout or "").strip()


def noninteractive_env(
    remote_url: str,
    *,
    repo: Path | None = None,
    base: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """Return a safe, inherited environment for one non-interactive Git call."""

    env = dict(os.environ if base is None else base)
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GCM_INTERACTIVE"] = "Never"
    if is_ssh_url(remote_url):
        # An explicitly configured command (environment or repository config)
        # remains authoritative; we only add BatchMode for the default SSH.
        if not env.get("GIT_SSH_COMMAND") and not _configured_ssh_command(repo):
            env["GIT_SSH_COMMAND"] = "ssh -oBatchMode=yes -o ConnectTimeout=30"
    return env


def run_git(
    repo: Path | None,
    *args: str,
    env: Mapping[str, str] | None = None,
    timeout: int = 30,
) -> subprocess.CompletedProcess:
    command = ["git"]
    if repo is not None:
        command.extend(["-C", str(repo)])
    command.extend(args)
    try:
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=dict(env) if env is not None else None,
        )
    except subprocess.TimeoutExpired as exc:
        # Preserve the conventional timeout return code so classification and
        # the owner-facing message do not describe a timeout as transport.
        return subprocess.CompletedProcess(
            command,
            124,
            "",
            f"git {' '.join(args)} timed out after {timeout} seconds",
        )
    except OSError as exc:
        return subprocess.CompletedProcess(command, 1, "", str(exc))


def _remote_url(repo: Path, remote: str) -> str:
    result = run_git(repo, "config", "--get", f"remote.{remote}.url")
    if result.returncode != 0:
        return ""
    return (result.stdout or "").strip()


def classify_failure(stderr: str, returncode: int | None = None) -> str:
    """Classify a failed Git remote operation without exposing its output.

    Concrete transport/timeout evidence wins over the generic "could not read
    from remote repository" suffix, because Git adds that suffix after a reset
    or timeout as well as after a genuine authentication failure. Only an
    explicit authentication marker (``Permission denied (publickey)``,
    ``Authentication failed`` and similar) is classified as ``auth``.
    """

    text = str(stderr or "")
    if returncode == 124 or _TIMEOUT_RE.search(text):
        return "timeout"
    if _TRANSIENT_RE.search(text):
        return "transport"
    if _HOST_KEY_RE.search(text):
        return "host_key"
    if _AUTH_RE.search(text):
        return "auth"
    return "transport"


def _failure_message(kind: str, remote: str) -> str:
    if kind == "auth":
        return (
            f"GitHub delivery is unavailable: non-interactive authentication for "
            f"remote {remote!r} failed. Configure valid HTTPS credentials or an "
            "existing SSH key/agent, then retry. The job was not started and no "
            "branch was changed."
        )
    if kind == "host_key":
        return (
            f"GitHub delivery is unavailable: the SSH host key for remote "
            f"{remote!r} could not be verified against the owner's known_hosts. "
            "Verify the host key through an interactive SSH session, then retry. "
            "Host-key verification was not disabled. The job was not started and "
            "no branch was changed."
        )
    if kind == "timeout":
        return (
            f"GitHub delivery is unavailable: the non-interactive transport for "
            f"remote {remote!r} timed out. Check network reachability and retry. "
            "The job was not started and no branch was changed."
        )
    return (
        f"GitHub delivery is unavailable: the non-interactive transport for "
        f"remote {remote!r} failed. Check network reachability, SSH/HTTPS "
        "credentials and host-key configuration, then retry. The job was not "
        "started and no branch was changed."
    )


def probe_remote(
    repo: str | Path,
    remote: str,
    *,
    expected_repository: str | None = None,
    attempts: int = DEFAULT_ATTEMPTS,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    sleep=time.sleep,
) -> RemoteProbe:
    """Verify remote identity and read remote heads with bounded retry."""

    path = Path(repo).expanduser().resolve()
    remote = str(remote or "").strip()
    if not remote:
        raise RemoteProbeError("identity", "the project delivery policy has no Git remote")
    url = _remote_url(path, remote)
    if not url:
        raise RemoteProbeError("identity", f"git remote {remote!r} is not configured")
    actual = project_policy.normalise_remote_url(url)
    if actual is None:
        raise RemoteProbeError(
            "identity", f"remote {remote!r} does not point at a GitHub repository"
        )
    expected = project_policy.normalise_github_repository(expected_repository)
    if expected_repository is not None and expected is None:
        raise RemoteProbeError(
            "identity", "the project delivery policy has no valid GitHub repository"
        )
    if expected is not None and actual != expected:
        raise RemoteProbeError(
            "identity",
            f"remote {remote!r} points at {actual}, expected {expected}; "
            "the project remote was not changed",
        )

    env = noninteractive_env(url, repo=path)
    tries = max(1, int(attempts))
    kind = "transport"
    for attempt in range(tries):
        result = run_git(
            path,
            "ls-remote",
            "--heads",
            remote,
            env=env,
            timeout=timeout,
        )
        if result.returncode == 0:
            heads: dict[str, str] = {}
            for line in (result.stdout or "").splitlines():
                fields = line.split()
                if len(fields) >= 2 and fields[1].startswith("refs/heads/"):
                    heads[fields[1][len("refs/heads/") :]] = fields[0]
            return RemoteProbe(
                remote=remote,
                remote_url=url,
                github_repository=actual,
                heads=heads,
            )
        kind = classify_failure(result.stderr or str(result.stderr), result.returncode)
        if kind != "transport" or attempt + 1 >= tries:
            break
        sleep(RETRY_DELAY_SECONDS)
    raise RemoteProbeError(kind, _failure_message(kind, remote))


def probe_remote_branch(
    repo: str | Path,
    remote: str,
    branch: str,
    *,
    timeout: int = 45,
) -> str | None:
    """Return the remote SHA for one branch using the canonical environment."""

    path = Path(repo).expanduser().resolve()
    url = _remote_url(path, remote)
    if not url:
        raise RemoteProbeError("identity", f"git remote {remote!r} is not configured")
    env = noninteractive_env(url, repo=path)
    result = run_git(
        path,
        "ls-remote",
        "--heads",
        remote,
        branch,
        env=env,
        timeout=timeout,
    )
    if result.returncode != 0:
        kind = classify_failure(result.stderr or "", result.returncode)
        raise RemoteProbeError(
            kind,
            f"could not read remote {remote!r} branch {branch!r} "
            f"({kind} failure)",
        )
    fields = (result.stdout or "").split()
    return fields[0] if fields else None
