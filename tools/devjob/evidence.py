"""Automatic, truthful per-job completion-contract evidence.

The harness initializes one evidence file per job with facts it can observe at
start time (job ID, repository, branch, base SHA, project and contract source).
It deliberately does not fill the required task-start fields: those must be
recorded by the executing agent after the work actually happens.  Initialization
is therefore not completion evidence and can never satisfy the contract by
itself.

The structured block below is machine-checked by :mod:`devjob.contract`.  A job
initialized by this module cannot fall back to the older free-text marker scan:
if the block is removed, the contract fails instead of silently accepting the
template prose.
"""

from __future__ import annotations

import os
from pathlib import Path

from .store import job_dir

EVIDENCE_FILENAME = "TASK.md"
EVIDENCE_SUBDIR = "evidence"

EVIDENCE_BEGIN = "<!-- workflow-v3-evidence:v1 -->"
EVIDENCE_END = "<!-- workflow-v3-evidence:end -->"

REQUIRED_FIELDS = (
    "skill_discovery",
    "freshness",
    "documentation_loading",
    "capability_harvest",
    "documentation_updates",
)

# Values that mean "the agent has not recorded this yet".  The initializer only
# writes UNRECORDED; the contract rejects every value in this set.
PLACEHOLDER_VALUES = (
    "unrecorded",
    "not recorded",
    "todo",
    "tbd",
    "fixme",
    "pending",
)

FIELD_HELP = {
    "skill_discovery": (
        "skills searched/loaded (paths, platform, maturity) or an explicit "
        "'no applicable skill'"
    ),
    "freshness": (
        "the freshness/compatibility result and the source revision checked"
    ),
    "documentation_loading": (
        "the control-plane, platform-pack and project documentation actually read"
    ),
    "capability_harvest": (
        "the reusable result or an explicit project-specific/no-harvest result"
    ),
    "documentation_updates": (
        "the documentation changed, or an explicit 'no documentation change needed'"
    ),
}


def evidence_path(job_id: str) -> Path:
    """Return the job-specific evidence path outside the project working tree."""

    return job_dir(job_id) / EVIDENCE_SUBDIR / EVIDENCE_FILENAME


def build_template(
    *,
    job_id: str,
    title: str,
    repo: str,
    branch: str | None,
    base_sha: str | None,
    project_id: str | None,
    contract_source: str,
    initialized_at: str,
) -> str:
    """Build a truthful but deliberately incomplete evidence template."""

    lines = [
        f"# Workflow v3 job evidence: {title}",
        "",
        "This file was initialized by the Workflow v3 harness at job start.",
        "Only the metadata below is harness-recorded. Every required evidence value",
        "is `UNRECORDED` until the executing agent records what it actually did.",
        "Initialization is not completion, approval or proof of work.",
        "",
        f"- Job ID: `{job_id}`",
        f"- Title: {title}",
        f"- Repository: `{repo}`",
        f"- Branch: `{branch or '(detached)'}`",
        f"- Base SHA: `{base_sha or '(unknown)'}`",
        f"- Project: `{project_id or '(unregistered)'}`",
        f"- Contract source: `{contract_source}`",
        f"- Initialized at: `{initialized_at}`",
        "- Executing agent: `UNRECORDED` (record the registered role that did the work; never infer it)",
        "",
        "## Required evidence",
        "",
        "Replace each `UNRECORDED` value with truthful, job-specific evidence.",
        "Keep the field names, the `job_id` line and the markers intact. Do not",
        "claim work that was not performed. The harness never fills these values.",
        "",
        EVIDENCE_BEGIN,
        f"- job_id: {job_id}",
    ]
    for field in REQUIRED_FIELDS:
        lines.append(f"- {field}: UNRECORDED")
    lines.extend([EVIDENCE_END, "", "Field meaning:"])
    for field in REQUIRED_FIELDS:
        lines.append(f"- `{field}`: {FIELD_HELP[field]}.")
    lines.extend(
        [
            "",
            "The completion contract reads this file. It fails while any required",
            "value is `UNRECORDED`, placeholder-like or lacks the expected detail,",
            "and it fails if this block is removed after initialization.",
            "",
        ]
    )
    return "\n".join(lines)


def initialize(
    *,
    job_id: str,
    title: str,
    repo: str,
    branch: str | None,
    base_sha: str | None,
    project_id: str | None,
    contract_source: str,
    initialized_at: str,
) -> tuple[Path, bool]:
    """Create the job evidence file if absent.

    Returns ``(path, created)``.  An existing file is never overwritten: a resume
    or a retried initialization must preserve the agent's recorded evidence.
    """

    path = evidence_path(job_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = build_template(
        job_id=job_id,
        title=title,
        repo=repo,
        branch=branch,
        base_sha=base_sha,
        project_id=project_id,
        contract_source=contract_source,
        initialized_at=initialized_at,
    )
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o640)
    except FileExistsError:
        return path, False
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(text)
    except Exception:
        try:
            path.unlink()
        except OSError:
            pass
        raise
    return path, True
