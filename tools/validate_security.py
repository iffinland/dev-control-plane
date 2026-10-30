#!/usr/bin/env python3
"""Scan files intended for Git commit for sensitive infrastructure detail.

This validator is deliberately conservative. It reports likely exposed public
and private (non-loopback) IP addresses, credential-bearing URLs, private-key
blocks and well-known token formats. Standard loopback, unspecified,
link-local, multicast/reserved, RFC 5737 / RFC 3849 documentation ranges,
common public resolvers and obvious placeholders are ignored.

Private RFC1918/ULA addresses are reported by default, matching the control
plane security policy. Use --no-private only for an explicitly approved
documentation audit.

A documented exception may suppress one exact finding by repository-relative
path, finding kind, line number and SHA-256 of the full line. The exception does
not disable scanning of the file and cannot suppress the same value in another
path or on another line.

Values are masked in output. Never print a raw secret or a full infrastructure
address to a report or terminal log.

Usage:
    python3 tools/validate_security.py [PATH ...]
    python3 tools/validate_security.py --no-private /path/to/docs
    python3 tools/validate_security.py --exceptions tools/security-exceptions.json
    python3 tools/validate_security.py --self-test

Exit codes: 0 = clean, 1 = findings, 2 = usage/internal error.
"""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {
    ".git",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "node_modules",
    "dist",
    "build",
}
MAX_BYTES = 2 * 1024 * 1024

IPV4_RE = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")
IPV6_RE = re.compile(
    r"(?<![0-9A-Fa-f:])(?:[0-9A-Fa-f]{0,4}:){2,7}[0-9A-Fa-f]{0,4}(?![0-9A-Fa-f:])"
)

DOCUMENTATION_NETWORKS = (
    ipaddress.ip_network("192.0.2.0/24"),
    ipaddress.ip_network("198.51.100.0/24"),
    ipaddress.ip_network("203.0.113.0/24"),
    ipaddress.ip_network("2001:db8::/32"),
)
PLACEHOLDER_IPS = {
    "1.2.3.4",
    "1.1.1.1",
    "8.8.8.8",
    "8.8.4.4",
    "9.9.9.9",
    "255.255.255.255",
}

SECRET_PATTERNS = (
    ("private-key block", re.compile(r"-----BEGIN (?:[A-Z0-9]+ )?PRIVATE KEY-----")),
    (
        "GitHub token",
        re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{60,})\b"),
    ),
    ("AWS access key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("OpenAI-style key", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
    (
        "credential-bearing URL",
        re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://[^/\s:@]+:[^/\s@]+@"),
    ),
    (
        "assigned secret",
        re.compile(
            r"(?i)\b(?:api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token|"
            r"password|passwd|client[_-]?secret)\b\s*[:=]\s*[\"']?([^\s\"']{8,})"
        ),
    ),
)
PLACEHOLDER_VALUE_RE = re.compile(
    r"(?i)^(?:<.*>|\$\{.*\}|\*+|\.+|x{3,}|-+|_+|\{\{.*\}\}|"
    r"example.*|placeholder.*|redacted|changeme|change[-_]?me|your[-_].*|"
    r"token|secret|password|passwd|null|none|true|false|"
    r"get[a-z_]*\(|process\.env|os\.environ|env\..*|getenv\(.*)$"
)
SENSITIVE_NAME_RE = re.compile(
    r"(?i)(?:^\.env$|^\.env\.|\.pem$|\.key$|\.p12$|\.pfx$|\.jks$|"
    r"^id_rsa|^id_ed25519|\.kdbx$|^secrets?$|^credentials?$)"
)


def normalize_path(value: str | Path) -> str:
    text = Path(value).as_posix()
    while text.startswith("./"):
        text = text[2:]
    return text


def line_fingerprint(line: str) -> str:
    return hashlib.sha256(line.rstrip("\r\n").encode("utf-8")).hexdigest()


class ExceptionRule:
    __slots__ = ("path", "kind", "line", "line_sha256", "reason")

    def __init__(
        self, path: str, kind: str, line: int, line_sha256: str, reason: str = ""
    ) -> None:
        self.path = normalize_path(path)
        self.kind = kind
        self.line = line
        self.line_sha256 = line_sha256
        self.reason = reason


class ExceptionSet:
    def __init__(self, rules: list[ExceptionRule]) -> None:
        self.rules = rules

    def matches(self, path: str | Path, line: int, kind: str, line_text: str) -> bool:
        if line == 0 or not line_text:
            return False
        path_text = normalize_path(path)
        fingerprint = line_fingerprint(line_text)
        return any(
            rule.path == path_text
            and rule.line == line
            and rule.kind == kind
            and rule.line_sha256 == fingerprint
            for rule in self.rules
        )


