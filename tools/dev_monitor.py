#!/usr/bin/env python3
"""Qortium Dev Monitor (P1 read-only observer).

Commands:
    run     start the owner-started foreground long-polling monitor
    check   validate configuration, Telegram access, registry and docs roots
    status  show monitor state and whether an instance is running
    stop    request a graceful stop through the monitor's flag file

The monitor is not a service or scheduler. It never opens an inbound listener,
never creates or mutates Workflow v3 jobs in P1, and never touches Qortium or the
VPS system configuration.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from devmonitor import __version__  # noqa: E402
from devmonitor.api import TelegramApi, TelegramError  # noqa: E402
from devmonitor.config import (  # noqa: E402
    ConfigError,
    ensure_state_dir,
    load_monitor_config,
    resolve_state_dir,
)
from devmonitor.documents import DocumentLibrary, DocumentError  # noqa: E402
from devmonitor.jobs import JobFacade  # noqa: E402
from devmonitor.projects import Registry, RegistryError  # noqa: E402
from devmonitor.render import service_status_text  # noqa: E402
from devmonitor.router import Router  # noqa: E402
from devmonitor.service import (  # noqa: E402
    AlreadyRunning,
    MonitorService,
    check_monitor,
    monitor_running,
)
from devmonitor.state import MonitorState  # noqa: E402


def _build_config(args: argparse.Namespace):
    return load_monitor_config(
        args.config,
        state_dir=args.state_dir,
        require_secure=True,
    )


def _build_components(config):
    state = MonitorState(config.state_dir / "monitor.db")
    api = TelegramApi(
        config.bot_token,
        base_url=config.api_base,
        timeout_seconds=config.poll_timeout_seconds + 10,
    )
    registry = Registry(config.registry_path, config.allowed_repo_roots)
    try:
        projects = registry.load(force=True)
    except RegistryError:
        projects = []
    documents = DocumentLibrary.from_sources(config.docs_roots, projects)
    jobs = JobFacade(config.job_state_root)
    router = Router(config, state, api, jobs, registry, documents)
    return state, api, registry, documents, jobs, router


def command_run(args: argparse.Namespace) -> int:
    config = _build_config(args)
    state, api, _registry, _documents, _jobs, router = _build_components(config)
    service = MonitorService(config, api, state, router, log=lambda message: print(f"monitor: {message}", file=sys.stderr))
    try:
        service.run()
    except AlreadyRunning as exc:
        print(f"dev-monitor: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("dev-monitor: interrupted; running jobs are unaffected", file=sys.stderr)
        return 130
    except TelegramError as exc:
        print(f"dev-monitor: stopped: {exc}", file=sys.stderr)
        return 1
    finally:
        state.close()
    return 0


def command_check(args: argparse.Namespace) -> int:
    try:
        config = _build_config(args)
    except ConfigError as exc:
        print(f"dev-monitor check: FAILED - {exc}")
        return 1
    state = MonitorState(config.state_dir / "monitor.db")
    try:
        api = TelegramApi(config.bot_token, base_url=config.api_base, timeout_seconds=15)
        registry = Registry(config.registry_path, config.allowed_repo_roots)
        try:
            projects = registry.load(force=True)
        except RegistryError:
            projects = []
        documents = DocumentLibrary.from_sources(config.docs_roots, projects)
        ok, lines = check_monitor(config, api, registry, documents)
    finally:
        state.close()
    print("\n".join(lines))
    print("dev-monitor check: " + ("passed" if ok else "FAILED"))
    return 0 if ok else 1


def command_status(args: argparse.Namespace) -> int:
    state_dir = resolve_state_dir(args.state_dir)
    database = state_dir / "monitor.db"
    if database.is_file():
        state = MonitorState(database)
        try:
            snapshot = state.snapshot()
        finally:
            state.close()
    else:
        snapshot = {
            "path": str(database),
            "update_offset": 0,
            "last_poll_at": None,
            "counts": {},
        }
    running = monitor_running(state_dir)
    if args.json:
        print(json.dumps({"running": running, **snapshot}, indent=2, sort_keys=True))
    else:
        print(service_status_text(snapshot, running=running))
    return 0


def command_stop(args: argparse.Namespace) -> int:
    state_dir = ensure_state_dir(resolve_state_dir(args.state_dir))
    stop_path = state_dir / "monitor.stop"
    stop_path.write_text("stop requested from dev_monitor.py stop\n", encoding="utf-8")
    try:
        import os

        os.chmod(stop_path, 0o600)
    except OSError:
        pass
    print(f"Stop requested: {stop_path}")
    if not monitor_running(state_dir):
        print("No running monitor instance was detected; the stale stop flag will be cleared on the next run.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dev-monitor",
        description="Qortium Dev Monitor P1 (read-only Telegram observer).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"dev-monitor {__version__}")
    parser.add_argument("--config", default=None, help="Telegram config path (default: owner-local)")
    parser.add_argument(
        "--state-dir",
        default=None,
        help="monitor state directory (default: $DEV_MONITOR_STATE or Workflow state/monitor)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run", help="run the foreground long-polling monitor")
    run.set_defaults(func=command_run)

    check = subparsers.add_parser("check", help="validate configuration without polling")
    check.set_defaults(func=command_check)

    status = subparsers.add_parser("status", help="show monitor state")
    status.add_argument("--json", action="store_true")
    status.set_defaults(func=command_status)

    stop = subparsers.add_parser("stop", help="request a graceful monitor stop")
    stop.set_defaults(func=command_stop)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except ConfigError as exc:
        print(f"dev-monitor: {exc}", file=sys.stderr)
        return 2
    except (DocumentError, RegistryError) as exc:
        print(f"dev-monitor: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
