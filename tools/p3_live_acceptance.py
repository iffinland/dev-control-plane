#!/usr/bin/env python3
"""CLI for the isolated P3 Telegram live acceptance harness.

This command prepares a synthetic fixture, optionally runs an isolated monitor
against the real authorized Telegram bot, verifies the recorded interactions and
removes the fixture. It never edits the owner Telegram configuration, the
production project registry, the live monitor state or a production project.

Typical operator sequence (the live monitor must be stopped first, manually):

    python3 tools/p3_live_acceptance.py prepare --work-dir /tmp/p3-live
    python3 tools/p3_live_acceptance.py run --work-dir /tmp/p3-live \
        --confirm-live-telegram
    # interact with the real bot, then fill telegram-evidence.json
    python3 tools/p3_live_acceptance.py verify --work-dir /tmp/p3-live
    python3 tools/p3_live_acceptance.py cleanup --work-dir /tmp/p3-live

`prepare`, `verify`, `status` and `cleanup` do not contact Telegram. Only `run`
starts the isolated long poller, and only with the explicit confirmation flag.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from devmonitor.acceptance import (  # noqa: E402
    DEFAULT_INSTRUCTION,
    AcceptanceError,
    LiveAcceptanceHarness,
)
from devmonitor.config import ConfigError, resolve_config_path  # noqa: E402


def _print_prepare(harness: LiveAcceptanceHarness, source_config: Path) -> None:
    manifest = harness.manifest
    print("P3 Telegram live acceptance fixture prepared (SYNTHETIC).")
    print(f"  work dir: {manifest['paths']['root']}")
    print(f"  job id:   {manifest['job_id']}")
    print(f"  project:  {manifest['project_id']}")
    print(f"  source config: {source_config} (unchanged)")
    print(f"  source registry: {manifest['source']['registry']} (unchanged)")
    print(f"  isolated registry: {manifest['paths']['registry']}")
    print(f"  isolated job state: {manifest['paths']['job_state']}")
    print(f"  isolated monitor state: {manifest['paths']['monitor_state']}")
    print(
        "\nThis fixture is not a development job and can never become a real "
        "success. It forces the synthetic job to CANCELLED."
    )
    print("\nNext steps:")
    print("  1. Stop the production monitor through its documented path.")
    print(
        "  2. Run: python3 tools/p3_live_acceptance.py run "
        f"--work-dir {manifest['paths']['root']} --confirm-live-telegram"
    )
    print("  3. In the private owner chat, follow evidence TELEGRAM-EVIDENCE.md.")
    print(
        "  4. Fill telegram-evidence.json, then run: "
        f"python3 tools/p3_live_acceptance.py verify "
        f"--work-dir {manifest['paths']['root']}"
    )
    print(
        "  5. Remove the fixture: python3 tools/p3_live_acceptance.py cleanup "
        f"--work-dir {manifest['paths']['root']}"
    )


def command_prepare(args: argparse.Namespace) -> int:
    source = Path(args.source_config).expanduser() if args.source_config else resolve_config_path()
    if args.work_dir:
        work_dir = Path(args.work_dir).expanduser()
    else:
        work_dir = Path(tempfile.mkdtemp(prefix="p3-telegram-live-"))
    harness = LiveAcceptanceHarness.prepare(
        work_dir,
        source_config=source,
        live_state_dir=args.live_state_dir,
        instruction=args.instruction,
    )
    _print_prepare(harness, source)
    if args.json:
        print(json.dumps(harness.manifest, indent=2, sort_keys=True))
    return 0


def command_run(args: argparse.Namespace) -> int:
    harness = LiveAcceptanceHarness.load(args.work_dir)
    result = harness.run(
        timeout_seconds=args.timeout,
        expect_resume=args.expect_resume,
        confirm_live=args.confirm_live_telegram,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    print(
        "\nPoller stopped. Fill the Telegram evidence and run verify. "
        "Restart the production monitor manually only after cleanup."
    )
    return 0


def command_verify(args: argparse.Namespace) -> int:
    harness = LiveAcceptanceHarness.load(args.work_dir)
    report = harness.verify(args.evidence)
    print("P3 Telegram live acceptance verification PASSED (synthetic).")
    print(f"  job id: {report['job_id']}")
    print(f"  final state: {report['final_state']}")
    print(f"  instruction: {report['instruction_state']}")
    print(f"  report: {harness.manifest['paths']['report']}")
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    return 0


def command_status(args: argparse.Namespace) -> int:
    harness = LiveAcceptanceHarness.load(args.work_dir)
    snapshot = harness.status()
    if args.json:
        print(json.dumps(snapshot, indent=2, sort_keys=True))
    else:
        print(f"job: {snapshot['job_id']}")
        print(f"state: {snapshot['state']}")
        print(f"monitor running: {snapshot['monitor_running']}")
        print(f"journal entries: {snapshot['journal_entries']}")
        for item in snapshot["owner_messages"]:
            print(
                "owner message: "
                f"{item['delivery_state']} attempt={item['delivered_attempt']} "
                f"token={item['contains_token']}"
            )
        print(f"report: {snapshot['report']}")
    return 0


def command_cleanup(args: argparse.Namespace) -> int:
    harness = LiveAcceptanceHarness.load(args.work_dir)
    harness.cleanup()
    print(f"Removed isolated acceptance work directory: {harness.root}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="p3-live-acceptance",
        description=(
            "Isolated P3 Telegram acceptance harness (synthetic job, real bot). "
            "It does not touch production projects, the live monitor config or Qortium."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare", help="create an isolated synthetic fixture")
    prepare.add_argument("--work-dir", help="empty directory for the fixture")
    prepare.add_argument("--source-config", help="owner telegram.json to copy (never edit)")
    prepare.add_argument("--live-state-dir", help="live monitor state dir to check")
    prepare.add_argument("--instruction", default=DEFAULT_INSTRUCTION)
    prepare.add_argument("--json", action="store_true")
    prepare.set_defaults(func=command_prepare)

    run = subparsers.add_parser("run", help="start the isolated poller against the real bot")
    run.add_argument("--work-dir", required=True)
    run.add_argument("--timeout", type=float, default=900.0)
    run.add_argument("--expect-resume", action="store_true")
    run.add_argument(
        "--confirm-live-telegram",
        action="store_true",
        help="explicit acknowledgement that the live monitor is stopped",
    )
    run.set_defaults(func=command_run)

    verify = subparsers.add_parser("verify", help="verify synthetic state and evidence")
    verify.add_argument("--work-dir", required=True)
    verify.add_argument("--evidence", help="telegram-evidence.json path")
    verify.add_argument("--json", action="store_true")
    verify.set_defaults(func=command_verify)

    status = subparsers.add_parser("status", help="show fixture state")
    status.add_argument("--work-dir", required=True)
    status.add_argument("--json", action="store_true")
    status.set_defaults(func=command_status)

    cleanup = subparsers.add_parser("cleanup", help="remove the isolated fixture")
    cleanup.add_argument("--work-dir", required=True)
    cleanup.set_defaults(func=command_cleanup)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except AcceptanceError as exc:
        print(f"p3-live-acceptance: {exc}", file=sys.stderr)
        return 1
    except ConfigError as exc:
        print(f"p3-live-acceptance: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
