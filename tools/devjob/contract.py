"""Executable Workflow v3 completion contract.

A completion contract turns task-start discipline and delivery rules into
machine-checked evidence instead of prompt advice.  It is deliberately
conservative: a missing evidence file, an uncommitted change, a protected branch,
a missing push authorization or a remote SHA that differs from local HEAD is
reported as failed or pending, never inferred as success.

The contract never grants authority.  Push, protected-branch, merge, deploy,
QDN, wallet and destructive-operation permissions remain explicit fields that
the owner must set for the job.  This module only verifies that the recorded
authorization matches the observed Git state.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Iterable

PROTECTED_BRANCH_NAMES = {"main", "master", "trunk", "release", "production"}
DEFAULT_REMOTE = "dev-control-plane"
MAX_EVIDENCE_BYTES = 1_500_000

# Paths that must never be committed by an autonomous job.  This is a
# path-level guard; the repository Git hook performs the content-level secret
# scan before a commit is accepted.
DENY_PATH_PATTERNS = (
    re.compile(r"(^|/)\.env(\.|$)"),
    re.compile(r"(^|/)id_(rsa|ed25519|ecdsa|dsa)(\.|$)"),
    re.compile(r"\.(pem|key|p12|pfx|jks|kdbx)$", re.IGNORECASE),
    re.compile(r"(^|/)(wallet|wallets|seed|seeds|mnemonic|keystore)(/|\.|$)", re.IGNORECASE),
    re.compile(r"(^|/)credentials?(\.|/|$)", re.IGNORECASE),
    re.compile(r"(^|/)secrets?(\.|/|$)", re.IGNORECASE),
)

DIFF_SECRET_PATTERNS = (
    ("private-key block", re.compile(r"-----BEGIN (?:[A-Z0-9]+ )?PRIVATE KEY-----")),
    ("GitHub token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{60,})\b")),
    ("AWS access key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("OpenAI-style key", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
    ("credential-bearing URL", re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://[^/\s:@]+:[^/\s@]+@")),
)

REQUIRED_EVIDENCE = (
    "skill_discovery",
    "freshness",
    "documentation_loading",
    "capability_harvest",
    "documentation_updates",
)

EVIDENCE_MARKERS = {
    "skill_discovery": (
        "skill",
        ("skills/", "no applicable skill", "no skill", "none applicable"),
    ),
    "freshness": (
        "fresh",
        ("last checked", "revision", "sha", "compatible", "stale"),
    ),
    "documentation_loading": (
        "doc",
        ("docs/", "documentation", "read", "workflow.md", "agents.md"),
    ),
    "capability_harvest": (
        "harvest",
        ("capability harvest", "harvest", "no harvest", "project-specific"),
    ),
    "documentation_updates": (
        "document",
        ("documentation update", "docs updated", "updated docs", "no documentation", "documentation: none"),
    ),
}


class ContractError(ValueError):
    """The completion contract itself is invalid."""


def load_contract(path: str | Path) -> dict:
    target = Path(path).expanduser()
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ContractError(f"cannot read completion contract {target}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ContractError(f"completion contract is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ContractError("completion contract must be a JSON object")
    validate_spec(data)
    return data


def validate_spec(spec: dict) -> None:
    if int(spec.get("version", 1)) != 1:
        raise ContractError("unsupported completion contract version")
    evidence = spec.get("evidence_files") or spec.get("evidence_file")
    if isinstance(evidence, str):
        evidence = [evidence]
    if evidence is not None and not isinstance(evidence, list):
        raise ContractError("evidence_files must be a list of paths")
    for item in evidence or []:
        if not isinstance(item, str) or not item.strip():
            raise ContractError("evidence_files entries must be non-empty strings")
    require = spec.get("require")
    if require is not None and not isinstance(require, dict):
        raise ContractError("require must be an object")
    authorization = spec.get("authorization")
    if authorization is not None and not isinstance(authorization, dict):
        raise ContractError("authorization must be an object")
    for key in ("allowed_paths", "forbidden_paths", "allowed_dirty_paths", "protected_branches"):
        value = spec.get(key)
        if value is not None and not isinstance(value, list):
            raise ContractError(f"{key} must be a list of path prefixes/branch names")


def _run_git(repo: Path, *args: str, timeout: int = 30) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return subprocess.CompletedProcess(["git", *args], 1, "", str(exc))


def _git_text(repo: Path, *args: str) -> str:
    result = _run_git(repo, *args)
    if result.returncode != 0:
        return ""
    return (result.stdout or "").strip()


def _exists_prefix(path: str, prefixes: Iterable[str]) -> bool:
    return any(path == prefix.rstrip("/") or path.startswith(prefix.rstrip("/") + "/") for prefix in prefixes)


def _read_evidence(paths: Iterable[str], repo: Path, control_plane: Path) -> tuple[str, list[str], list[str]]:
    chunks: list[str] = []
    found: list[str] = []
    missing: list[str] = []
    for raw in paths:
        candidate = Path(raw).expanduser()
        if not candidate.is_absolute():
            local = (repo / candidate).resolve()
            fallback = (control_plane / candidate).resolve()
            candidate = local if local.exists() else fallback
        try:
            resolved = candidate.resolve()
            resolved.relative_to(repo.resolve())
        except (OSError, ValueError):
            # Absolute paths under the control plane or the workspace are
            # allowed; arbitrary absolute paths are not trusted as evidence.
            try:
                resolved = candidate.resolve()
                if not str(resolved).startswith(str(control_plane.resolve())):
                    missing.append(raw)
                    continue
            except OSError:
                missing.append(raw)
                continue
        if not resolved.is_file():
            missing.append(raw)
            continue
        try:
            data = resolved.read_bytes()[:MAX_EVIDENCE_BYTES]
            chunks.append(data.decode("utf-8", "replace"))
            found.append(str(resolved))
        except OSError:
            missing.append(raw)
    return "\n".join(chunks).lower(), found, missing


def _check_evidence(text: str, found: list[str], missing: list[str], spec: dict) -> list[dict]:
    checks: list[dict] = []
    require = spec.get("require") or {}
    if not found:
        for check_id in REQUIRED_EVIDENCE:
            if require.get(check_id, True):
                checks.append(
                    {
                        "id": check_id,
                        "label": check_id.replace("_", " "),
                        "status": "failed",
                        "severity": "failed",
                        "detail": "no readable evidence file was provided",
                    }
                )
        return checks
    if missing:
        checks.append(
            {
                "id": "evidence_files",
                "label": "evidence files present",
                "status": "failed",
                "severity": "failed",
                "detail": "missing evidence file(s): " + ", ".join(missing),
            }
        )
    for check_id in REQUIRED_EVIDENCE:
        if not require.get(check_id, True):
            checks.append(
                {
                    "id": check_id,
                    "label": check_id.replace("_", " "),
                    "status": "skipped",
                    "severity": "info",
                    "detail": "not required by contract",
                }
            )
            continue
        _needle, markers = EVIDENCE_MARKERS[check_id]
        if any(marker in text for marker in markers):
            checks.append(
                {
                    "id": check_id,
                    "label": check_id.replace("_", " "),
                    "status": "verified",
                    "severity": "info",
                    "detail": "recorded in " + ", ".join(found),
                }
            )
        else:
            checks.append(
                {
                    "id": check_id,
                    "label": check_id.replace("_", " "),
                    "status": "failed",
                    "severity": "failed",
                    "detail": "evidence file does not record " + check_id.replace("_", " "),
                }
            )
    return checks


def _branch_checks(repo: Path, spec: dict) -> tuple[list[dict], str]:
    checks: list[dict] = []
    branch = _git_text(repo, "rev-parse", "--abbrev-ref", "HEAD")
    expected = spec.get("branch")
    if expected and branch != expected:
        checks.append(
            {
                "id": "branch",
                "label": "development branch",
                "status": "failed",
                "severity": "failed",
                "detail": f"expected {expected}, found {branch or 'unknown'}",
            }
        )
    else:
        checks.append(
            {
                "id": "branch",
                "label": "development branch",
                "status": "verified",
                "severity": "info",
                "detail": branch or "detached HEAD",
            }
        )
    protected = set(PROTECTED_BRANCH_NAMES)
    protected.update(str(item) for item in spec.get("protected_branches") or [])
    authorization = spec.get("authorization") or {}
    if branch in protected and not authorization.get("protected_branch"):
        checks.append(
            {
                "id": "protected_branch",
                "label": "protected branch authorization",
                "status": "failed",
                "severity": "failed",
                "detail": f"branch {branch} is protected and no protected-branch authorization was recorded",
            }
        )
    elif branch in protected:
        checks.append(
            {
                "id": "protected_branch",
                "label": "protected branch authorization",
                "status": "verified",
                "severity": "info",
                "detail": f"branch {branch} is protected; explicit authorization recorded",
            }
        )
    return checks, branch


def _commit_checks(repo: Path, spec: dict) -> list[dict]:
    checks: list[dict] = []
    base = str(spec.get("base_sha") or "").strip()
    if not base:
        base = _git_text(repo, "rev-parse", "HEAD~1") if _run_git(repo, "rev-parse", "HEAD~1").returncode == 0 else ""
    head = _git_text(repo, "rev-parse", "HEAD")
    if not base:
        checks.append(
            {
                "id": "commit",
                "label": "scoped commit",
                "status": "failed",
                "severity": "failed",
                "detail": "no base SHA and no commit history to compare against",
            }
        )
        return checks
    ancestry = _run_git(repo, "merge-base", "--is-ancestor", base, "HEAD")
    if ancestry.returncode != 0:
        checks.append(
            {
                "id": "commit",
                "label": "scoped commit",
                "status": "failed",
                "severity": "failed",
                "detail": "base SHA is not an ancestor of HEAD",
            }
        )
        return checks
    count = _git_text(repo, "rev-list", "--count", f"{base}..HEAD")
    try:
        commit_count = int(count or "0")
    except ValueError:
        commit_count = 0
    if commit_count < 1:
        checks.append(
            {
                "id": "commit",
                "label": "scoped commit",
                "status": "failed",
                "severity": "failed",
                "detail": "no commit exists after the recorded base SHA",
            }
        )
    else:
        checks.append(
            {
                "id": "commit",
                "label": "scoped commit",
                "status": "verified",
                "severity": "info",
                "detail": f"{commit_count} commit(s) after base {base[:12]}",
            }
        )

    merges = _git_text(repo, "rev-list", "--merges", f"{base}..HEAD")
    authorization = spec.get("authorization") or {}
    if merges and not authorization.get("merge"):
        checks.append(
            {
                "id": "no_merge_commits",
                "label": "no unauthorized merge commit",
                "status": "failed",
                "severity": "failed",
                "detail": "merge commit(s) present without merge authorization",
            }
        )
    elif merges:
        checks.append(
            {
                "id": "no_merge_commits",
                "label": "no unauthorized merge commit",
                "status": "verified",
                "severity": "info",
                "detail": "merge commit(s) covered by explicit merge authorization",
            }
        )
    else:
        checks.append(
            {
                "id": "no_merge_commits",
                "label": "no unauthorized merge commit",
                "status": "verified",
                "severity": "info",
                "detail": "no merge commits",
            }
        )

    changed = [line for line in _git_text(repo, "diff", "--name-only", f"{base}..HEAD").splitlines() if line]
    allowed = [str(item) for item in spec.get("allowed_paths") or []]
    forbidden = [str(item) for item in spec.get("forbidden_paths") or []]
    out_of_scope = [path for path in changed if allowed and not _exists_prefix(path, allowed)]
    denied = [path for path in changed if _exists_prefix(path, forbidden)]
    sensitive = [path for path in changed if any(pattern.search(path) for pattern in DENY_PATH_PATTERNS)]
    if out_of_scope:
        checks.append(
            {
                "id": "scoped_paths",
                "label": "scoped changed paths",
                "status": "failed",
                "severity": "failed",
                "detail": "changed path(s) outside allowed_paths: " + ", ".join(out_of_scope[:10]),
            }
        )
    else:
        checks.append(
            {
                "id": "scoped_paths",
                "label": "scoped changed paths",
                "status": "verified",
                "severity": "info",
                "detail": f"{len(changed)} changed path(s) within the declared scope",
            }
        )
    if denied:
        checks.append(
            {
                "id": "forbidden_paths",
                "label": "forbidden paths",
                "status": "failed",
                "severity": "failed",
                "detail": "forbidden path(s) changed: " + ", ".join(denied[:10]),
            }
        )
    if sensitive:
        checks.append(
            {
                "id": "sensitive_paths",
                "label": "no secret-bearing path",
                "status": "failed",
                "severity": "failed",
                "detail": "secret-bearing path(s) committed: " + ", ".join(sensitive[:10]),
            }
        )
    else:
        checks.append(
            {
                "id": "sensitive_paths",
                "label": "no secret-bearing path",
                "status": "verified",
                "severity": "info",
                "detail": "no recognized secret-bearing path in the diff",
            }
        )

    diff = _run_git(repo, "diff", "--no-ext-diff", "--unified=0", f"{base}..HEAD")
    diff_text = diff.stdout or ""
    findings = sorted({label for label, pattern in DIFF_SECRET_PATTERNS if pattern.search(diff_text)})
    if findings:
        checks.append(
            {
                "id": "diff_secrets",
                "label": "no secret-like diff content",
                "status": "failed",
                "severity": "failed",
                # Never echo the matching value.
                "detail": "secret-like content detected: " + ", ".join(findings),
            }
        )
    else:
        checks.append(
            {
                "id": "diff_secrets",
                "label": "no secret-like diff content",
                "status": "verified",
                "severity": "info",
                "detail": "no recognized secret pattern in the diff",
            }
        )
    return checks


def _worktree_check(repo: Path, spec: dict) -> dict:
    status = _git_text(repo, "status", "--porcelain")
    allowed_dirty = [str(item) for item in spec.get("allowed_dirty_paths") or []]
    unexpected: list[str] = []
    for line in status.splitlines():
        if not line.strip():
            continue
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1].strip()
        path = path.strip('"')
        if allowed_dirty and _exists_prefix(path, allowed_dirty):
            continue
        unexpected.append(path)
    if unexpected:
        return {
            "id": "clean_tree",
            "label": "working tree committed",
            "status": "failed",
            "severity": "failed",
            "detail": "uncommitted change(s): " + ", ".join(unexpected[:10]),
        }
    return {
        "id": "clean_tree",
        "label": "working tree committed",
        "status": "verified",
        "severity": "info",
        "detail": "no uncommitted changes" + (" (declared owner paths ignored)" if allowed_dirty else ""),
    }


def _push_check(repo: Path, spec: dict, branch: str, authorization: dict) -> dict:
    remote = str(spec.get("remote") or DEFAULT_REMOTE)
    if not authorization.get("push"):
        return {
            "id": "remote_sha",
            "label": "authorized development-branch push",
            "status": "pending",
            "severity": "pending",
            "detail": "push is not authorized; handoff_sync=pending_authorization",
        }
    if not branch or branch == "HEAD":
        return {
            "id": "remote_sha",
            "label": "authorized development-branch push",
            "status": "failed",
            "severity": "failed",
            "detail": "cannot verify a detached HEAD against a remote branch",
        }
    remote_check = _run_git(repo, "remote", "get-url", remote)
    if remote_check.returncode != 0 or not (remote_check.stdout or "").strip():
        return {
            "id": "remote_sha",
            "label": "authorized development-branch push",
            "status": "failed",
            "severity": "failed",
            "detail": f"git remote {remote!r} is not configured",
        }
    result = _run_git(repo, "ls-remote", "--heads", remote, branch, timeout=45)
    if result.returncode != 0:
        return {
            "id": "remote_sha",
            "label": "authorized development-branch push",
            "status": "failed",
            "severity": "failed",
            "detail": f"could not read remote {remote} branch {branch}",
        }
    fields = (result.stdout or "").split()
    remote_sha = fields[0] if fields else ""
    local_sha = _git_text(repo, "rev-parse", "HEAD")
    if not remote_sha:
        return {
            "id": "remote_sha",
            "label": "authorized development-branch push",
            "status": "failed",
            "severity": "failed",
            "detail": f"remote {remote} has no branch {branch}",
        }
    if remote_sha != local_sha:
        return {
            "id": "remote_sha",
            "label": "authorized development-branch push",
            "status": "failed",
            "severity": "failed",
            "detail": f"remote SHA {remote_sha[:12]} differs from local HEAD {local_sha[:12]}",
        }
    return {
        "id": "remote_sha",
        "label": "authorized development-branch push",
        "status": "verified",
        "severity": "info",
        "detail": f"{remote}/{branch} = {remote_sha[:12]} (matches local HEAD)",
    }


def evaluate(job: dict, spec: dict | None, repo: Path | None = None) -> dict:
    """Evaluate a contract against the job's repository and evidence."""

    if not spec:
        return {"configured": False, "state": "NOT_CONFIGURED", "checks": []}
    validate_spec(spec)
    repo_path = Path(repo or job.get("repo") or ".").expanduser().resolve()
    control_plane = Path(__file__).resolve().parents[2]
    evidence = spec.get("evidence_files") or spec.get("evidence_file") or []
    if isinstance(evidence, str):
        evidence = [evidence]
    text, found, missing = _read_evidence(evidence, repo_path, control_plane)
    checks = _check_evidence(text, found, missing, spec)
    branch_checks, branch = _branch_checks(repo_path, spec)
    checks.extend(branch_checks)
    checks.append(_worktree_check(repo_path, spec))

    require = spec.get("require") or {}
    authorization = spec.get("authorization") or {}
    if require.get("commit", True):
        checks.extend(_commit_checks(repo_path, spec))
    if require.get("push", True):
        checks.append(_push_check(repo_path, spec, branch, authorization))
    elif authorization.get("push"):
        checks.append(
            {
                "id": "remote_sha",
                "label": "authorized development-branch push",
                "status": "skipped",
                "severity": "info",
                "detail": "push verification disabled by contract",
            }
        )

    statuses = {check["status"] for check in checks}
    if "failed" in statuses:
        state = "FAILED"
    elif "pending" in statuses:
        state = "PENDING"
    else:
        state = "VERIFIED"
    failed = [check["id"] for check in checks if check["status"] == "failed"]
    pending = [check["id"] for check in checks if check["status"] == "pending"]
    return {
        "configured": True,
        "state": state,
        "branch": branch,
        "evidence_files": found,
        "missing_evidence_files": missing,
        "failed_checks": failed,
        "pending_checks": pending,
        "checks": checks,
        "evaluated_at": None,
    }