EMPTY_EXCEPTIONS = ExceptionSet([])


def load_exceptions(path: Path) -> ExceptionSet:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("exceptions", []), list):
        raise ValueError("exception file must contain an 'exceptions' list")
    rules: list[ExceptionRule] = []
    for index, item in enumerate(data.get("exceptions", []), 1):
        if not isinstance(item, dict):
            raise ValueError(f"exception {index} is not an object")
        missing = {"path", "kind", "line", "line_sha256"} - item.keys()
        if missing:
            raise ValueError(f"exception {index} lacks: {', '.join(sorted(missing))}")
        if not isinstance(item["line"], int) or item["line"] < 1:
            raise ValueError(f"exception {index} has an invalid line")
        if not re.fullmatch(r"[0-9a-f]{64}", str(item["line_sha256"])):
            raise ValueError(f"exception {index} has an invalid line_sha256")
        rules.append(
            ExceptionRule(
                str(item["path"]),
                str(item["kind"]),
                item["line"],
                str(item["line_sha256"]),
                str(item.get("reason", "")),
            )
        )
    return ExceptionSet(rules)


class Finding:
    __slots__ = ("path", "line", "kind", "detail")

    def __init__(self, path: str | Path, line: int, kind: str, detail: str) -> None:
        self.path = Path(path)
        self.line = line
        self.kind = kind
        self.detail = detail

    def render(self, root: Path) -> str:
        display = self.path
        if display.is_absolute():
            try:
                display = display.relative_to(root)
            except ValueError:
                pass
        location = f"{display}:{self.line}" if self.line else str(display)
        return f"ERROR: {location}: {self.kind}: {self.detail}"


def mask_ip(value: str) -> str:
    if "." in value:
        first = value.split(".", 1)[0]
        return f"{first}.***.***.***"
    first = value.split(":", 1)[0] or "::"
    return f"{first}:***"


def is_ignored_ip(value: str, include_private: bool) -> tuple[bool, str]:
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        return True, ""
    if value in PLACEHOLDER_IPS:
        return True, ""
    if any(ip in network for network in DOCUMENTATION_NETWORKS):
        return True, ""
    if ip.is_loopback or ip.is_unspecified or ip.is_link_local:
        return True, ""
    if ip.is_multicast or ip.is_reserved:
        return True, ""
    if ip.is_private:
        return (not include_private), "private"
    return False, "public"


