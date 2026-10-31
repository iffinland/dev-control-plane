#!/usr/bin/env python3
"""Validate the control-plane's active Markdown structure and links.

This checks active guidance only. Historical reports and task artifacts are
excluded because they intentionally preserve original paths and provenance.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HISTORICAL = {"reports", "tasks"}
REQUIRED = (
    "AGENTS.md",
    "README.md",
    "WORKFLOW.md",
    "GIT-AND-HANDOFF.md",
    "PROJECT-REGISTRY.md",
    "ENVIRONMENT.md",
    "skills/README.md",
    "skills/_template/SKILL.md",
    "platforms/README.md",
    "platforms/qortal/README.md",
    "platforms/qortium/README.md",
    "adapters/opencode/README.md",
    "adapters/deepseek/README.md",
    "docs/migration/2026-10-30-phase1-control-plane.md",
    "templates/TASK.md",
    "templates/STATUS.json",
    "templates/HANDOFF.md",
    "templates/REPORT.md",
    "tools/validate_skills.py",
    "tools/validate_control_plane.py",
    "tools/opencode_guard.py",
    "tools/session_state.py",
    "tools/dev.py",
    "tools/test_opencode_guard.py",
    "tools/test_dev_cli.py",
    "tools/test_agent_permissions.py",
    "tools/test_install_profiles.py",
    "tools/test_detect.py",
    "tools/test_session_lifecycle.py",
    "tools/test_dev_monitor_redact.py",
    "tools/test_dev_monitor_auth.py",
    "tools/test_dev_monitor_projects.py",
    "tools/test_dev_monitor_documents.py",
    "tools/test_dev_monitor_jobs.py",
    "tools/test_dev_monitor_api.py",
    "tools/test_dev_monitor_state.py",
    "tools/test_dev_monitor_timings.py",
    "tools/test_dev_monitor_service_unit.py",
    "tools/test_dev_monitor_admission.py",
    "tools/test_dev_monitor_lifecycle.py",
    "tools/test_dev_monitor_control.py",
    "tools/test_dev_monitor_integration.py",
    "tools/devmonitor/admission.py",
    "tools/devmonitor/control.py",
    "tools/devmonitor/lifecycle.py",
    "tools/devmonitor/passphrase.py",
    "tools/dev_monitor.py",
    "deploy/systemd/user/qortium-dev-monitor.service",
    "tools/validate_agent_permissions.py",
    "tools/install_opencode_profiles.sh",
    "docs/operations/UNATTENDED-OPENCODE.md",
    "docs/operations/DEV-WORKFLOW-V3.md",
    "docs/operations/OPENCODE-PERMISSIONS.md",
    "docs/operations/QORTIUM-DEV-MONITOR.md",
    "docs/migration/2026-10-31-workflow-v3.md",
    "adapters/opencode/agents/opencode-unattended.md",
    "adapters/opencode/agents/opencode-development.md",
)
LINK_RE = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
REF_RE = re.compile(r"^ {0,3}\[[^\]]+\]:\s*<?([^ >]+)>?", re.MULTILINE)


def active_markdown() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*.md"):
        rel = path.relative_to(ROOT)
        if ".git" in rel.parts:
            continue
        if rel.parts and rel.parts[0] in HISTORICAL:
            continue
        files.append(path)
    return sorted(files)


def main() -> int:
    errors: list[str] = []

    for rel in REQUIRED:
        if not (ROOT / rel).is_file():
            errors.append(f"missing required file: {rel}")

    checked = 0
    for path in active_markdown():
        text = path.read_text(encoding="utf-8")
        targets = LINK_RE.findall(text) + REF_RE.findall(text)
        for raw in targets:
            target = raw.strip()
            if not target or target.startswith(("#", "http://", "https://", "mailto:", "tel:", "qortal://")):
                continue
            target = target.split("#", 1)[0].split("?", 1)[0]
            if not target:
                continue
            checked += 1
            resolved = (path.parent / target).resolve()
            try:
                resolved.relative_to(ROOT)
            except ValueError:
                errors.append(f"{path.relative_to(ROOT)}: link escapes control plane: {raw}")
                continue
            if not resolved.exists():
                errors.append(f"{path.relative_to(ROOT)}: broken link: {raw}")

    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        print(f"Control-plane validation failed: {len(errors)} error(s)")
        return 1

    print(
        f"Control-plane validation passed: {len(active_markdown())} active Markdown files, "
        f"{checked} relative links, {len(REQUIRED)} required files."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
