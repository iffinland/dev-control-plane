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

import copy
import fnmatch
import json
import re
import subprocess
from pathlib import Path
from typing import Iterable

from . import evidence as evidence_module
from . import project_policy
from .store import job_dir

PROTECTED_BRANCH_NAMES = set(project_policy.PROTECTED_BRANCHES)
# There is deliberately no global fallback remote. A new job must resolve its
# remote from a validated project delivery policy.
DEFAULT_REMOTE = None
DEFAULT_EVIDENCE_FILES = ("TASK.md",)
MAX_EVIDENCE_BYTES = 1_500_000
# New contracts use NUL-separated porcelain output. Older contracts lack this
# marker and may contain the historical one-character path truncation.
DIRTY_PATHS_PARSER_VERSION = "porcelain-v1-z"
LEGACY_DIRTY_PARSER_REPAIR = "one-character-truncation-repaired"

# These checks are not configurable for a new Workflow v3 job.  An explicit
# contract file may add constraints (more evidence, narrower paths, extra
# forbidden paths), but it may never turn a mandatory delivery check off.
MANDATORY_REQUIREMENTS = (
    "skill_discovery",
    "freshness",
    "documentation_loading",
    "capability_harvest",
    "documentation_updates",
    "clean_tree",
    "commit",
    "no_merge_commits",
    "push",
)

AUTHORIZATION_KEYS = (
    "push",
    "protected_branch",
    "merge",
    "deploy",
    "qdn_write",
    "wallet_transaction",
    "destructive",
)

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


def load_contract(path: str | Path, *, enforce_policy: bool = True) -> dict:
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
    if enforce_policy:
        ensure_mandatory(data)
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
    for key, value in (require or {}).items():
        if not isinstance(key, str) or not isinstance(value, bool):
            raise ContractError("require entries must be boolean check flags")
    authorization = spec.get("authorization")
    if authorization is not None and not isinstance(authorization, dict):
        raise ContractError("authorization must be an object")
    for key, value in (authorization or {}).items():
        if not isinstance(key, str) or not isinstance(value, bool):
            raise ContractError("authorization entries must be boolean flags")
    for key in ("allowed_paths", "forbidden_paths", "allowed_dirty_paths", "protected_branches"):
        value = spec.get(key)
        if value is not None and not isinstance(value, list):
            raise ContractError(f"{key} must be a list of path prefixes/branch names")
    delivery = spec.get("delivery_policy")
    if delivery is not None:
        if not isinstance(delivery, dict):
            raise ContractError("delivery_policy must be an object")
        for key in ("project_id", "github_repository", "branch_pattern"):
            value = delivery.get(key)
            if value is not None and not isinstance(value, str):
                raise ContractError(f"delivery_policy.{key} must be a string")
        if delivery.get("automatic_push") is not None and not isinstance(
            delivery.get("automatic_push"), bool
        ):
            raise ContractError("delivery_policy.automatic_push must be boolean")
        remote = delivery.get("remote")
        if remote is not None and not isinstance(remote, str):
            raise ContractError("delivery_policy.remote must be a string")


def ensure_mandatory(spec: dict) -> None:
    """Reject an explicit contract that disables a mandatory delivery check."""

    require = spec.get("require") or {}
    weakened = [key for key in MANDATORY_REQUIREMENTS if require.get(key) is False]
    if weakened:
        raise ContractError(
            "completion contract may not disable mandatory checks: " + ", ".join(weakened)
        )
    evidence = spec.get("evidence_files", spec.get("evidence_file"))
    if evidence == []:
        raise ContractError("completion contract may not remove task-start evidence files")


