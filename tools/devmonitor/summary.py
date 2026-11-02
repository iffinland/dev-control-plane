"""Concise, evidence-based job result summaries for Telegram.

The summary deliberately separates technical completion from the functional
outcome the owner actually cares about:

* technical completion can be VERIFIED by acceptance commands, the mandatory
  completion contract, a scoped commit and an authorized pushed SHA;
* functional outcome is only VERIFIED when explicit owner/manual acceptance
  proves it. A green build, passing tests and a pushed commit are never treated
  as proof that the underlying bug is fixed.

Unresolved issues and pending work are reported as UNRESOLVED or NOT VERIFIED
instead of being hidden behind a SUCCESS label.
"""

from __future__ import annotations

from typing import Any

TECH_VERIFIED = "VERIFIED"
TECH_NOT_VERIFIED = "NOT VERIFIED"
TECH_PENDING = "PENDING"

FUNC_VERIFIED = "VERIFIED"
FUNC_UNRESOLVED = "UNRESOLVED"
FUNC_NOT_VERIFIED = "NOT VERIFIED"
FUNC_PENDING = "PENDING"

TERMINAL_FAILURE_STATES = {"FAILED", "TIMEOUT"}
TERMINAL_UNRESOLVED_STATES = {"BLOCKED", "CANCELLED"}


def _contract(payload: dict, record: dict | None) -> dict:
    value = (payload or {}).get("completion_contract")
    if not isinstance(value, dict) and record:
        value = record.get("completion_contract")
    return value if isinstance(value, dict) else {}


def _checks(contract: dict) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for check in contract.get("checks") or []:
        if isinstance(check, dict) and check.get("id"):
            result[str(check["id"])] = check
    return result


def technical_outcome(payload: dict, record: dict | None = None) -> tuple[str, str]:
    state = str((payload or {}).get("state") or "UNKNOWN")
    contract = _contract(payload, record)
    if state == "RUNNING":
        return TECH_PENDING, "the attempt is still running"
    if state == "SUCCESS":
        if contract.get("configured"):
            contract_state = str(contract.get("state") or "UNKNOWN")
            if contract_state == "VERIFIED":
                return TECH_VERIFIED, "acceptance criteria and the completion contract verified"
            if contract_state == "PENDING":
                return TECH_PENDING, f"completion contract is {contract_state}"
            return TECH_NOT_VERIFIED, f"completion contract is {contract_state}"
        return TECH_VERIFIED, "acceptance criteria verified (legacy job without a contract)"
    if state in TERMINAL_FAILURE_STATES:
        return TECH_NOT_VERIFIED, f"job ended {state}"
    if state in TERMINAL_UNRESOLVED_STATES:
        return TECH_NOT_VERIFIED, f"job ended {state}"
    return TECH_NOT_VERIFIED, f"job state is {state}"


def _manual_verified(record: dict | None) -> bool:
    if not record:
        return False
    verification = record.get("verification") or {}
    for criterion in record.get("acceptance_criteria") or []:
        if not isinstance(criterion, dict):
            continue
        if criterion.get("kind") != "manual":
            continue
        result = verification.get(str(criterion.get("id"))) or {}
        if isinstance(result, dict) and result.get("verified"):
            return True
    return False


def _unresolved_issues(payload: dict, record: dict | None) -> list[str]:
    issues: list[str] = []
    blocker = str((payload or {}).get("blocker") or "")
    if blocker:
        issues.append(f"blocker: {blocker[:200]}")
    for issue in (payload or {}).get("issues") or []:
        if not isinstance(issue, dict):
            continue
        if issue.get("recovered"):
            continue
        severity = str(issue.get("severity") or "")
        if severity.lower() in {"blocked", "failed", "critical", "high"}:
            issues.append(
                f"{severity or 'issue'} {issue.get('kind') or ''}: "
                f"{str(issue.get('message') or '')[:180]}".strip()
            )
    return issues


def functional_outcome(
    payload: dict, record: dict | None = None
) -> tuple[str, str]:
    state = str((payload or {}).get("state") or "UNKNOWN")
    if state == "RUNNING":
        return FUNC_PENDING, "no outcome yet"
    unresolved = _unresolved_issues(payload, record)
    if state in TERMINAL_FAILURE_STATES:
        return FUNC_UNRESOLVED, "the job did not complete successfully"
    if state in TERMINAL_UNRESOLVED_STATES:
        return FUNC_UNRESOLVED, "the job stopped before a functional outcome was established"
    if unresolved:
        return FUNC_UNRESOLVED, "unresolved issues remain"
    if state == "SUCCESS" and _manual_verified(record):
        return FUNC_VERIFIED, "explicit owner/manual acceptance was recorded"
    return (
        FUNC_NOT_VERIFIED,
        "technical checks do not prove the owner's underlying bug is fixed",
    )


