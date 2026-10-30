#!/usr/bin/env python3
"""Shared Git security hook driver for control-plane and central docs.

The driver uses the repository's real Git plumbing:

- pre-commit reads the exact staged blobs from the index.
- pre-push inspects every path changed by outgoing commits, including blobs that
  no longer exist in the current working tree.

It imports the shared validator from this directory. Repository-specific hook
wrappers under .githooks/ only locate this driver, so validation logic is not
duplicated.

Any failure to run validation exits non-zero. The hooks never silently skip a
finding and never print raw secret or infrastructure values.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import validate_security


class HookError(RuntimeError):
    pass


def git(repo: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", "replace").strip()
        raise HookError(f"git {' '.join(args)} failed: {stderr}")
    return result.stdout


def git_optional(repo: Path, *args: str) -> bytes | None:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout


def split_z(data: bytes) -> list[str]:
    return [item for item in data.decode("utf-8", "replace").split("\0") if item]


def is_zero_sha(value: str) -> bool:
    return bool(value) and set(value) == {"0"}


def object_exists(repo: Path, revision: str) -> bool:
    return git_optional(repo, "cat-file", "-e", revision) is not None


def blob_type(repo: Path, oid: str) -> str | None:
    data = git_optional(repo, "cat-file", "-t", oid)
    return data.decode("ascii", "replace").strip() if data else None


def read_blob(repo: Path, oid: str) -> bytes:
    return git(repo, "cat-file", "blob", oid)


def load_repo_exceptions(repo: Path, explicit: Path | None) -> validate_security.ExceptionSet:
    if explicit is not None:
        if not explicit.is_file():
            raise HookError(f"exception file not found: {explicit}")
        return validate_security.load_exceptions(explicit)
    for candidate in (repo / ".security-exceptions.json", repo / "tools/security-exceptions.json"):
        if candidate.is_file():
            return validate_security.load_exceptions(candidate)
    return validate_security.EMPTY_EXCEPTIONS


def index_entries(repo: Path) -> dict[str, str]:
    data = git(repo, "ls-files", "--stage", "-z")
    entries: dict[str, str] = {}
    for item in split_z(data):
        if "\t" not in item:
            raise HookError("could not parse the Git index")
        meta, path = item.split("\t", 1)
        fields = meta.split()
        if len(fields) != 3:
            raise HookError("could not parse a Git index entry")
        mode, oid, stage = fields
        if stage != "0":
            raise HookError(f"unmerged index entry blocks security validation: {path}")
        entries[path] = oid
    return entries


def scan_blob(
    repo: Path,
    path: str,
    oid: str,
    exceptions: validate_security.ExceptionSet,
) -> list[validate_security.Finding]:
    if blob_type(repo, oid) != "blob":
        return []
    data = read_blob(repo, oid)
    if b"\0" in data:
        return []
    if len(data) > validate_security.MAX_BYTES:
        raise HookError(f"staged/pushed file exceeds security scan limit: {path}")
    text = data.decode("utf-8", "replace")
    return validate_security.scan_text(path, text, True, exceptions)


def pre_commit(repo: Path, exceptions: validate_security.ExceptionSet) -> int:
    changed = split_z(
        git(repo, "diff", "--cached", "--name-only", "-z", "--diff-filter=ACMR")
    )
    if not changed:
        print("Security pre-commit passed: no staged text changes to scan.")
        return 0

    entries = index_entries(repo)
    findings: list[validate_security.Finding] = []
    for path in changed:
        oid = entries.get(path)
        if oid is None:
            raise HookError(f"staged path is missing from the index: {path}")
        findings.extend(scan_blob(repo, path, oid, exceptions))

    if findings:
        for finding in findings:
            print(finding.render(repo))
        print(f"Security pre-commit blocked: {len(findings)} finding(s) in staged content.")
        return 1
    print(f"Security pre-commit passed: {len(changed)} staged file(s) scanned.")
    return 0


def outgoing_commits(repo: Path, local_sha: str, remote_sha: str) -> list[str]:
    if not object_exists(repo, local_sha):
        raise HookError("local push revision is not present in the repository")
    if not is_zero_sha(remote_sha) and object_exists(repo, remote_sha):
        revisions = [f"{remote_sha}..{local_sha}"]
    else:
        revisions = [local_sha]
    data = git(repo, "rev-list", "--topo-order", *revisions)
    return [item for item in data.decode("ascii", "replace").split() if item]


def changed_paths(repo: Path, commit: str) -> list[str]:
    data = git(
        repo,
        "diff-tree",
        "--root",
        "-r",
        "-m",
        "--no-commit-id",
        "--name-only",
        "-z",
        commit,
    )
    return split_z(data)


def pre_push(repo: Path, exceptions: validate_security.ExceptionSet) -> int:
    payload = sys.stdin.buffer.read()
    refs = [line.split() for line in payload.decode("utf-8", "replace").splitlines() if line.strip()]
    if not refs:
        raise HookError("pre-push received no refs; refusing to skip validation")

    findings: list[validate_security.Finding] = []
    total_commits = 0
    scanned: set[tuple[str, str]] = set()
    seen_paths: set[tuple[str, str]] = set()
    seen_commits: set[str] = set()

    for fields in refs:
        if len(fields) < 4:
            raise HookError("could not parse pre-push ref data")
        _local_ref, local_sha, _remote_ref, remote_sha = fields[:4]
        if is_zero_sha(local_sha):
            continue
        commits = outgoing_commits(repo, local_sha, remote_sha)
        for commit in commits:
            if commit in seen_commits:
                continue
            seen_commits.add(commit)
            total_commits += 1
            message = git(repo, "log", "-1", "--format=%B", commit)
            findings.extend(
                validate_security.scan_text(
                    f"commit:{commit}",
                    message.decode("utf-8", "replace"),
                    True,
                    exceptions,
                    check_name=False,
                )
            )
            for path in changed_paths(repo, commit):
                key = (commit, path)
                if key in seen_paths:
                    continue
                seen_paths.add(key)
                oid = git_optional(repo, "rev-parse", "--verify", "--quiet", f"{commit}:{path}")
                if oid is None:
                    continue
                oid_text = oid.decode("ascii", "replace").strip()
                blob_key = (path, oid_text)
                if blob_key in scanned:
                    continue
                scanned.add(blob_key)
                findings.extend(scan_blob(repo, path, oid_text, exceptions))

    if findings:
        for finding in findings:
            print(finding.render(repo))
        print(
            f"Security pre-push blocked: {len(findings)} finding(s) in "
            f"{total_commits} outgoing commit(s)."
        )
        return 1
    print(
        f"Security pre-push passed: {total_commits} outgoing commit(s), "
        f"{len(scanned)} blob(s) scanned."
    )
    return 0


def resolve_repo(value: Path | None) -> Path:
    if value is not None:
        return value.resolve()
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise HookError("not inside a Git repository")
    return Path(result.stdout.decode("utf-8", "replace").strip()).resolve()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("hook", choices=("pre-commit", "pre-push"))
    parser.add_argument("--repo", type=Path)
    parser.add_argument("--exceptions", type=Path)
    args = parser.parse_args()

    try:
        repo = resolve_repo(args.repo)
        exceptions = load_repo_exceptions(repo, args.exceptions)
        if args.hook == "pre-commit":
            return pre_commit(repo, exceptions)
        return pre_push(repo, exceptions)
    except HookError as error:
        print(f"Security hook blocked: {error}", file=sys.stderr)
        return 1
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"Security hook blocked: validation could not run: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
