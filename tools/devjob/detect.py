"""Detect unsafe or incomplete outcomes in an OpenCode run.

An OpenCode exit code of zero is not acceptance. These detectors add explicit
signals for permission rejection, failed commands, missing dependencies, agent
step exhaustion and incomplete implementation.

Preference order:

1. structured OpenCode session events from ``opencode export`` when the session
   id and export are available;
2. context-aware parsing of the default OpenCode console log.

The fallback parser deliberately scans runtime error contexts, not arbitrary
file content. Documentation, source code, read/edit output and git diff text
are not treated as runtime failures merely because they contain words such as
"permission denied" or "not installed".
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

import session_state

from .store import safe_text


MAX_LOG_BYTES = 4 * 1024 * 1024
MAX_SESSION_BYTES = 32 * 1024 * 1024
MAX_ISSUES = 50
SESSION_EXPORT_TIMEOUT = 30
EXECUTION_TOOLS = {"bash", "shell", "terminal"}
ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
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
SECTION_PREFIXES = (
    "===",
    "guard:",
    "opencode:",
    "opencode-guard:",
    "snapshot_before=",
    "snapshot_after=",
    "started_utc=",
    "timeout_seconds=",
    "lock_file=",
    "heavy_command=",
    "command=",
    "cwd=",
    "log=",
)
DIFF_START_PREFIXES = ("diff --git ", "Index: ", "@@ ")
DIFF_CONTENT_PREFIXES = ("+", "-", " ", "\\ No newline")
RUNTIME_PREFIXES = (
    "error:",
    "fatal:",
    "traceback (most recent call last):",
    "guard:",
    "opencode:",
    "opencode-guard:",
    "permission denied:",
    "operation not permitted",
    "bash:",
    "sh:",
    "zsh:",
    "dash:",
    "npm err!",
    "pnpm err!",
    "yarn error",
    "python:",
    "node:",
    "modulenotfounderror:",
    "importerror:",
    "filenotfounderror:",
    "[errno 2]",
    "cannot find module",
    "err_module_not_found",
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
        "permission_rejection",
        "blocked",
        re.compile(r"(?i)rule which prevents you from using this specific tool call"),
        "OpenCode rejected the tool call by permission rule",
    ),
    (
        "missing_dependency",
        "blocked",
        re.compile(
            r"(?i)\b(?:command not found|no such file or directory|"
            r"module not found error|import error: no module named|"
            r"no module named|cannot find module|err_module_not_found|enoent|"
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

SPECIFIC_KINDS = (
    "permission_rejection",
    "missing_dependency",
    "step_exhaustion",
    "incomplete_implementation",
    "blocked_marker",
)
MESSAGE_BY_KIND = {kind: message for kind, _severity, _pattern, message in PATTERNS}
SEVERITY_BY_KIND = {kind: severity for kind, severity, _pattern, _message in PATTERNS}
SEVERITY_BY_KIND["failed_command"] = "failed"


def _severity(kind: str) -> str:
    return SEVERITY_BY_KIND.get(kind, "failed")


def _message(kind: str) -> str:
    return MESSAGE_BY_KIND.get(kind, "a runtime failure was detected")


def _strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


def _append(
    issues: list[Issue],
    seen: set[tuple[str, str]],
    kind: str,
    line: int,
    excerpt: str,
) -> None:
    if len(issues) >= MAX_ISSUES:
        return
    clean = safe_text(excerpt.strip(), 300)
    key = (kind, clean.lower())
    if not clean or key in seen:
        return
    seen.add(key)
    issues.append(
        Issue(
            kind=kind,
            severity=_severity(kind),
            message=_message(kind),
            line=line,
            excerpt=clean,
        )
    )


def _has_runtime_prefix(text: str) -> bool:
    return text.lower().startswith(RUNTIME_PREFIXES)


def _matches(kind: str, text: str) -> bool:
    return any(
        pattern.search(text)
        for candidate, _severity_value, pattern, _message_value in PATTERNS
        if candidate == kind
    )


def _specific_signal(text: str) -> str | None:
    for kind in SPECIFIC_KINDS:
        if _matches(kind, text):
            return kind
    return None


def _runtime_text(text: str) -> str | None:
    if not text[:1].isspace():
        return text
    stripped = text.lstrip()
    return stripped if _has_runtime_prefix(stripped) else None


def _permission_line(text: str) -> bool:
    return _has_runtime_prefix(text) and _matches("permission_rejection", text)


def _missing_line(text: str) -> bool:
    return _has_runtime_prefix(text) and _matches("missing_dependency", text)


def _step_line(text: str) -> bool:
    return len(text) < 300 and _matches("step_exhaustion", text)


def _incomplete_line(text: str) -> bool:
    return len(text) < 300 and _matches("incomplete_implementation", text)


def _blocked_line(text: str) -> bool:
    return bool(re.match(r"(?i)^BLOCKED:\s*\S", text))


def _failed_line(text: str) -> bool:
    lower = text.lower()
    if lower.startswith(
        (
            "command failed",
            "a command failed",
            "process failed",
            "build failed",
            "test failed",
            "failed (",
            "failed:",
        )
    ):
        return True
    return _has_runtime_prefix(text) and _matches("failed_command", text)


def _line_signals(text: str, include_specific: bool = True) -> tuple[str, ...]:
    signals: list[str] = []
    if include_specific and _permission_line(text):
        signals.append("permission_rejection")
    if include_specific and _missing_line(text):
        signals.append("missing_dependency")
    if _step_line(text):
        signals.append("step_exhaustion")
    if _incomplete_line(text):
        signals.append("incomplete_implementation")
    if _blocked_line(text):
        signals.append("blocked_marker")
    if _failed_line(text):
        signals.append("failed_command")
    return tuple(signals)


def _infer_failure_tool(line: str) -> str:
    body = line[2:].strip() if line.startswith("✗ ") else line.strip()
    first = body.split(maxsplit=1)[0].lower() if body else ""
    if first in {"webfetch", "websearch", "edit", "write", "read", "glob", "grep", "list", "skill"}:
        return first
    return "bash"


def _output_signal(text: str) -> tuple[str, str] | None:
    found: dict[str, str] = {}
    for raw in text.splitlines():
        clean = _strip_ansi(raw).rstrip()
        if not clean:
            continue
        runtime = _runtime_text(clean)
        if runtime is None:
            continue
        for kind in _line_signals(runtime):
            if kind in SPECIFIC_KINDS and kind not in found:
                found[kind] = runtime
    for kind in SPECIFIC_KINDS:
        if kind in found:
            return kind, found[kind]
    return None


def _classify_failure_block(lines: list[str], tool: str) -> tuple[str, str] | None:
    body = "\n".join(lines[1:]).strip()
    if body:
        found = _output_signal(body)
        if found:
            return found
    if tool in EXECUTION_TOOLS:
        return "failed_command", lines[0] if lines else ""
    # A failed web/read/edit tool that is not a permission or dependency error
    # is not a command/build/test failure. Keep it out of the final state.
    return None


def _process_line(
    text: str,
    line_number: int,
    issues: list[Issue],
    seen: set[tuple[str, str]],
    *,
    include_specific: bool = True,
) -> None:
    if not text.strip():
        return
    if text.startswith(SKIP_PREFIXES):
        return
    if text.startswith(DIFF_START_PREFIXES):
        return
    if text.startswith(("+", "-")):
        return
    # Indented output is almost always file content, diffs or wrapped prose.
    # Only an explicit runtime error prefix is allowed through indentation.
    runtime = _runtime_text(text)
    if runtime is None:
        return
    for kind in _line_signals(runtime, include_specific=include_specific):
        _append(issues, seen, kind, line_number, runtime)


def _iter_lines(path: Path, start_offset: int = 0) -> list[str]:
    try:
        size = path.stat().st_size
    except OSError:
        return []
    if size <= start_offset:
        return []
    try:
        with path.open("rb") as handle:
            begin = max(start_offset, size - MAX_LOG_BYTES)
            handle.seek(begin)
            if begin > start_offset:
                handle.readline()
            data = handle.read()
    except OSError:
        return []
    return data.decode("utf-8", "replace").splitlines()


def scan_text(text: str) -> list[Issue]:
    """Scan a default OpenCode console log with runtime-context awareness."""

    issues: list[Issue] = []
    seen: set[tuple[str, str]] = set()
    current_kind = "none"
    failure_tool = "bash"
    failure_lines: list[str] = []
    in_diff = False

    def flush_failure() -> None:
        nonlocal failure_lines, failure_tool
        if not failure_lines:
            return
        classified = _classify_failure_block(failure_lines, failure_tool)
        if classified:
            kind, excerpt = classified
            _append(issues, seen, kind, failure_line, excerpt)
        failure_lines = []
        failure_tool = "bash"

    failure_line = 0
    for number, raw in enumerate(text.splitlines(), 1):
        clean = _strip_ansi(raw).rstrip()
        stripped = clean.strip()
        if not stripped:
            if current_kind == "failure":
                failure_lines.append(clean)
            continue
        if clean.startswith(SECTION_PREFIXES):
            flush_failure()
            current_kind = "none"
            in_diff = False
            continue
        if clean.startswith("$ "):
            flush_failure()
            current_kind = "bash"
            in_diff = False
            continue
        if clean.startswith("✗ "):
            flush_failure()
            current_kind = "failure"
            failure_tool = _infer_failure_tool(clean)
            failure_lines = [clean]
            failure_line = number
            in_diff = False
            continue
        if clean.startswith(("← ", "→ ", "% ")):
            flush_failure()
            current_kind = "skip"
            in_diff = False
            continue

        if current_kind == "failure":
            failure_lines.append(clean)
            continue
        if current_kind == "skip":
            continue
        if current_kind == "bash":
            if clean.startswith(DIFF_START_PREFIXES):
                in_diff = True
                continue
            if in_diff:
                if clean.startswith(DIFF_CONTENT_PREFIXES):
                    continue
                in_diff = False
        _process_line(
            clean,
            number,
            issues,
            seen,
            include_specific=(current_kind != "bash"),
        )
        if len(issues) >= MAX_ISSUES:
            break
    flush_failure()
    return issues[:MAX_ISSUES]


def _exit_code(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and re.fullmatch(r"-?\d+", value.strip()):
        return int(value.strip())
    return None


def _message_created(info: dict) -> int | None:
    time_info = info.get("time")
    if not isinstance(time_info, dict):
        return None
    created = time_info.get("created")
    if isinstance(created, (int, float)) and not isinstance(created, bool):
        return int(created)
    return None


def _event_tool_issue(part: dict) -> tuple[str, str] | None:
    state = part.get("state")
    if not isinstance(state, dict):
        return None
    tool = str(part.get("tool") or "").lower()
    status = str(state.get("status") or "").lower()
    error = str(state.get("error") or "")
    output = str(state.get("output") or "")
    metadata = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
    exit_code = _exit_code(metadata.get("exit"))

    if error:
        signal = _specific_signal(error)
        if signal:
            return signal, error.splitlines()[0]
        if tool in EXECUTION_TOOLS:
            return "failed_command", error.splitlines()[0]
        return None
    if status == "error":
        if tool in EXECUTION_TOOLS:
            return "failed_command", f"{tool} tool failed"
        return None
    if status == "completed" and exit_code not in (None, 0):
        body = (error + "\n" + output).strip()
        found = _output_signal(body)
        if found:
            return found
        if tool in EXECUTION_TOOLS:
            return "failed_command", body.splitlines()[0] if body else f"{tool} exited {exit_code}"
    return None


def scan_events(payload: object, since_ms: int | None = None) -> list[Issue]:
    """Scan structured OpenCode session-export events.

    The function reads only tool state and assistant text. User prompts, tool
    inputs and successful tool output are not scanned for permission or
    dependency words.
    """

    if not isinstance(payload, dict):
        return []
    messages = payload.get("messages")
    if not isinstance(messages, list):
        return []
    issues: list[Issue] = []
    seen: set[tuple[str, str]] = set()
    for message in messages:
        if not isinstance(message, dict):
            continue
        info = message.get("info") if isinstance(message.get("info"), dict) else {}
        created = _message_created(info)
        if since_ms is not None and created is not None and created < since_ms:
            continue
        role = str(info.get("role") or "")
        parts = message.get("parts")
        if not isinstance(parts, list):
            continue
        for part in parts:
            if not isinstance(part, dict):
                continue
            part_type = str(part.get("type") or "")
            if part_type == "tool":
                found = _event_tool_issue(part)
                if found:
                    kind, excerpt = found
                    _append(issues, seen, kind, 0, excerpt)
                continue
            if part_type == "text" and role == "assistant":
                text = str(part.get("text") or "")
                for line in text.splitlines():
                    clean = _strip_ansi(line).rstrip()
                    if not clean or clean[:1].isspace():
                        continue
                    for kind in _line_signals(clean):
                        if kind in {"step_exhaustion", "incomplete_implementation", "blocked_marker"}:
                            _append(issues, seen, kind, 0, clean)
            if len(issues) >= MAX_ISSUES:
                return issues[:MAX_ISSUES]
    return issues[:MAX_ISSUES]


def scan_session(
    session_id: str | None,
    *,
    cwd: str | Path | None = None,
    since_ms: int | None = None,
    timeout: int = SESSION_EXPORT_TIMEOUT,
) -> list[Issue] | None:
    """Return structured issues, or ``None`` when export is unavailable.

    The export is parsed in memory and never written to the job directory. Only
    short sanitized excerpts are retained in the issue list.
    """

    if not session_id:
        return None
    # OpenCode 1.19.5 truncates large export output when stdout is a pipe.
    # session_state reads through an anonymous temporary file instead. The
    # export is parsed and discarded; nothing is written to the job directory.
    payload = session_state.load_export(
        session_id,
        cwd=cwd,
        timeout=timeout,
        max_bytes=MAX_SESSION_BYTES,
    )
    if payload is None:
        return None
    messages = payload.get("messages")
    if not isinstance(messages, list) or not messages:
        return None
    if not session_state.has_observable_events(payload):
        return None
    return scan_events(payload, since_ms=since_ms)


def scan_log(path: str | Path, start_offset: int = 0) -> list[Issue]:
    return scan_text("\n".join(_iter_lines(Path(path), start_offset)))


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