def _acceptance_counts(record: dict | None) -> tuple[int, int, int]:
    if not record:
        return (0, 0, 0)
    verification = record.get("verification") or {}
    passed = failed = pending = 0
    for criterion in record.get("acceptance_criteria") or []:
        if not isinstance(criterion, dict):
            continue
        if not criterion.get("required", True):
            continue
        result = verification.get(str(criterion.get("id"))) or {}
        if isinstance(result, dict) and result.get("verified"):
            passed += 1
        elif criterion.get("kind") == "manual":
            pending += 1
        else:
            failed += 1
    return (passed, failed, pending)


def _github_line(contract: dict) -> str:
    checks = _checks(contract)
    commit = checks.get("commit") or {}
    push = checks.get("push") or {}
    remote = checks.get("remote_sha") or {}
    status = str(push.get("status") or "")
    remote_status = str(remote.get("status") or "")
    if status == "passed" and remote_status == "passed":
        sha = ""
        detail = str(remote.get("detail") or "")
        for token in detail.replace("`", " ").split():
            if len(token) >= 7 and all(ch in "0123456789abcdef" for ch in token.lower()):
                sha = token[:12]
                break
        return f"verified{(' @ ' + sha) if sha else ''}; remote SHA matches local HEAD"
    if status == "pending" or remote_status == "pending":
        return "not yet verified (push or remote SHA is pending)"
    if status or remote_status:
        failing = ", ".join(
            f"{name}={value.get('status')}"
            for name, value in (("push", push), ("remote_sha", remote))
            if value
        )
        return f"not verified ({failing})"
    if commit.get("status") == "passed":
        return "commit verified; no push authorization or remote verification recorded"
    return "not verified (no delivery evidence recorded)"


def _changes_line(record: dict | None) -> str:
    if not record:
        return "no change evidence available"
    snapshot = record.get("git") or {}
    diffstat = str(snapshot.get("diffstat") or "").strip()
    if diffstat:
        first = next((line for line in diffstat.splitlines() if line.strip()), "")
        return first[:220]
    contract = record.get("completion_contract") or {}
    commit = _checks(contract).get("commit") or {}
    detail = str(commit.get("detail") or "").strip()
    return detail[:220] if detail else "no changed files recorded"


def summary_text(
    payload: dict,
    record: dict | None = None,
    *,
    project: str | None = None,
) -> str:
    technical, technical_reason = technical_outcome(payload, record)
    functional, functional_reason = functional_outcome(payload, record)
    contract = _contract(payload, record)
    passed, failed, pending = _acceptance_counts(record)
    unresolved = _unresolved_issues(payload, record)
    failed_checks = [
        str(check.get("id"))
        for check in contract.get("checks") or []
        if isinstance(check, dict) and check.get("status") == "failed"
    ]
    pending_checks = [
        str(check.get("id"))
        for check in contract.get("checks") or []
        if isinstance(check, dict) and check.get("status") == "pending"
    ]
    lines = [
        "Result summary",
        f"Technical completion: {technical} ({technical_reason})",
        f"Functional outcome: {functional} ({functional_reason})",
    ]
    if project:
        lines.append(f"Project: {project}")
    lines.extend(
        [
            f"Changes: {_changes_line(record)}",
            f"Tests: {passed} verified, {failed} failed, {pending} pending",
            f"GitHub delivery: {_github_line(contract)}",
        ]
    )
    unresolved_notes = list(unresolved)
    if failed_checks:
        unresolved_notes.append("failed contract checks: " + ", ".join(failed_checks[:6]))
    if pending_checks:
        unresolved_notes.append("pending contract checks: " + ", ".join(pending_checks[:6]))
    if not unresolved_notes:
        lines.append("Unresolved issues: none recorded")
    else:
        lines.append("Unresolved issues:")
        for item in unresolved_notes[:5]:
            lines.append(f"  - {item}")
    lines.append(
        "Open Report or the logs for complete technical detail; this summary is not "
        "additional acceptance evidence."
    )
    return "\n".join(lines)


def outcome_badge(payload: dict, record: dict | None = None) -> str:
    technical, _ = technical_outcome(payload, record)
    functional, _ = functional_outcome(payload, record)
    return f"technical {technical} / functional {functional}"
