#!/usr/bin/env python3
"""Inspect and check OpenCode agent permission profiles.

OpenCode 1.x evaluates permission rules by matching the permission name and the
tool input, with the **last matching rule winning**. Bash rules match the text of
each parsed shell command. This tool implements that matching model over the
agent Markdown front matter so profile changes can be checked without starting
an OpenCode model session.

It is a policy inspector, not a sandbox. The patterns it evaluates are ordinary
string matches; wrappers, interpreters, scripts and remote SSH commands can do
more than the visible command text suggests. See
docs/operations/OPENCODE-PERMISSIONS.md.

Usage:
    python3 tools/validate_agent_permissions.py --check
    python3 tools/validate_agent_permissions.py --command "git push origin feature"
    python3 tools/validate_agent_permissions.py --matrix
    python3 tools/validate_agent_permissions.py --profile PATH --json

Exit codes: 0 = checks passed, 1 = policy check failed, 2 = usage/parse error.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROFILE = ROOT / "adapters/opencode/agents/opencode-development.md"


@dataclass(frozen=True)
class Rule:
    permission: str
    pattern: str
    action: str


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def front_matter(text: str) -> list[str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("profile has no leading YAML front matter")
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return lines[1:index]
    raise ValueError("profile front matter is not terminated")


def parse_permission(text: str) -> dict[str, dict[str, str]]:
    """Parse the small YAML subset used by agent permission blocks.

    This avoids a PyYAML dependency for a control-plane validator. It accepts the
    two forms used by OpenCode: ``tool: allow`` and a nested
    ``tool: {pattern: allow}`` mapping. Unsupported indentation is an error.
    """

    permission: dict[str, dict[str, str]] = {}
    in_permission = False
    current: str | None = None
    for number, raw in enumerate(front_matter(text), 2):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        stripped = raw.strip()
        if indent == 0:
            in_permission = stripped == "permission:"
            current = None
            continue
        if not in_permission:
            continue
        if indent == 2:
            key, separator, value = stripped.partition(":")
            if not separator:
                raise ValueError(f"line {number}: expected 'key: value'")
            key = _unquote(key)
            value = _unquote(value.strip())
            if value:
                permission[key] = {"*": value}
                current = None
            else:
                permission.setdefault(key, {})
                current = key
            continue
        if indent == 4 and current is not None:
            key, separator, value = stripped.partition(":")
            if not separator or not value.strip():
                raise ValueError(f"line {number}: expected 'pattern: action'")
            permission[current][_unquote(key)] = _unquote(value.strip())
            continue
        raise ValueError(f"line {number}: unsupported permission indentation")
    if not permission:
        raise ValueError("profile has no permission block")
    return permission


def rules_from_permission(permission: dict[str, dict[str, str]]) -> list[Rule]:
    return [
        Rule(tool, pattern, action)
        for tool, patterns in permission.items()
        for pattern, action in patterns.items()
    ]


def load_rules(path: Path) -> tuple[list[Rule], dict[str, dict[str, str]]]:
    permission = parse_permission(path.read_text(encoding="utf-8"))
    return rules_from_permission(permission), permission


def wildcard_match(value: str, pattern: str) -> bool:
    """Match like OpenCode's simple wildcard implementation.

    ``*`` matches zero or more characters, ``?`` matches one character, a pattern
    ending in ``" *"`` also matches without the trailing arguments, and matching
    is anchored to the whole value.
    """

    value = value.replace("\\", "/")
    pattern = pattern.replace("\\", "/")
    escaped = re.sub(r"([.+^${}()|\[\]\\])", r"\\\1", pattern)
    escaped = escaped.replace("*", ".*").replace("?", ".")
    if escaped.endswith(" .*"):
        escaped = escaped[:-3] + "( .*)?"
    return re.fullmatch(escaped, value, re.S) is not None


def evaluate(permission: str, value: str, rules: list[Rule]) -> str:
    """Return the last matching action, defaulting to ``ask`` like OpenCode."""

    action = "ask"
    for rule in rules:
        if wildcard_match(permission, rule.permission) and wildcard_match(value, rule.pattern):
            action = rule.action
    return action


def split_commands(command: str) -> list[str]:
    """Split a shell line on top-level ``;``, ``&&``, ``||`` and ``|``.

    This is an approximation used for policy checks. OpenCode uses tree-sitter to
    find command nodes. Quoted separators are preserved; command substitution and
    nested shells are intentionally not evaluated, which is one of the documented
    limitations.
    """

    parts: list[str] = []
    buffer: list[str] = []
    quote: str | None = None
    escaped = False
    index = 0
    while index < len(command):
        char = command[index]
        if escaped:
            buffer.append(char)
            escaped = False
            index += 1
            continue
        if char == "\\" and quote != "'":
            buffer.append(char)
            escaped = True
            index += 1
            continue
        if quote is not None:
            buffer.append(char)
            if char == quote:
                quote = None
            index += 1
            continue
        if char in "\"'":
            quote = char
            buffer.append(char)
            index += 1
            continue
        if command.startswith("&&", index) or command.startswith("||", index):
            parts.append("".join(buffer).strip())
            buffer = []
            index += 2
            continue
        if char in ";|\n":
            parts.append("".join(buffer).strip())
            buffer = []
            index += 1
            continue
        buffer.append(char)
        index += 1
    parts.append("".join(buffer).strip())
    return [part for part in parts if part]


def decide(permission: str, value: str, rules: list[Rule]) -> str:
    if permission != "bash":
        return evaluate(permission, value, rules)
    actions = [evaluate("bash", part, rules) for part in split_commands(value)]
    if "deny" in actions:
        return "deny"
    if "ask" in actions:
        return "ask"
    return "allow"


# (permission, value, expected action)
CHECKS: tuple[tuple[str, str, str], ...] = (
    # Normal development must not require approval.
    ("bash", "git status", "allow"),
    ("bash", "git add -A", "allow"),
    ("bash", "git commit -m 'permissions'", "allow"),
    ("bash", "git push origin feature/permissions", "allow"),
    ("bash", "gh pr create --fill", "allow"),
    ("bash", "ssh dev-host uptime", "allow"),
    ("bash", "npm ci", "allow"),
    ("bash", "npm run build", "allow"),
    ("bash", "npm test", "allow"),
    ("bash", "python3 -m pytest -q", "allow"),
    ("bash", "qortal qdn publish --help", "allow"),
    ("bash", "curl -s http://127.0.0.1:24991/api/status", "allow"),
    # Workflow/tooling state and diagnostics are normal development paths.
    ("bash", "cat ~/.local/state/dev-control-plane/jobs/example/job.json", "allow"),
    ("bash", "cd ~/.local/state/dev-control-plane/monitor && python3 -c 'print(1)'", "allow"),
    ("bash", "cp -a ~/.local/state/dev-control-plane /tmp/opencode/state-copy", "allow"),
    ("bash", "grep -rn 'qortium-data' docs/operations", "allow"),
    ("bash", "python3 -c \"print('/home/iffi/qortium-data')\"", "allow"),
    # Read-only VPS and Qortium diagnostics.
    ("bash", "ps -o pid,rss,args -p 299485", "allow"),
    ("bash", "journalctl -u qortium -n 100 --no-pager", "allow"),
    ("bash", "systemctl status qortium", "allow"),
    ("bash", "systemctl --no-pager status qortium", "allow"),
    ("bash", "systemctl --user status qortium", "allow"),
    ("bash", "service qortium status", "allow"),
    ("bash", "service --status-all", "allow"),
    ("bash", "apt list --installed", "allow"),
    ("bash", "dpkg -l", "allow"),
    ("bash", "sysctl -a", "allow"),
    ("bash", "ip addr show", "allow"),
    ("bash", "mount", "allow"),
    ("bash", "swapon --show", "allow"),
    ("bash", "dmesg", "allow"),
    ("bash", "tail -n 50 /home/iffi/qortium-preview/preview/run.log", "allow"),
    ("bash", "cat /home/iffi/qortium-preview/preview/settings-preview-local.json", "allow"),
    ("read", "/home/iffi/qortium-preview/preview/run.log", "allow"),
    ("read", "/home/iffi/dev-workspace/projects/example/.env.example", "allow"),
    ("edit", "/home/iffi/dev-workspace/projects/example/.env.example", "allow"),
    # Hard boundaries.
    ("bash", "sudo apt update", "deny"),
    ("bash", "/usr/bin/sudo apt update", "deny"),
    ("bash", "systemctl restart qortium", "deny"),
    ("bash", "systemctl stop qortium", "deny"),
    ("bash", "systemctl --user restart qortium", "deny"),
    ("bash", "service qortium stop", "deny"),
    ("bash", "kill 299485", "deny"),
    ("bash", "pkill java", "deny"),
    ("bash", "killall java", "deny"),
    ("bash", "tmux kill-server", "deny"),
    ("bash", "git push --force origin feature", "deny"),
    ("bash", "git merge main", "deny"),
    ("bash", "gh pr merge 1", "deny"),
    ("bash", "apt install curl", "deny"),
    ("bash", "npm install -g example", "deny"),
    ("bash", "npm publish", "deny"),
    ("bash", "java -jar /home/iffi/qortium-preview/qortium.jar", "deny"),
    ("bash", "rm -rf /home/iffi/qortium-preview/preview", "deny"),
    ("bash", "mv /home/iffi/qortium-preview/preview/run.log /tmp/run.log", "deny"),
    ("bash", "chmod 777 /home/iffi/qortium-data/blockchain.data", "deny"),
    ("bash", "cat /home/iffi/qortium-data/wallet.json", "deny"),
    ("bash", "echo changed > /home/iffi/qortium-preview/preview/settings-preview-local.json", "deny"),
    ("bash", "cat .env", "deny"),
    ("bash", "cat ~/.ssh/id_rsa", "deny"),
    ("bash", "journalctl --vacuum-size=1G", "deny"),
    ("bash", "hostnamectl set-hostname example", "deny"),
    ("bash", "nmcli connection modify eth0 ipv4.method manual", "deny"),
    ("bash", "nmcli connection show", "allow"),
    ("bash", "ip link set eth0 up", "deny"),
    ("bash", "ip link add dummy0 type dummy", "deny"),
    ("bash", "sysctl --system", "deny"),
    ("bash", "dmesg -n 1", "deny"),
    ("bash", "mount /dev/sda1 /mnt", "deny"),
    # File and external-directory boundaries.
    ("edit", "/home/iffi/qortium-preview/preview/settings-preview-local.json", "deny"),
    ("edit", "/home/iffi/qortium-data/blockchain.data", "deny"),
    ("edit", "/home/iffi/qortium-data/wallet.json", "deny"),
    ("edit", "/home/iffi/.local/state/dev-control-plane/jobs/example/job.json", "deny"),
    ("edit", "/home/iffi/.opencode/bin/opencode", "deny"),
    ("edit", "/home/iffi/dev-workspace/projects/example/src/main.ts", "allow"),
    ("read", "/home/iffi/dev-workspace/projects/example/.env", "deny"),
    ("read", "/home/iffi/.ssh/id_ed25519", "deny"),
    ("read", "/home/iffi/.config/opencode/opencode.jsonc", "deny"),
    ("read", "/home/iffi/qortium-data/wallet.json", "deny"),
    ("read", "/home/iffi/.local/state/dev-control-plane/jobs/example/job.json", "allow"),
    # Exact roots matter: "/**" does not match the directory itself.
    ("external_directory", "/home/iffi/dev-workspace", "allow"),
    ("external_directory", "/home/iffi/dev-workspace/projects/**", "allow"),
    ("external_directory", "/home/iffi/.local/state/dev-control-plane", "allow"),
    ("external_directory", "/home/iffi/.local/state/dev-control-plane/jobs/example/job.json", "allow"),
    ("external_directory", "/home/iffi/.opencode", "allow"),
    ("external_directory", "/home/iffi/.opencode/bin/opencode", "allow"),
    ("external_directory", "/tmp/opencode", "allow"),
    ("external_directory", "/home/iffi/qortium-preview", "allow"),
    ("external_directory", "/home/iffi/qortium-preview/**", "allow"),
    ("external_directory", "/home/iffi/qortium-data", "allow"),
    ("external_directory", "/home/iffi/qortium-data/**", "allow"),
    ("external_directory", "/etc/passwd", "deny"),
    ("external_directory", "/home/iffi/.ssh/id_ed25519", "deny"),
    ("external_directory", "/home/iffi/.gnupg/private-keys-v1.d", "deny"),
    ("external_directory", "/home/iffi/.aws/credentials", "deny"),
    ("external_directory", "/home/iffi/.local/share/opencode/auth.json", "deny"),
    ("external_directory", "/home/iffi/.config/opencode/opencode.jsonc", "deny"),
)


def render_matrix(rules: list[Rule]) -> list[dict[str, str]]:
    return [
        {"permission": permission, "value": value, "expected": expected, "actual": decide(permission, value, rules)}
        for permission, value, expected in CHECKS
    ]


def check(rules: list[Rule]) -> list[str]:
    errors: list[str] = []
    for permission, value, expected in CHECKS:
        actual = decide(permission, value, rules)
        if actual != expected:
            errors.append(f"{permission} {value!r}: expected {expected}, got {actual}")
    return errors


def limitation_rows(rules: list[Rule]) -> list[dict[str, str]]:
    """Commands that demonstrate why command patterns are not isolation."""

    samples = (
        "bash -c 'sudo apt update'",
        "sh -c 'systemctl restart qortium'",
        "env sudo systemctl stop qortium",
        "python3 -c \"import os; os.kill(299485, 9)\"",
        "ssh host 'sudo systemctl restart qortium'",
        "cat /home/iffi/qortium-preview/preview/run.log | sh",
        "node -e \"require('fs').writeFileSync('/home/iffi/qortium-preview/preview/x','y')\"",
    )
    return [
        {"value": value, "actual": decide("bash", value, rules), "note": "visible pattern does not contain the inner action"}
        for value in samples
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--profile", type=Path, action="append", default=[])
    parser.add_argument("--check", action="store_true", help="verify the development profile invariants")
    parser.add_argument("--command", help="show the decision for one bash command")
    parser.add_argument("--matrix", action="store_true", help="print the checked command matrix")
    parser.add_argument("--limitations", action="store_true", help="print known wrapper/script limitations")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    profiles = args.profile or [DEFAULT_PROFILE]
    payload: dict[str, object] = {}
    errors: list[str] = []
    try:
        for profile in profiles:
            rules, permission = load_rules(profile)
            if args.command:
                payload[str(profile)] = {
                    "command": args.command,
                    "parts": split_commands(args.command),
                    "action": decide("bash", args.command, rules),
                }
            if args.matrix:
                payload[str(profile)] = render_matrix(rules)
            if args.limitations:
                payload[str(profile)] = limitation_rows(rules)
            if args.check or not (args.command or args.matrix or args.limitations):
                errors.extend(f"{profile}: {error}" for error in check(rules))
                payload[str(profile)] = {
                    "rules": len(rules),
                    "tools": len(permission),
                    "checks": len(CHECKS),
                    "errors": check(rules),
                }
    except (OSError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        if args.command:
            for profile, result in payload.items():
                print(f"{profile}: {result['action']}")
                print("  parts: " + " | ".join(result["parts"]))
        elif args.matrix:
            for profile, rows in payload.items():
                print(f"{profile}:")
                for row in rows:
                    mark = "ok " if row["actual"] == row["expected"] else "BAD"
                    print(f"  {mark} {row['permission']:18} {row['actual']:5} {row['value']}")
        elif args.limitations:
            for profile, rows in payload.items():
                print(f"{profile}:")
                for row in rows:
                    print(f"  {row['actual']:5} {row['value']}")
        else:
            for profile, result in payload.items():
                status = "PASS" if not result["errors"] else "FAIL"
                print(f"{profile}: {status} ({result['rules']} rules, {result['checks']} checks)")
                for error in result["errors"]:
                    print(f"  ERROR: {error}")

    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