def parse_dirty_paths(status_text: str) -> list[str]:
    """Return normalized paths from ``git status --porcelain`` output.

    Accepts both NUL-separated (``-z``) and newline-separated records.  The
    porcelain v1 format always starts each record with two status columns and a
    space.  Older callers passed output that had been ``.strip()``-ed as a whole,
    which removed the leading status space from the first line and caused its
    first path character to be dropped (``skills/README.md`` became
    ``kills/README.md``).  Handle that truncated first record explicitly rather
    than applying a fixed ``line[3:]`` slice.
    """

    text = str(status_text or "")
    if not text:
        return []
    records = text.split("\0") if "\0" in text else text.splitlines()
    paths: list[str] = []
    for record in records:
        record = record.rstrip("\r\n")
        if not record.strip():
            continue
        if len(record) >= 3 and record[2] == " ":
            # Normal porcelain v1: XY<space>PATH.
            path = record[3:]
        elif len(record) >= 2 and record[1] == " ":
            # A whole-output strip removed the leading status column.
            path = record[2:]
        elif len(record) >= 3:
            path = record[3:]
        else:
            path = record
        if " -> " in path:
            path = path.split(" -> ", 1)[1].strip()
        path = path.strip().strip('"')
        if path and path not in paths:
            paths.append(path)
    return paths


def _authorization_value(value: object) -> bool:
    return bool(value)


def _policy_snapshot(delivery_policy: object) -> dict | None:
    if delivery_policy is None:
        return None
    if isinstance(delivery_policy, project_policy.DeliveryPolicy):
        return delivery_policy.snapshot()
    if isinstance(delivery_policy, dict):
        return copy.deepcopy(delivery_policy)
    raise ContractError("delivery_policy must be a validated policy object or mapping")


def build_default_contract(
    *,
    branch: str | None,
    base_sha: str | None,
    dirty_paths: Iterable[str] | None = None,
    remote: str | None = DEFAULT_REMOTE,
    evidence_files: Iterable[str] | None = None,
    allowed_paths: Iterable[str] | None = None,
    authorization: dict | None = None,
    delivery_policy: object | None = None,
) -> dict:
    """Build the mandatory contract applied to a new Workflow v3 job."""

    dirty = [str(item) for item in dirty_paths or [] if str(item).strip()]
    evidence = [str(item) for item in evidence_files or DEFAULT_EVIDENCE_FILES if str(item).strip()]
    scope = [str(item) for item in allowed_paths or [] if str(item).strip()]
    auth = {key: False for key in AUTHORIZATION_KEYS}
    for key, value in (authorization or {}).items():
        if key in auth:
            auth[key] = _authorization_value(value)
    snapshot = _policy_snapshot(delivery_policy)
    policy_remote = (snapshot or {}).get("remote") if snapshot else None
    contract = {
        "version": 1,
        "branch": branch or None,
        "base_sha": base_sha or None,
        "remote": remote or policy_remote or None,
        "evidence_files": evidence,
        "allowed_paths": scope,
        # Pre-existing owner changes are preserved, not staged or committed.
        # They are also forbidden so a job cannot silently absorb them.
        "forbidden_paths": dirty,
        "allowed_dirty_paths": dirty,
        "require": {key: True for key in MANDATORY_REQUIREMENTS},
        "authorization": auth,
        "dirty_paths_parser": DIRTY_PATHS_PARSER_VERSION,
    }
    if snapshot is not None:
        contract["delivery_policy"] = snapshot
    return contract


