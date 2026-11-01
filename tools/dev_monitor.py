#!/usr/bin/env python3
"""Qortium Dev Monitor (P4 hardened observer plus authorized control).

Commands:
    run              run the long-polling monitor (foreground or systemd user service)
    check            validate configuration, Telegram access, registry and docs roots
    status           show monitor state and whether an instance is running
    stop             request a graceful stop through the monitor's flag file
    hash-passphrase  create a control_passphrase_hash without echoing it

Read-only mode is the default. Start, resume and cancel are available only when the
owner explicitly configures ``monitor.mode = "control"``. Every mutating action
goes through the existing Workflow v3 CLI with fixed arguments and an explicit
confirmation. The monitor never touches Qortium or VPS system configuration.

Run exit codes: 0 graceful stop, 1 unexpected/transient failure, 2 configuration
error, 75 another instance owns the lock, 78 fatal Telegram conflict/auth error.
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
from devmonitor.admission import AdmissionManager  # noqa: E402
from devmonitor.api import TelegramApi, TelegramError, TelegramFatalError  # noqa: E402
from devmonitor.config import (  # noqa: E402
    ConfigError,
    ensure_state_dir,
    load_monitor_config,
    resolve_state_dir,
)
from devmonitor.control import ControlManager  # noqa: E402
from devmonitor.documents import DocumentLibrary, DocumentError  # noqa: E402
from devmonitor.jobs import JobFacade  # noqa: E402
from devmonitor.lifecycle import LifecycleNotifier  # noqa: E402
from devmonitor.passphrase import PassphraseError, hash_passphrase  # noqa: E402
from devmonitor.projects import Registry, RegistryError  # noqa: E402
from devmonitor.render import service_status_text  # noqa: E402
from devmonitor.router import Router  # noqa: E402
from devmonitor.service import (  # noqa: E402
    AlreadyRunning,
    MonitorService,
    MonitorShutdown,
    check_monitor,
    install_shutdown_handlers,
    monitor_running,
    restore_signal_handlers,
)
from devmonitor.state import MonitorState  # noqa: E402
from devmonitor.timings import TimingRecorder  # noqa: E402


def _build_config(args: argparse.Namespace):
    return load_monitor_config(
        args.config,
        state_dir=args.state_dir,
        require_secure=True,
    )


def _build_components(config, timings=None):
    timings = timings or TimingRecorder(slow_seconds=config.slow_timing_seconds)
    state = MonitorState(config.state_dir / "monitor.db", timings=timings)
    api = TelegramApi(
        config.bot_token,
        base_url=config.api_base,
        # Ordinary Bot API calls must not inherit the long-poll timeout.
        timeout_seconds=config.request_timeout_seconds,
        document_timeout_seconds=config.document_timeout_seconds,
        timings=timings,
    )
    registry = Registry(config.registry_path, config.allowed_repo_roots)
    try:
        projects = registry.load(force=True)
    except RegistryError:
        projects = []
    documents = DocumentLibrary.from_sources(config.docs_roots, projects, timings=timings)
    jobs = JobFacade(config.job_state_root, timings=timings)
    admission = AdmissionManager(
        config.state_dir,
        jobs,
        registry,
        lock_timeout=config.admission_lock_timeout_seconds,
        timings=timings,
    )
    lifecycle = LifecycleNotifier(config, state, jobs, api, registry)
    control = ControlManager(
        config, state, jobs, registry, admission, notifier=lifecycle
    )
    router = Router(
        config,
        state,
        api,
        jobs,
        registry,
        documents,
        control=control,
        admission=admission,
        notifier=lifecycle,
        timings=timings,
    )
    return state, api, registry, documents, jobs, router, timings


def command_run(args: argparse.Namespace) -> int:
    config = _build_config(args)
    state, api, _registry, _documents, _jobs, router, timings = _build_components(config)
    service = MonitorService(
        config,
        api,
        state,
        router,
        lifecycle=getattr(router, "lifecycle", None),
        log=lambda message: print(f"monitor: {message}", file=sys.stderr),
        timings=timings,
    )
    previous = install_shutdown_handlers(service)
    try:
        service.run()
    except MonitorShutdown:
        print("dev-monitor: stopped gracefully; running jobs are unaffected", file=sys.stderr)
        return 0
    except AlreadyRunning as exc:
        print(f"dev-monitor: {exc}", file=sys.stderr)
        return 75
    except KeyboardInterrupt:
        print("dev-monitor: interrupted; running jobs are unaffected", file=sys.stderr)
        return 130
    except TelegramFatalError as exc:
        print(f"dev-monitor: stopped: {exc}", file=sys.stderr)
        return 78
    except TelegramError as exc:
        print(f"dev-monitor: stopped: {exc}", file=sys.stderr)
        return 1
    finally:
        restore_signal_handlers(previous)
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
        api = TelegramApi(
            config.bot_token,
            base_url=config.api_base,
            timeout_seconds=config.request_timeout_seconds,
            document_timeout_seconds=config.document_timeout_seconds,
        )
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


def command_hash_passphrase(args: argparse.Namespace) -> int:
    import getpass

    first = getpass.getpass("Control passphrase: ")
    second = getpass.getpass("Repeat passphrase: ")
    if first != second:
        print("dev-monitor: passphrases did not match", file=sys.stderr)
        return 2
    try:
        print(hash_passphrase(first))
    except PassphraseError as exc:
        print(f"dev-monitor: {exc}", file=sys.stderr)
        return 2
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
        description="Qortium Dev Monitor P4 (hardened Telegram observer with explicit control mode).",
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

    hashing = subparsers.add_parser(
        "hash-passphrase", help="create a control_passphrase_hash without echoing it"
    )
    hashing.set_defaults(func=command_hash_passphrase)
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
