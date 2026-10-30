#!/usr/bin/env python3
"""Disposable-repository tests for the Git security hooks.

All repositories are created under a temporary directory. The canonical
workspace repositories are never committed to, staged, or pushed by this test.

Test fixtures construct sensitive-looking values at runtime so this file itself
does not contain a literal public/private address, token or credential URL.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path


TOOLS = Path(__file__).resolve().parent
CONTROL_PLANE = TOOLS.parent
DOCS = CONTROL_PLANE.parent / "docs"
DRIVER = TOOLS / "git_hooks.py"
VALIDATOR = TOOLS / "validate_security.py"
EXCEPTIONS = TOOLS / "security-exceptions.json"
HISTORICAL = CONTROL_PLANE / "reports/2026-09-13-phase-2-qortal-node-b-tunnel.md"
WRAPPER = CONTROL_PLANE / ".githooks/pre-commit"

PUBLIC_IP = ".".join(("93", "184", "216", "34"))
PRIVATE_IP = ".".join(("10", "20", "30", "40"))
TOKEN = "ghp_" + "b" * 36
CREDENTIAL_URL = "https://" + "user" + ":" + "pass" + "@" + "example.invalid/path"
ZERO = "0" * 40


def run(
    args: list[str],
    cwd: Path,
    input_text: str | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        input=input_text,
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )


def redact(text: str) -> str:
    for value in (PUBLIC_IP, PRIVATE_IP, TOKEN, CREDENTIAL_URL):
        text = text.replace(value, "[redacted]")
    return text


def git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    result = run(["git", *args], repo)
    if result.returncode != 0:
        raise RuntimeError(redact(result.stderr or result.stdout))
    return result


def init_repo(root: Path) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    repo = root / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "user.name", "Security Test")
    git(repo, "config", "user.email", "security-test@example.invalid")
    git(repo, "config", "commit.gpgsign", "false")
    return repo


def write(repo: Path, relative: str, text: str) -> None:
    path = repo / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def commit(repo: Path, message: str) -> str:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)
    return git(repo, "rev-parse", "HEAD").stdout.strip()


def empty_exceptions(root: Path) -> Path:
    path = root / "empty-exceptions.json"
    path.write_text('{"exceptions": []}\n', encoding="utf-8")
    return path


def pre_commit(repo: Path, exceptions: Path) -> subprocess.CompletedProcess[str]:
    return run(
        [sys.executable, str(DRIVER), "pre-commit", "--repo", str(repo), "--exceptions", str(exceptions)],
        repo,
    )


def pre_push(
    repo: Path,
    exceptions: Path,
    local_sha: str,
    remote_sha: str,
) -> subprocess.CompletedProcess[str]:
    payload = f"refs/heads/main {local_sha} refs/heads/main {remote_sha}\n"
    return run(
        [sys.executable, str(DRIVER), "pre-push", "--repo", str(repo), "--exceptions", str(exceptions)],
        repo,
        input_text=payload,
    )


def hook_env() -> dict[str, str]:
    env = dict(os.environ)
    env["CONTROL_PLANE_ROOT"] = str(CONTROL_PLANE)
    env["GIT_TERMINAL_PROMPT"] = "0"
    return env


def wrapper_pre_push(
    wrapper: Path,
    repo: Path,
    local_sha: str,
    remote_sha: str,
) -> subprocess.CompletedProcess[str]:
    payload = f"refs/heads/main {local_sha} refs/heads/main {remote_sha}\n"
    return run(
        [str(wrapper), "origin", "https://example.invalid/repo.git"],
        repo,
        input_text=payload,
        env=hook_env(),
    )


def git_push_with_hooks(
    repo: Path,
    hooks_dir: Path,
) -> subprocess.CompletedProcess[str]:
    git(repo, "config", "core.hooksPath", str(hooks_dir))
    return run(["git", "push", "origin", "main"], repo, env=hook_env())


def historical_ip() -> str:
    text = HISTORICAL.read_text(encoding="utf-8")
    match = re.search(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])", text)
    if not match:
        raise RuntimeError("historical fixture address not found")
    return match.group(0)


def check(name: str, condition: bool, failures: list[str], detail: str = "") -> None:
    if condition:
        print(f"PASS: {name}")
    else:
        print(f"FAIL: {name}{(' — ' + detail) if detail else ''}")
        failures.append(name)


def main() -> int:
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="git-security-tests-") as temporary:
        root = Path(temporary)
        empty = empty_exceptions(root)

        # Clean staged content.
        repo = init_repo(root / "clean")
        write(repo, "docs/example.md", "loopback 127.0.0.1:24991\nrfc5737 192.0.2.10\n")
        git(repo, "add", "docs/example.md")
        result = pre_commit(repo, empty)
        check("clean staged changes pass", result.returncode == 0, failures, redact(result.stderr))

        # Public IP.
        repo = init_repo(root / "public")
        write(repo, "host.md", f"host {PUBLIC_IP}\n")
        git(repo, "add", "host.md")
        result = pre_commit(repo, empty)
        check("new public IP is blocked", result.returncode == 1, failures, redact(result.stderr))

        # Private infrastructure IP.
        repo = init_repo(root / "private")
        write(repo, "host.md", f"internal {PRIVATE_IP}\n")
        git(repo, "add", "host.md")
        result = pre_commit(repo, empty)
        check("new private IP is blocked", result.returncode == 1, failures, redact(result.stderr))

        # Token and credential URL.
        repo = init_repo(root / "secret")
        write(repo, "secret.md", f"token {TOKEN}\nurl {CREDENTIAL_URL}\n")
        git(repo, "add", "secret.md")
        result = pre_commit(repo, empty)
        check("new token or credential URL is blocked", result.returncode == 1, failures, redact(result.stderr))

        # Exact staged content, not the working tree.
        repo = init_repo(root / "staged")
        write(repo, "file.md", "clean staged content\n")
        git(repo, "add", "file.md")
        write(repo, "file.md", f"working tree only {PUBLIC_IP}\n")
        result = pre_commit(repo, empty)
        check("unstaged working-tree secret does not block", result.returncode == 0, failures, redact(result.stderr))
        git(repo, "add", "file.md")
        result = pre_commit(repo, empty)
        check("staged version of the same secret blocks", result.returncode == 1, failures, redact(result.stderr))

        # Historical exception unchanged.
        repo = init_repo(root / "historical")
        write(repo, "reports/2026-09-13-phase-2-qortal-node-b-tunnel.md", HISTORICAL.read_text(encoding="utf-8"))
        git(repo, "add", "reports/2026-09-13-phase-2-qortal-node-b-tunnel.md")
        result = pre_commit(repo, EXCEPTIONS)
        check("unchanged historical exception passes", result.returncode == 0, failures, redact(result.stderr))

        # Additional finding in the excepted file.
        repo = init_repo(root / "historical-extra")
        historical_text = HISTORICAL.read_text(encoding="utf-8")
        write(
            repo,
            "reports/2026-09-13-phase-2-qortal-node-b-tunnel.md",
            historical_text + f"\nnew host {PUBLIC_IP}\n",
        )
        git(repo, "add", "reports/2026-09-13-phase-2-qortal-node-b-tunnel.md")
        result = pre_commit(repo, EXCEPTIONS)
        check("additional IP in the exception file is blocked", result.returncode == 1, failures, redact(result.stderr))

        # Same historical address in another file.
        repo = init_repo(root / "historical-copy")
        write(repo, "other.md", f"copied host {historical_ip()}\n")
        git(repo, "add", "other.md")
        result = pre_commit(repo, EXCEPTIONS)
        check("same historical address in another file is blocked", result.returncode == 1, failures, redact(result.stderr))

        # Pre-push catches a secret added and then deleted.
        repo = init_repo(root / "push-deleted")
        write(repo, "base.md", "clean\n")
        base = commit(repo, "base")
        write(repo, "secret.md", f"token {TOKEN}\n")
        commit(repo, "add secret")
        git(repo, "rm", "-q", "secret.md")
        final = commit(repo, "delete secret")
        result = pre_push(repo, empty, final, base)
        check("pre-push blocks a secret added then deleted", result.returncode == 1, failures, redact(result.stderr))

        # Pre-push clean outgoing commits.
        repo = init_repo(root / "push-clean")
        write(repo, "base.md", "clean\n")
        base = commit(repo, "base")
        write(repo, "next.md", "still clean 127.0.0.1\n")
        final = commit(repo, "next")
        result = pre_push(repo, empty, final, base)
        check("clean outgoing commits pass pre-push", result.returncode == 0, failures, redact(result.stderr))

        # Pre-push historical exception on a full-history push.
        repo = init_repo(root / "push-historical")
        write(repo, "reports/2026-09-13-phase-2-qortal-node-b-tunnel.md", HISTORICAL.read_text(encoding="utf-8"))
        final = commit(repo, "historical report")
        result = pre_push(repo, EXCEPTIONS, final, ZERO)
        check("pre-push unchanged historical exception passes", result.returncode == 0, failures, redact(result.stderr))

        # Pre-push same historical address in another file.
        repo = init_repo(root / "push-historical-copy")
        write(repo, "reports/2026-09-13-phase-2-qortal-node-b-tunnel.md", HISTORICAL.read_text(encoding="utf-8"))
        base = commit(repo, "historical report")
        write(repo, "other.md", f"copied host {historical_ip()}\n")
        final = commit(repo, "copy historical host")
        result = pre_push(repo, EXCEPTIONS, final, base)
        check("pre-push blocks historical address in another file", result.returncode == 1, failures, redact(result.stderr))

        # Pre-push blocks a credential in an outgoing commit message.
        repo = init_repo(root / "push-message")
        write(repo, "base.md", "clean\n")
        base = commit(repo, "base")
        write(repo, "next.md", "clean\n")
        final = commit(repo, f"leak {PUBLIC_IP}")
        result = pre_push(repo, empty, final, base)
        check("pre-push blocks a secret in a commit message", result.returncode == 1, failures, redact(result.stderr))

        # Pre-push wrappers must accept the two positional arguments Git supplies.
        hook_dirs = [("control-plane", CONTROL_PLANE / ".githooks")]
        if (DOCS / ".githooks/pre-push").is_file():
            hook_dirs.append(("docs", DOCS / ".githooks"))

        for label, hooks_dir in hook_dirs:
            repo = init_repo(root / f"wrapper-args-{label}")
            write(repo, "base.md", "clean\n")
            base = commit(repo, "base")
            write(repo, "next.md", "clean\n")
            final = commit(repo, "next")
            result = wrapper_pre_push(hooks_dir / "pre-push", repo, final, base)
            check(
                f"{label} pre-push wrapper accepts Git remote arguments",
                result.returncode == 0,
                failures,
                redact(result.stdout + result.stderr),
            )

            repo = init_repo(root / f"wrapper-secret-{label}")
            write(repo, "base.md", "clean\n")
            base = commit(repo, "base")
            write(repo, "secret.md", f"token {TOKEN}\n")
            final = commit(repo, "add secret")
            result = wrapper_pre_push(hooks_dir / "pre-push", repo, final, base)
            check(
                f"{label} pre-push wrapper still blocks with Git remote arguments",
                result.returncode == 1,
                failures,
                redact(result.stdout + result.stderr),
            )

            repo = init_repo(root / f"real-push-clean-{label}")
            remote = root / f"real-push-clean-{label}.git"
            git(root, "init", "-q", "--bare", str(remote))
            write(repo, "base.md", "clean\n")
            commit(repo, "base")
            git(repo, "remote", "add", "origin", str(remote))
            result = git_push_with_hooks(repo, hooks_dir)
            output = result.stdout + result.stderr
            check(
                f"{label} real Git push passes the pre-push hook",
                result.returncode == 0 and "Security pre-push passed" in output,
                failures,
                redact(output),
            )

            repo = init_repo(root / f"real-push-secret-{label}")
            remote = root / f"real-push-secret-{label}.git"
            git(root, "init", "-q", "--bare", str(remote))
            write(repo, "base.md", "clean\n")
            commit(repo, "base")
            write(repo, "secret.md", f"token {TOKEN}\n")
            commit(repo, "add secret")
            git(repo, "remote", "add", "origin", str(remote))
            result = git_push_with_hooks(repo, hooks_dir)
            output = result.stdout + result.stderr
            check(
                f"{label} real Git push blocks a secret",
                result.returncode != 0 and "Security pre-push blocked" in output,
                failures,
                redact(output),
            )

        # Validator unavailable.
        repo = init_repo(root / "unavailable")
        write(repo, "clean.md", "clean\n")
        git(repo, "add", "clean.md")
        env = dict(os.environ)
        env["CONTROL_PLANE_ROOT"] = str(root / "missing-control-plane")
        result = run([str(WRAPPER)], repo, env=env)
        check("unavailable validator blocks", result.returncode != 0, failures, redact(result.stderr))

        # Validator broken at import time.
        broken = root / "broken-control-plane"
        (broken / "tools").mkdir(parents=True)
        (broken / "tools/git_hooks.py").write_text("import definitely_missing_module\n", encoding="utf-8")
        repo = init_repo(root / "broken")
        write(repo, "clean.md", "clean\n")
        git(repo, "add", "clean.md")
        env = dict(os.environ)
        env["CONTROL_PLANE_ROOT"] = str(broken)
        result = run([str(WRAPPER)], repo, env=env)
        check("broken validator blocks", result.returncode != 0, failures, redact(result.stderr))

    if failures:
        print(f"Security hook tests failed: {len(failures)} case(s)")
        return 1
    print("Security hook tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