def prepare_contract(
    spec: dict | None,
    *,
    branch: str | None,
    base_sha: str | None,
    dirty_paths: Iterable[str] | None = None,
    remote: str | None = DEFAULT_REMOTE,
    evidence_files: Iterable[str] | None = None,
    allowed_paths: Iterable[str] | None = None,
    authorization: dict | None = None,
    delivery_policy: object | None = None,
    require_delivery_policy: bool = False,
) -> tuple[dict, str]:
    """Normalize a default or explicit contract without weakening it.

    Returns ``(spec, source)`` where source is ``default`` or ``file``. When a
    validated project policy is supplied it always wins over an omitted or
    conflicting explicit remote; conflicting policy snapshots are rejected.
    """

    snapshot = _policy_snapshot(delivery_policy)
    policy_remote = (snapshot or {}).get("remote") if snapshot else None
    if require_delivery_policy and snapshot is None:
        raise ContractError(
            "a new Workflow v3 job requires a validated project delivery policy"
        )
    if spec is None:
        return (
            build_default_contract(
                branch=branch,
                base_sha=base_sha,
                dirty_paths=dirty_paths,
                remote=remote or policy_remote,
                evidence_files=evidence_files,
                allowed_paths=allowed_paths,
                authorization=authorization,
                delivery_policy=snapshot,
            ),
            "default",
        )
    if not isinstance(spec, dict):
        raise ContractError("completion contract must be a JSON object")
    validate_spec(spec)
    ensure_mandatory(spec)
    prepared = copy.deepcopy(spec)
    prepared.setdefault("version", 1)
    prepared.setdefault("dirty_paths_parser", DIRTY_PATHS_PARSER_VERSION)
    if prepared.get("version") != 1:
        raise ContractError("unsupported completion contract version")
    if snapshot is not None:
        declared = prepared.get("delivery_policy")
        if isinstance(declared, dict):
            for key in (
                "project_id",
                "remote",
                "github_repository",
                "branch_pattern",
                "automatic_push",
            ):
                if key in declared and declared.get(key) != snapshot.get(key):
                    raise ContractError(
                        f"explicit delivery_policy.{key} conflicts with the validated "
                        "project policy"
                    )
        prepared["delivery_policy"] = snapshot
        explicit_remote = prepared.get("remote")
        if explicit_remote and policy_remote and str(explicit_remote) != str(policy_remote):
            raise ContractError(
                f"explicit remote {explicit_remote!r} conflicts with the validated "
                f"project remote {policy_remote!r}"
            )
        prepared["remote"] = policy_remote
    if not prepared.get("branch"):
        prepared["branch"] = branch or None
    if not prepared.get("base_sha"):
        prepared["base_sha"] = base_sha or None
    if not prepared.get("remote"):
        prepared["remote"] = remote or policy_remote or None
    if prepared.get("evidence_files") is None and prepared.get("evidence_file") is None:
        prepared["evidence_files"] = [
            str(item) for item in evidence_files or DEFAULT_EVIDENCE_FILES if str(item).strip()
        ]
    if prepared.get("evidence_file") is not None and prepared.get("evidence_files") is None:
        value = prepared.pop("evidence_file")
        prepared["evidence_files"] = [value] if isinstance(value, str) else list(value)
    if prepared.get("allowed_paths") is None and allowed_paths:
        prepared["allowed_paths"] = [str(item) for item in allowed_paths if str(item).strip()]
    dirty = [str(item) for item in dirty_paths or [] if str(item).strip()]
    if dirty:
        declared_dirty = [str(item) for item in prepared.get("allowed_dirty_paths") or []]
        prepared["allowed_dirty_paths"] = list(dict.fromkeys([*declared_dirty, *dirty]))
    require = dict(prepared.get("require") or {})
    for key in MANDATORY_REQUIREMENTS:
        require[key] = True
    prepared["require"] = require
    auth = {key: False for key in AUTHORIZATION_KEYS}
    for key, value in (prepared.get("authorization") or {}).items():
        if key in auth:
            auth[key] = _authorization_value(value)
    for key, value in (authorization or {}).items():
        if key in auth and value:
            # CLI flags may grant an action explicitly; they never revoke a
            # grant that the owner put in the contract file.
            auth[key] = True
    prepared["authorization"] = auth
    return prepared, "file"


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


def _actual_dirty_paths(repo: Path) -> list[str] | None:
    result = _run_git(repo, "status", "--porcelain=v1", "-z", "--no-renames")
    if result.returncode != 0:
        return None
    return parse_dirty_paths(result.stdout or "")


