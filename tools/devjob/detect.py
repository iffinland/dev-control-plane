"""Detect unsafe or incomplete outcomes in an OpenCode run log.

An OpenCode exit code of zero is not acceptance. These detectors add explicit
signals for permission rejection, failed commands, missing dependencies, agent
step exhaustion and incomplete implementation.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path

from .store import safe_text


MAX_LOG_BYTES = 4 * 1024 * 1024
MAX_ISSUES = 50
SKIP_PREFIXES = (
    "command=",
    "snapshot_before=",
    "snapshot_after=",
    "started_utc=",
    "timeout_seconds=",
    "lock_file=",
    "heavy_command=",
    "cwd=",
    "log=",
    "=== ",
)


@dataclass(frozen=True)
class Issue:
    kind: str
    severity: str
    message: str
    line: int
    excerpt: str

    def asdict(self) -> dict:
        return asdict(self)


PATTERNS: tuple[tuple[str, str, re.Pattern[str], str], ...] = (
    (
        "permission_rejection",
        "blocked",
        re.compile(
            r"(?i)\bpermission\b.{0,50}\b(?:denied|rejected|not granted|required|blocked)\b"
        ),
        "the run reported a permission rejection or approval requirement",
    ),
    (
        "permission_rejection",
        "blocked",
        re.compile(r"(?i)\bauto[- ]?reject(?:ed|ing)?\b"),
        "OpenCode auto-rejected a permission request",
    ),
    (
        "permission_rejection",
        "blocked",
        re.compile(r"(?i)\boperation not permitted\b"),
        "the run hit an operation-not-permitted error",
    ),
    (
        "missing_dependency",
        "blocked",
        re.compile(
            r"(?i)\b(?:command not found|no such file or directory|"
            r"module not found error|import error: no module named|"
            r"cannot find module|err_module_not_found|enoent|"
            r"missing dependenc(?:y|ies)|is not installed)\b"
        ),
        "a required command, module or dependency is missing",
    ),
    (
        "step_exhaustion",
        "failed",
        re.compile(
            r"(?i)\b(?:reached|exceeded|exhausted)\b.{0,30}\b(?:step|steps|step limit|maximum steps)\b"
        ),
        "the agent exhausted its step limit",
    ),
    (
        "step_exhaustion",
        "failed",
        re.compile(r"(?i)\b(?:max|maximum)[-_ ]?steps\b|\bmaximum number of steps\b"),
        "the run reported a maximum-step condition",
    ),
    (
        "failed_command",
        "failed",
        re.compile(
            r"(?i)\b(?:command|process|script|step|build|test)\b.{0,40}"
            r"\b(?:failed|exited with (?:a )?non-?zero|returned (?:exit )?code [1-9])"
        ),
        "a command or step failed",
    ),
    (
        "failed_command",
        "failed",
        re.compile(r"(?i)\bexit(?:ed)? (?:with )?(?:code|status) [1-9]\d*\b"),
        "the log records a non-zero exit code",
    ),
    (
        "failed_command",
        "failed",
        re.compile(
            r"(?i)\b(?:pytest|npm|pnpm|yarn|bun|cargo|go test|mvn|gradle|make)\b"
            r".{0,80}\b(?:failed|failure|error)\b"
        ),
        "a project build or test command reported failure",
    ),
    (
        "incomplete_implementation",
        "failed",
        re.compile(
            r"(?i)\b(?:implementation|task|work|change|feature)\b.{0,20}"
            r"\b(?:is |was )?(?:incomplete|not complete|not completed)\b"
        ),
        "the agent reported an incomplete implementation",
    ),
    (
        "incomplete_implementation",
        "failed",
        re.compile(r"(?i)\b(?:not (?:yet )?implemented|partial(?:ly)? implement(?:ed|ation)?)\b"),
        "the log records unfinished implementation work",
    ),
    (
        "incomplete_implementation",
        "failed",
        re.compile(
            r"(?i)\bI (?:could not|was unable to|couldn't) "
            r"(?:complete|finish|implement)\b"
        ),
        "the agent said it could not complete the work",
    ),
    (
        "blocked_marker",
        "blocked",
        re.compile(r"(?i)\bBLOCKED:\s*\S"),
        "the agent marked the task as blocked",
    ),
)


def _iter_lines(path: Path) -> list[str]:
    try:
        size = path.stat().st_size
    except OSError:
        return []
    try:
        with path.open("rb") as handle:
            if size > MAX_LOG_BYTES:
                handle.seek(size - MAX_LOG_BYTES)
                handle.readline()
            data = handle.read()
    except OSError:
        return []
    return data.decode("utf-8", "replace").splitlines()


def scan_text(text: str) -> list[Issue]:
    issues: list[Issue] = []
    seen: set[tuple[str, str]] = set()
    for number, line in enumerate(text.splitlines(), 1):
        if line.startswith(SKIP_PREFIXES):
            continue
        for kind, severity, pattern, message in PATTERNS:
            match = pattern.search(line)
            if not match:
                continue
            key = (kind, match.group(0).lower())
            if key in seen:
                continue
            seen.add(key)
            issues.append(
                Issue(
                    kind=kind,
                    severity=severity,
                    message=message,
                    line=number,
                    excerpt=safe_text(line.strip(), 300),
                )
            )
            if len(issues) >= MAX_ISSUES:
                return issues
    return issues


def scan_log(path: str | Path) -> list[Issue]:
    return scan_text("\n".join(_iter_lines(Path(path))))


def highest_severity(issues: list[Issue | dict]) -> str | None:
    severities = {
        item.severity if isinstance(item, Issue) else str(item.get("severity"))
        for item in issues
    }
    if "blocked" in severities:
        return "blocked"
    if "failed" in severities:
        return "failed"
    return None