def iter_files(root: Path) -> list[Path]:
    if not root.exists():
        raise FileNotFoundError(root)
    if root.is_file():
        return [root]
    if (root / ".git").exists():
        result = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-co", "--exclude-standard", "-z"],
            capture_output=True,
            check=False,
        )
        if result.returncode == 0:
            names = [name for name in result.stdout.decode("utf-8", "replace").split("\0") if name]
            return sorted(root / name for name in names if (root / name).is_file())
    files: list[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        files.append(path)
    return files


def scan_text(
    path: str | Path,
    text: str,
    include_private: bool = True,
    exceptions: ExceptionSet | None = None,
    check_name: bool = True,
) -> list[Finding]:
    path_obj = Path(path)
    findings: list[Finding] = []
    active = exceptions or EMPTY_EXCEPTIONS

    if check_name and SENSITIVE_NAME_RE.search(path_obj.name) and path_obj.name not in {
        ".env.example",
        ".env.sample",
    }:
        findings.append(
            Finding(path_obj, 0, "sensitive filename", "review before commit")
        )

    for number, line in enumerate(text.splitlines(), 1):
        seen: set[str] = set()
        for match in IPV4_RE.finditer(line):
            value = match.group(0)
            if value in seen:
                continue
            seen.add(value)
            ignored, scope = is_ignored_ip(value, include_private)
            if ignored or not scope:
                continue
            kind = f"{scope} IPv4 address"
            if active.matches(path_obj, number, kind, line):
                continue
            findings.append(Finding(path_obj, number, kind, mask_ip(value)))
        for match in IPV6_RE.finditer(line):
            value = match.group(0)
            if value in seen:
                continue
            seen.add(value)
            ignored, scope = is_ignored_ip(value, include_private)
            if ignored or not scope:
                continue
            kind = f"{scope} IPv6 address"
            if active.matches(path_obj, number, kind, line):
                continue
            findings.append(Finding(path_obj, number, kind, mask_ip(value)))
        for label, pattern in SECRET_PATTERNS:
            match = pattern.search(line)
            if not match:
                continue
            if label == "assigned secret":
                value = match.group(1)
                if PLACEHOLDER_VALUE_RE.match(value):
                    continue
            findings.append(Finding(path_obj, number, label, "[redacted]"))
    return findings


def scan_file(
    path: Path,
    include_private: bool,
    exceptions: ExceptionSet | None = None,
    display_path: Path | None = None,
) -> list[Finding]:
    try:
        if path.stat().st_size > MAX_BYTES:
            return []
        data = path.read_bytes()
    except OSError:
        return []
    if b"\0" in data:
        return []
    text = data.decode("utf-8", "replace")
    return scan_text(display_path or path, text, include_private, exceptions)


def scan(
    roots: list[Path],
    include_private: bool,
    exceptions: ExceptionSet | None = None,
) -> list[Finding]:
    findings: list[Finding] = []
    for root in roots:
        if root.is_file():
            display = Path(root.name)
        else:
            display = None
        for path in iter_files(root):
            relative = display or path.relative_to(root)
            findings.extend(scan_file(path, include_private, exceptions, relative))
    return findings


def self_test() -> int:
    with tempfile.TemporaryDirectory(prefix="security-validator-") as temporary:
        root = Path(temporary)
        (root / "clean.md").write_text(
            "loopback 127.0.0.1:24991\n"
            "docs 192.0.2.10 and 198.51.100.20 and 203.0.113.30\n"
            "placeholder 1.2.3.4 and 0.0.0.0 and 255.255.255.255\n",
            encoding="utf-8",
        )
        public_ip = ".".join(("144", "91", "123", "144"))
        private_ip = ".".join(("10", "20", "30", "40"))
        credential_url = "https://" + "user" + ":" + "pass" + "@" + "example.invalid/path"
        (root / "bad.md").write_text(
            f"host {public_ip}\n"
            "token ghp_" + "a" * 36 + "\n"
            f"url {credential_url}\n",
            encoding="utf-8",
        )
        (root / "private.md").write_text(f"internal {private_ip}\n", encoding="utf-8")

        excepted_line = f"historical host {public_ip}"
        (root / "report.md").write_text(excepted_line + "\n", encoding="utf-8")
        exception = ExceptionSet(
            [
                ExceptionRule(
                    "report.md",
                    "public IPv4 address",
                    1,
                    line_fingerprint(excepted_line),
                    "self-test",
                )
            ]
        )

        if scan([root / "clean.md"], True):
            print("self-test failed: clean fixture produced findings", file=sys.stderr)
            return 1
        if not scan([root / "bad.md"], True):
            print("self-test failed: bad fixture produced no findings", file=sys.stderr)
            return 1
        if not scan([root / "private.md"], True):
            print("self-test failed: private fixture was not flagged by default", file=sys.stderr)
            return 1
        if scan([root / "private.md"], False):
            print("self-test failed: private fixture was flagged with --no-private", file=sys.stderr)
            return 1
        if scan([root / "report.md"], True, exception):
            print("self-test failed: exact exception did not suppress the finding", file=sys.stderr)
            return 1
        (root / "report.md").write_text(
            excepted_line + f"\nsecond host {public_ip}\n", encoding="utf-8"
        )
        if not scan([root / "report.md"], True, exception):
            print("self-test failed: duplicate finding in excepted file was not reported", file=sys.stderr)
            return 1
        (root / "other.md").write_text(f"host {public_ip}\n", encoding="utf-8")
        if not scan([root / "other.md"], True, exception):
            print("self-test failed: excepted address in another file was not reported", file=sys.stderr)
            return 1
    print("Security validator self-test passed.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument(
        "--no-private",
        action="store_true",
        help="ignore RFC1918/ULA addresses (loopback is always ignored)",
    )
    parser.add_argument("--exceptions", type=Path, help="JSON exception file")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return self_test()

    roots = args.paths or [ROOT]
    include_private = not args.no_private

    try:
        exceptions: ExceptionSet | None = None
        exception_path = args.exceptions
        if exception_path is None:
            candidate = ROOT / "tools/security-exceptions.json"
            if candidate.exists():
                for root in roots:
                    resolved = root.resolve()
                    if resolved == ROOT or ROOT in resolved.parents:
                        exception_path = candidate
                        break
        if exception_path is not None:
            exceptions = load_exceptions(exception_path)
        findings = scan(roots, include_private, exceptions)
    except FileNotFoundError as error:
        print(f"ERROR: path not found: {error}", file=sys.stderr)
        return 2
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"ERROR: security validation could not run: {error}", file=sys.stderr)
        return 2

    if findings:
        for finding in findings:
            print(finding.render(roots[0] if len(roots) == 1 else Path.cwd()))
        print(f"Security validation failed: {len(findings)} finding(s)")
        return 1

    print(
        f"Security validation passed: {sum(len(iter_files(root)) for root in roots)} file(s) scanned."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