def repair_legacy_dirty_paths(spec: dict, repo: Path) -> tuple[dict, list[dict]]:
    """Repair a known pre-fix path truncation without widening the contract.

    Jobs created before the NUL-safe parser may have recorded the first dirty
    path with its first character missing (``skills/README.md`` became
    ``kills/README.md``).  Only an exact one-character truncation of exactly one
    currently dirty path is repaired.  No new path is allowed and no path is
    dropped.
    """

    if spec.get("dirty_paths_parser"):
        return spec, []
    actual = _actual_dirty_paths(repo)
    if actual is None:
        return spec, []
    actual_set = set(actual)
    repairs: list[dict] = []
    repaired = copy.deepcopy(spec)
    for key in ("allowed_dirty_paths", "forbidden_paths"):
        items = [str(item) for item in repaired.get(key) or []]
        if not items:
            continue
        fixed: list[str] = []
        for item in items:
            if item in actual_set or any(_exists_prefix(path, [item]) for path in actual):
                fixed.append(item)
                continue
            candidates = [path for path in actual if len(path) > 1 and path[1:] == item]
            if len(candidates) == 1:
                fixed.append(candidates[0])
                repairs.append({"field": key, "from": item, "to": candidates[0]})
            else:
                fixed.append(item)
        if fixed != items:
            repaired[key] = list(dict.fromkeys(fixed))
    if repairs:
        repaired["dirty_paths_parser"] = LEGACY_DIRTY_PARSER_REPAIR
    return (repaired, repairs) if repairs else (spec, [])


def _read_evidence(
    paths: Iterable[str],
    repo: Path,
    control_plane: Path,
    extra_roots: Iterable[Path] | None = None,
) -> tuple[str, list[str], list[str]]:
    chunks: list[str] = []
    found: list[str] = []
    missing: list[str] = []
    roots = [repo.resolve(), control_plane.resolve()]
    for root in extra_roots or []:
        try:
            roots.append(Path(root).resolve())
        except OSError:
            continue
    for raw in paths:
        candidate = Path(raw).expanduser()
        if not candidate.is_absolute():
            local = (repo / candidate).resolve()
            fallback = (control_plane / candidate).resolve()
            candidate = local if local.exists() else fallback
        try:
            resolved = candidate.resolve()
        except OSError:
            missing.append(raw)
            continue
        if not any(resolved == root or str(resolved).startswith(str(root) + "/") for root in roots):
            # Absolute paths outside the repository, control plane and the job's
            # own evidence root are not trusted as evidence.
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


PLACEHOLDER_RE = re.compile(
    r"\b(unrecorded|not recorded|todo|tbd|fixme|pending)\b", re.IGNORECASE
)


def _evidence_block(text: str) -> dict[str, str] | None:
    """Parse the structured evidence block, if present.

    ``text`` is already lower-cased by :func:`_read_evidence`.
    """

    begin = evidence_module.EVIDENCE_BEGIN.lower()
    end = evidence_module.EVIDENCE_END.lower()
    start = text.find(begin)
    if start < 0:
        return None
    finish = text.find(end, start + len(begin))
    if finish < 0:
        return {}
    body = text[start + len(begin) : finish]
    entries: dict[str, str] = {}
    for line in body.splitlines():
        match = re.match(r"\s*-\s*([a-z_]+)\s*:\s*(.*?)\s*$", line)
        if match:
            entries[match.group(1)] = match.group(2)
    return entries


def _evidence_value_problem(field: str, value: str) -> str | None:
    value = value.strip()
    if not value:
        return "is empty"
    if PLACEHOLDER_RE.search(value):
        return "is still a placeholder"
    if len(value) < 8:
        return "is too short to be useful evidence"
    if value == field:
        return "only repeats the field name"
    _needle, markers = EVIDENCE_MARKERS[field]
    if not any(marker in value for marker in markers):
        return "does not name the concrete result or detail the field requires"
    return None


def _check_evidence(
    text: str,
    found: list[str],
    missing: list[str],
    spec: dict,
    job: dict | None = None,
) -> list[dict]:
    checks: list[dict] = []
    require = spec.get("require") or {}
    job = job or {}
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

    block = _evidence_block(text)
    initialized = bool(job.get("evidence_initialized") or job.get("evidence_file"))
    if block is not None:
        expected_job = str(job.get("id") or "").lower()
        actual_job = (block.get("job_id") or "").strip()
        identity_ok = bool(expected_job) and actual_job == expected_job
        checks.append(
            {
                "id": "evidence_identity",
                "label": "job-specific evidence",
                "status": "verified" if identity_ok else "failed",
                "severity": "info" if identity_ok else "failed",
                "detail": (
                    f"evidence names job {actual_job or '(missing)'}"
                    if identity_ok
                    else (
                        f"evidence names job {actual_job or '(missing)'}, "
                        f"expected {expected_job or '(missing job id)'}"
                    )
                ),
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
            value = block.get(check_id)
            if not identity_ok:
                checks.append(
                    {
                        "id": check_id,
                        "label": check_id.replace("_", " "),
                        "status": "failed",
                        "severity": "failed",
                        "detail": "structured evidence does not belong to this job",
                    }
                )
                continue
            if value is None:
                checks.append(
                    {
                        "id": check_id,
                        "label": check_id.replace("_", " "),
                        "status": "failed",
                        "severity": "failed",
                        "detail": "structured evidence does not contain " + check_id,
                    }
                )
                continue
            problem = _evidence_value_problem(check_id, value)
            if problem:
                checks.append(
                    {
                        "id": check_id,
                        "label": check_id.replace("_", " "),
                        "status": "failed",
                        "severity": "failed",
                        "detail": f"{check_id} {problem}",
                    }
                )
            else:
                checks.append(
                    {
                        "id": check_id,
                        "label": check_id.replace("_", " "),
                        "status": "verified",
                        "severity": "info",
                        "detail": "recorded in " + ", ".join(found),
                    }
                )
        return checks

    if initialized:
        # A job whose evidence was initialized by the harness may not silently
        # fall back to free-text marker matching by deleting the block.
        checks.append(
            {
                "id": "evidence_identity",
                "label": "job-specific evidence",
                "status": "failed",
                "severity": "failed",
                "detail": "initialized evidence block is missing",
            }
        )
        for check_id in REQUIRED_EVIDENCE:
            if not require.get(check_id, True):
                continue
            checks.append(
                {
                    "id": check_id,
                    "label": check_id.replace("_", " "),
                    "status": "failed",
                    "severity": "failed",
                    "detail": "initialized evidence block is missing",
                }
            )
        return checks

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
                "status": "pending",
                "severity": "pending",
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


def _delivery_checks(repo: Path, spec: dict, branch: str) -> list[dict]:
    """Verify the job's recorded project delivery policy against the checkout."""

    policy = spec.get("delivery_policy")
    if not isinstance(policy, dict):
        return []
    checks: list[dict] = []
    configured_remote = str(spec.get("remote") or "")
    policy_remote = str(policy.get("remote") or "")
    expected_repository = project_policy.normalise_github_repository(
        policy.get("github_repository")
    )
    actual_repository = None
    remote_url = ""
    if policy_remote:
        result = _run_git(repo, "config", "--get", f"remote.{policy_remote}.url")
        if result.returncode == 0:
            remote_url = (result.stdout or "").strip()
            actual_repository = project_policy.normalise_remote_url(remote_url)
    problems: list[str] = []
    if not configured_remote:
        problems.append("the contract has no remote")
    elif configured_remote != policy_remote:
        problems.append(
            f"contract remote {configured_remote!r} differs from policy remote "
            f"{policy_remote!r}"
        )
    if not policy_remote:
        problems.append("the delivery policy has no remote")
    elif not remote_url:
        problems.append(f"git remote {policy_remote!r} is not configured")
    if expected_repository is None:
        problems.append("the delivery policy has no valid GitHub repository")
    elif actual_repository is None:
        problems.append(
            f"remote {policy_remote!r} does not point at a GitHub repository"
        )
    elif actual_repository != expected_repository:
        problems.append(
            f"remote {policy_remote!r} points at {actual_repository}, "
            f"expected {expected_repository}"
        )
    if problems:
        checks.append(
            {
                "id": "delivery_policy",
                "label": "project delivery policy",
                "status": "failed",
                "severity": "failed",
                "detail": "; ".join(problems),
            }
        )
    else:
        checks.append(
            {
                "id": "delivery_policy",
                "label": "project delivery policy",
                "status": "verified",
                "severity": "info",
                "detail": (
                    f"project {policy.get('project_id') or 'unknown'} uses "
                    f"{policy_remote} -> {expected_repository}"
                ),
            }
        )

    authorization = spec.get("authorization") or {}
    pattern = str(policy.get("branch_pattern") or "")
    matches = bool(
        branch
        and branch not in PROTECTED_BRANCH_NAMES
        and branch.startswith("agent/")
        and pattern
        and project_policy.BRANCH_PATTERN_RE.match(pattern)
        and fnmatch.fnmatchcase(branch, pattern)
    )
    if matches:
        checks.append(
            {
                "id": "branch_policy",
                "label": "authorized development branch",
                "status": "verified",
                "severity": "info",
                "detail": f"branch {branch} matches {pattern}",
            }
        )
    elif authorization.get("push"):
        checks.append(
            {
                "id": "branch_policy",
                "label": "authorized development branch",
                "status": "failed",
                "severity": "failed",
                "detail": (
                    f"push was authorized but branch {branch or 'unknown'} is outside "
                    f"the project development pattern {pattern or '(none)'}"
                ),
            }
        )
    else:
        checks.append(
            {
                "id": "branch_policy",
                "label": "authorized development branch",
                "status": "pending",
                "severity": "pending",
                "detail": (
                    f"branch {branch or 'unknown'} is outside {pattern or '(none)'}; "
                    "automatic push is not authorized"
                ),
            }
        )
    return checks


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
    status_paths = _actual_dirty_paths(repo)
    if status_paths is None:
        status_paths = parse_dirty_paths(_git_text(repo, "status", "--porcelain"))
    allowed_dirty = [str(item) for item in spec.get("allowed_dirty_paths") or []]
    unexpected: list[str] = []
    for path in status_paths:
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
    remote = str(spec.get("remote") or "")
    policy = spec.get("delivery_policy")
    if isinstance(policy, dict):
        pattern = str(policy.get("branch_pattern") or "")
        allowed = bool(
            branch
            and branch not in PROTECTED_BRANCH_NAMES
            and branch.startswith("agent/")
            and pattern
            and project_policy.BRANCH_PATTERN_RE.match(pattern)
            and fnmatch.fnmatchcase(branch, pattern)
        )
        if not allowed and authorization.get("push"):
            return {
                "id": "remote_sha",
                "label": "authorized development-branch push",
                "status": "failed",
                "severity": "failed",
                "detail": (
                    f"push was authorized but branch {branch or 'unknown'} is outside "
                    f"the project development pattern {pattern or '(none)'}"
                ),
            }
        if not allowed:
            return {
                "id": "remote_sha",
                "label": "authorized development-branch push",
                "status": "pending",
                "severity": "pending",
                "detail": (
                    f"branch {branch or 'unknown'} is outside the project development "
                    "pattern; handoff_sync=pending_authorization"
                ),
            }
    if not authorization.get("push"):
        return {
            "id": "remote_sha",
            "label": "authorized development-branch push",
            "status": "pending",
            "severity": "pending",
            "detail": "push is not authorized; handoff_sync=pending_authorization",
        }
    if not remote:
        return {
            "id": "remote_sha",
            "label": "authorized development-branch push",
            "status": "failed",
            "severity": "failed",
            "detail": "no project remote is configured in the completion contract",
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
    spec, dirty_repairs = repair_legacy_dirty_paths(spec, repo_path)
    extra_roots: list[Path] = []
    if job.get("evidence_file"):
        extra_roots.append(Path(str(job["evidence_file"])).expanduser().resolve().parent)
    if job.get("id"):
        try:
            extra_roots.append(job_dir(str(job["id"])).resolve())
        except (OSError, ValueError):
            pass
    evidence = spec.get("evidence_files") or spec.get("evidence_file") or []
    if isinstance(evidence, str):
        evidence = [evidence]
    text, found, missing = _read_evidence(
        evidence, repo_path, control_plane, extra_roots=extra_roots
    )
    checks = _check_evidence(text, found, missing, spec, job=job)
    branch_checks, branch = _branch_checks(repo_path, spec)
    checks.extend(branch_checks)
    checks.extend(_delivery_checks(repo_path, spec, branch))
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
        "dirty_path_repairs": dirty_repairs,
        "checks": checks,
        "evaluated_at": None,
    }
