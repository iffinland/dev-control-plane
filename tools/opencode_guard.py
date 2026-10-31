#!/usr/bin/env python3
"""Boundary guard for authorized unattended OpenCode executions.

The guard is a short-lived process, not a service. It performs a resource
preflight, optionally runs one command with a wall-clock limit, and terminates
only the process group it created. It never scans for and signals Qortium by
name. Standard library only.

Exit codes:
    0   PASS, or the child exited successfully
    2   usage error
    10  WARN (check mode; run mode continues)
    20  REFUSE
    124 wall-clock timeout
    130 interrupted by SIGINT
    143 terminated by SIGTERM
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence

import session_state


DEFAULT_WORKSPACE = Path("/home/iffi/dev-workspace")
DEFAULT_PROC = Path("/proc")
MAX_TIMEOUT_SECONDS = 8 * 60 * 60
SESSION_POLL_SECONDS = 5.0
SESSION_IDLE_SECONDS = 20.0
SESSION_CONFIRM_SECONDS = 5.0
HEAVY_SUBCOMMANDS = {"run", "serve", "web", "attach", "acp"}
HELPER_SUBCOMMANDS = {
    "stats",
    "models",
    "debug",
    "session",
    "export",
    "import",
    "db",
    "auth",
    "providers",
    "agent",
    "mcp",
    "plugin",
    "completion",
    "upgrade",
    "uninstall",
    "github",
    "pr",
    "--version",
    "-v",
    "--help",
    "-h",
}
GIB = 1024**3
MIB = 1024**2

EXIT_PASS = 0
EXIT_USAGE = 2
EXIT_WARN = 10
EXIT_REFUSE = 20
EXIT_TIMEOUT = 124


class GuardError(RuntimeError):
    """A refusal or an unrecoverable guard condition."""


@dataclass
class ProcessInfo:
    pid: int
    argv: list[str]
    rss_kib: int
    comm: str


@dataclass
class Snapshot:
    available_ram_kib: int
    total_ram_kib: int
    swap_total_kib: int
    swap_free_kib: int
    load1: float
    load5: float
    load15: float
    disk_available_bytes: int
    heavy_opencode: list[ProcessInfo] = field(default_factory=list)
    qortium: list[ProcessInfo] = field(default_factory=list)


@dataclass
class Decision:
    warnings: list[str] = field(default_factory=list)
    refusals: list[str] = field(default_factory=list)

    @property
    def status(self) -> str:
        if self.refusals:
            return "REFUSE"
        if self.warnings:
            return "WARN"
        return "PASS"

    @property
    def exit_code(self) -> int:
        if self.refusals:
            return EXIT_REFUSE
        if self.warnings:
            return EXIT_WARN
        return EXIT_PASS


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise GuardError(f"cannot read {path}: {exc}") from exc


def read_meminfo(proc_root: Path) -> dict[str, int]:
    values: dict[str, int] = {}
    for line in read_text(proc_root / "meminfo").splitlines():
        match = re.match(r"^([A-Za-z_()]+):\s+(\d+)\s+kB$", line)
        if match:
            values[match.group(1)] = int(match.group(2))
    if "MemAvailable" not in values or "MemTotal" not in values:
        raise GuardError(f"meminfo at {proc_root} is missing MemAvailable/MemTotal")
    return values


def read_loadavg(proc_root: Path) -> tuple[float, float, float]:
    fields = read_text(proc_root / "loadavg").split()
    if len(fields) < 3:
        raise GuardError(f"loadavg at {proc_root} is malformed")
    try:
        return float(fields[0]), float(fields[1]), float(fields[2])
    except ValueError as exc:
        raise GuardError(f"loadavg at {proc_root} is not numeric") from exc


def read_swaps(proc_root: Path) -> tuple[int, int]:
    path = proc_root / "swaps"
    if not path.exists():
        return 0, 0
    total = 0
    used = 0
    for line in read_text(path).splitlines()[1:]:
        fields = line.split()
        if len(fields) >= 4 and fields[3].isdigit():
            total += int(fields[2])
            used += int(fields[3])
    return total, max(0, total - used)


def read_cmdline(pid_dir: Path) -> list[str]:
    raw = (pid_dir / "cmdline").read_bytes()
    if not raw:
        return []
    return [part.decode("utf-8", errors="replace") for part in raw.rstrip(b"\0").split(b"\0")]


def read_comm(pid_dir: Path) -> str:
    try:
        return (pid_dir / "comm").read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


def read_rss_kib(pid_dir: Path) -> int:
    try:
        text = (pid_dir / "status").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return 0
    match = re.search(r"^VmRSS:\s+(\d+)\s+kB$", text, re.MULTILINE)
    return int(match.group(1)) if match else 0


def iter_processes(proc_root: Path) -> Iterable[ProcessInfo]:
    try:
        entries = list(proc_root.iterdir())
    except OSError:
        return
    for entry in entries:
        if not entry.name.isdigit():
            continue
        try:
            argv = read_cmdline(entry)
        except OSError:
            continue
        if not argv:
            continue
        yield ProcessInfo(
            pid=int(entry.name),
            argv=argv,
            rss_kib=read_rss_kib(entry),
            comm=read_comm(entry),
        )


def command_is_heavy_opencode(argv: Sequence[str]) -> bool:
    if not argv:
        return False
    if Path(argv[0]).name != "opencode":
        return False
    subcommand = argv[1] if len(argv) > 1 else None
    return subcommand not in HELPER_SUBCOMMANDS


def find_heavy_opencode(
    proc_root: Path,
    min_rss_mib: int,
) -> list[ProcessInfo]:
    threshold = max(0, min_rss_mib) * 1024
    found: list[ProcessInfo] = []
    for process in iter_processes(proc_root):
        if Path(process.argv[0]).name != "opencode":
            continue
        if process.rss_kib < threshold:
            continue
        if command_is_heavy_opencode(process.argv):
            found.append(process)
    return sorted(found, key=lambda process: process.pid)


def find_qortium(proc_root: Path, pattern: str) -> list[ProcessInfo]:
    return sorted(
        (
            process
            for process in iter_processes(proc_root)
            if pattern
            and Path(process.argv[0]).name in {"java", "javaw"}
            and pattern in " ".join(process.argv)
        ),
        key=lambda process: process.pid,
    )


def disk_available_bytes(path: Path) -> int:
    try:
        stats = os.statvfs(path)
    except OSError as exc:
        raise GuardError(f"cannot stat {path}: {exc}") from exc
    return stats.f_bavail * stats.f_frsize


def collect_snapshot(
    workspace: Path,
    proc_root: Path,
    qortium_pattern: str,
    heavy_rss_mib: int,
) -> Snapshot:
    mem = read_meminfo(proc_root)
    load1, load5, load15 = read_loadavg(proc_root)
    swap_total, swap_free = read_swaps(proc_root)
    return Snapshot(
        available_ram_kib=mem["MemAvailable"],
        total_ram_kib=mem["MemTotal"],
        swap_total_kib=swap_total,
        swap_free_kib=swap_free,
        load1=load1,
        load5=load5,
        load15=load15,
        disk_available_bytes=disk_available_bytes(workspace),
        heavy_opencode=find_heavy_opencode(proc_root, heavy_rss_mib),
        qortium=find_qortium(proc_root, qortium_pattern),
    )


def evaluate(
    snapshot: Snapshot,
    warn_ram_gib: float,
    refuse_ram_gib: float,
    warn_load5: float,
    warn_disk_gib: float,
    heavy_command: bool,
) -> Decision:
    decision = Decision()
    available = snapshot.available_ram_kib / MIB
    if available < refuse_ram_gib:
        decision.refusals.append(
            f"available RAM {available:.2f} GiB is below the {refuse_ram_gib:.2f} GiB refusal threshold"
        )
    elif available < warn_ram_gib:
        decision.warnings.append(
            f"available RAM {available:.2f} GiB is below the {warn_ram_gib:.2f} GiB warning threshold"
        )
    if snapshot.load5 > warn_load5:
        decision.warnings.append(
            f"5-minute load average {snapshot.load5:.2f} exceeds the {warn_load5:.2f} warning threshold"
        )
    disk_gib = snapshot.disk_available_bytes / GIB
    if disk_gib < warn_disk_gib:
        decision.warnings.append(
            f"available disk {disk_gib:.2f} GiB is below the {warn_disk_gib:.2f} GiB warning threshold"
        )
    heavy_count = len(snapshot.heavy_opencode)
    if heavy_count > 1:
        decision.refusals.append(
            f"{heavy_count} heavyweight OpenCode executions are already running; maximum is 1"
        )
    elif heavy_count == 1 and heavy_command:
        decision.refusals.append(
            "a heavyweight OpenCode execution is already running; refusing to start a second"
        )
    return decision


def summarize(snapshot: Snapshot, decision: Decision) -> dict[str, object]:
    return {
        "status": decision.status,
        "warnings": decision.warnings,
        "refusals": decision.refusals,
        "available_ram_gib": round(snapshot.available_ram_kib / MIB, 3),
        "total_ram_gib": round(snapshot.total_ram_kib / MIB, 3),
        "swap_total_gib": round(snapshot.swap_total_kib / MIB, 3),
        "swap_free_gib": round(snapshot.swap_free_kib / MIB, 3),
        "load1": snapshot.load1,
        "load5": snapshot.load5,
        "load15": snapshot.load15,
        "disk_available_gib": round(snapshot.disk_available_bytes / GIB, 3),
        "heavy_opencode": [asdict(process) for process in snapshot.heavy_opencode],
        "qortium": [asdict(process) for process in snapshot.qortium],
    }


def print_summary(snapshot: Snapshot, decision: Decision) -> None:
    print(f"opencode-guard: {decision.status}")
    print(
        "  RAM: "
        f"{snapshot.available_ram_kib / MIB:.2f} GiB available of "
        f"{snapshot.total_ram_kib / MIB:.2f} GiB; swap "
        f"{snapshot.swap_total_kib / MIB:.2f} GiB"
    )
    print(f"  load: {snapshot.load1:.2f} {snapshot.load5:.2f} {snapshot.load15:.2f}")
    print(f"  disk: {snapshot.disk_available_bytes / GIB:.2f} GiB available")
    print(f"  heavyweight OpenCode: {len(snapshot.heavy_opencode)} (maximum 1)")
    for process in snapshot.heavy_opencode:
        print(f"    pid {process.pid} rss {process.rss_kib / 1024:.0f} MiB: {shlex.join(process.argv)}")
    if snapshot.qortium:
        for process in snapshot.qortium:
            print(f"  Qortium (read-only): pid {process.pid} rss {process.rss_kib / 1024:.0f} MiB")
    else:
        print("  Qortium (read-only): not detected")
    for warning in decision.warnings:
        print(f"  WARN: {warning}")
    for refusal in decision.refusals:
        print(f"  REFUSE: {refusal}")


def parse_duration(value: str) -> int:
    match = re.fullmatch(r"(\d+)([smh]?)", value.strip())
    if not match:
        raise argparse.ArgumentTypeError("duration must be an integer followed by s, m or h")
    amount = int(match.group(1))
    unit = match.group(2) or "s"
    seconds = amount * {"s": 1, "m": 60, "h": 3600}[unit]
    if seconds <= 0:
        raise argparse.ArgumentTypeError("duration must be greater than zero")
    if seconds > MAX_TIMEOUT_SECONDS:
        raise argparse.ArgumentTypeError("duration exceeds the eight-hour maximum")
    return seconds


class GuardLock:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.handle = None

    def __enter__(self) -> "GuardLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            self.handle.close()
            self.handle = None
            raise GuardError(f"another guard holds {self.path}") from exc
        self.handle.seek(0)
        self.handle.truncate()
        self.handle.write(f"pid={os.getpid()} started={utc_now()}\n")
        self.handle.flush()
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        if self.handle is not None:
            try:
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
            finally:
                self.handle.close()
                self.handle = None


class SessionCompletionWatcher(threading.Thread):
    """Observe structured session state for a definite end of the agent turn.

    OpenCode can keep the ``run`` process alive after it has already emitted the
    final assistant message. This watcher never signals a process. It only
    produces evidence that the current attempt's turn is finished:

    - the newest message created during this attempt is assistant ``finish=stop``;
    - it has no error;
    - no tool call created during this attempt is pending or running;
    - the session has been quiescent for an idle window; and
    - two consecutive observations agree.

    The guard's main loop decides whether to stop the process group it created.
    Acceptance criteria are still verified separately; completion is not success.
    """

    def __init__(
        self,
        *,
        session_id: str | None,
        session_title: str | None,
        cwd: str | Path | None,
        since_ms: int,
        poll_seconds: float,
        idle_seconds: float,
        confirm_seconds: float,
        export_timeout: int,
        log,
    ) -> None:
        super().__init__(name="session-completion", daemon=True)
        self.session_id = session_id
        self.session_title = session_title
        self.cwd = cwd
        self.since_ms = since_ms
        self.poll_seconds = max(0.05, poll_seconds)
        self.idle_seconds = max(0.0, idle_seconds)
        self.confirm_seconds = max(0.0, confirm_seconds)
        self.export_timeout = max(1, export_timeout)
        self.log = log
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._evidence: dict | None = None
        self._pending: dict | None = None
        self._pending_since: float | None = None
        self._last_updated: int | None = None
        self._last_exported_updated: int | None = None
        self._stable_since: float | None = None
        self._last_error: str | None = None

    def stop(self) -> None:
        self._stop.set()

    def current_evidence(self) -> dict | None:
        with self._lock:
            return dict(self._evidence) if self._evidence else None

    def clear_evidence(self) -> None:
        with self._lock:
            self._evidence = None
            self._pending = None
            self._pending_since = None
            # Force the next tick to re-read the session instead of skipping it
            # as already inspected.
            self._last_exported_updated = None

    def _log(self, message: str) -> None:
        try:
            self.log.write(f"guard: {message}\n")
            self.log.flush()
        except (OSError, ValueError):
            pass

    def _resolve_session(self) -> bool:
        if self.session_id:
            return True
        if not self.session_title:
            return False
        sessions = session_state.list_sessions(
            cwd=self.cwd,
            timeout=min(self.export_timeout, session_state.SESSION_LIST_TIMEOUT),
        )
        session_id = session_state.discover_session_id(sessions, title=self.session_title)
        if not session_id:
            return False
        self.session_id = session_id
        self._log(f"session completion watcher attached to {session_id}")
        return True

    def _list_updated(self) -> int | None:
        sessions = session_state.list_sessions(
            cwd=self.cwd,
            timeout=min(self.export_timeout, session_state.SESSION_LIST_TIMEOUT),
        )
        if sessions is None or not self.session_id:
            return None
        return session_state.session_updated_from_list(sessions, self.session_id)

    def _tick(self) -> None:
        if not self._resolve_session():
            return
        now = time.monotonic()
        updated = self._list_updated()
        if updated is not None:
            if self._last_updated != updated:
                self._last_updated = updated
                self._stable_since = now
                self._pending = None
                self._pending_since = None
                self.clear_evidence()
            elif self._stable_since is None:
                self._stable_since = now
            if now - (self._stable_since or now) < self.idle_seconds:
                return
            if self._pending is None and self._last_exported_updated == updated:
                return

        payload = session_state.load_export(
            self.session_id,
            cwd=self.cwd,
            timeout=self.export_timeout,
        )
        if payload is None:
            self._pending = None
            self._pending_since = None
            return
        if updated is not None:
            self._last_exported_updated = updated
        else:
            exported_updated = session_state.session_updated_ms(payload)
            if exported_updated is not None:
                self._last_exported_updated = exported_updated
        evidence = session_state.completion_evidence(payload, since_ms=self.since_ms)
        if not evidence:
            self._pending = None
            self._pending_since = None
            return
        if self._pending is None or evidence.get("message_id") != self._pending.get("message_id"):
            self._pending = evidence
            self._pending_since = now
            self._log(
                "session completion candidate "
                f"message={evidence.get('message_id')} finish=stop; awaiting confirmation"
            )
            return
        if now - (self._pending_since or now) < self.confirm_seconds:
            return
        evidence = dict(evidence)
        evidence["idle_seconds"] = round(now - (self._stable_since or now), 1)
        evidence["confirmed_seconds"] = round(now - (self._pending_since or now), 1)
        with self._lock:
            self._evidence = evidence
        self._pending = None
        self._pending_since = None
        self._log(
            "session completion confirmed "
            f"message={evidence.get('message_id')} idle={evidence['idle_seconds']}s"
        )

    def confirm_now(self) -> dict | None:
        """Re-read the session immediately before the main loop stops the child."""
        if not self.session_id:
            return None
        payload = session_state.load_export(
            self.session_id,
            cwd=self.cwd,
            timeout=self.export_timeout,
        )
        evidence = session_state.completion_evidence(payload, since_ms=self.since_ms)
        if not evidence:
            return None
        with self._lock:
            self._evidence = dict(evidence)
        return dict(evidence)

    def run(self) -> None:
        while not self._stop.wait(self.poll_seconds):
            try:
                self._tick()
            except Exception as exc:  # noqa: BLE001 - watcher must not kill the run
                message = f"{exc.__class__.__name__}: {exc}"
                if message != self._last_error:
                    self._last_error = message
                    self._log(f"session completion watcher error: {message}")


def write_completion_file(path: Path, evidence: dict, action: str) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = dict(evidence)
        payload["action"] = action
        payload["written_utc"] = utc_now()
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        temporary.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    except OSError:
        pass


def group_alive(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def assert_safe_target(pgid: int, qortium_pids: set[int]) -> None:
    if pgid <= 1:
        raise GuardError(f"refusing to signal unsafe process group {pgid}")
    if pgid in qortium_pids:
        raise GuardError(f"refusing to signal the Qortium process group {pgid}")
    if pgid == os.getpgrp():
        raise GuardError("refusing to signal the guard's own process group")


def stop_group(
    process: subprocess.Popen[str],
    grace_seconds: float,
    qortium_pids: set[int],
    log,
) -> None:
    pgid = process.pid
    assert_safe_target(pgid, qortium_pids)
    log.write(f"guard: sending SIGTERM to process group {pgid}\n")
    log.flush()
    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    deadline = time.monotonic() + grace_seconds
    while time.monotonic() < deadline and group_alive(pgid):
        time.sleep(0.1)
    if group_alive(pgid):
        log.write(f"guard: process group {pgid} still alive; sending SIGKILL\n")
        log.flush()
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        log.write("guard: child did not reap after SIGKILL\n")
        log.flush()


def pump_output(stream, log) -> None:
    try:
        for line in iter(stream.readline, ""):
            sys.stdout.write(line)
            sys.stdout.flush()
            log.write(line)
            log.flush()
    except Exception as exc:
        log.write(f"guard: output pump error: {exc}\n")
        log.flush()
    finally:
        try:
            stream.close()
        except OSError:
            pass


def session_hint(log) -> None:
    executable = shutil.which("opencode")
    if not executable:
        return
    try:
        result = subprocess.run(
            [executable, "session", "list", "--format", "json", "--max-count", "5"],
            text=True,
            capture_output=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.write(f"guard: could not list OpenCode sessions: {exc}\n")
        log.flush()
        return
    if result.returncode == 0 and result.stdout.strip():
        log.write("guard: recent OpenCode sessions (resume with --session <id>):\n")
        log.write(result.stdout.rstrip() + "\n")
    else:
        log.write("guard: session list unavailable; use `opencode session list` manually\n")
    log.flush()


def command_for_log(argv: Sequence[str]) -> str:
    try:
        return shlex.join(argv)
    except TypeError:
        return " ".join(argv)


def write_pid_file(path: Path, pid: int, log) -> None:
    """Record the child PID/PGID for external status readers.

    The file is evidence only. The guard never reads it back to decide which
    process group to signal; it always uses the Popen handle it created.
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "pid": pid,
            "pgid": pid,
            "started_utc": utc_now(),
        }
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        temporary.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temporary, path)
        log.write(f"guard: wrote pid file {path}\n")
        log.flush()
    except OSError as exc:
        log.write(f"guard: could not write pid file {path}: {exc}\n")
        log.flush()


def run_command(args: argparse.Namespace, command: list[str]) -> int:
    heavy_command = command_is_heavy_opencode(command)
    snapshot = collect_snapshot(
        args.workspace,
        args.proc_root,
        args.qortium_pattern,
        args.heavy_rss_mib,
    )
    decision = evaluate(
        snapshot,
        args.warn_ram_gib,
        args.refuse_ram_gib,
        args.warn_load5,
        args.warn_disk_gib,
        heavy_command,
    )
    print_summary(snapshot, decision)
    if decision.refusals:
        return EXIT_REFUSE

    lock_path = args.lock_file or (args.workspace / "logs/opencode-guard.lock")
    log_path = args.log or (
        args.workspace
        / "logs"
        / f"opencode-guard-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.log"
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with GuardLock(lock_path):
            snapshot = collect_snapshot(
                args.workspace,
                args.proc_root,
                args.qortium_pattern,
                args.heavy_rss_mib,
            )
            decision = evaluate(
                snapshot,
                args.warn_ram_gib,
                args.refuse_ram_gib,
                args.warn_load5,
                args.warn_disk_gib,
                heavy_command,
            )
            if decision.refusals:
                print_summary(snapshot, decision)
                return EXIT_REFUSE

            qortium_pids = {process.pid for process in snapshot.qortium}
            stop_signal: dict[str, int | None] = {"value": None}

            def handle_signal(signum, frame) -> None:
                stop_signal["value"] = signum

            previous_handlers = {}
            for sig in (signal.SIGINT, signal.SIGTERM):
                previous_handlers[sig] = signal.signal(sig, handle_signal)

            with log_path.open("a", encoding="utf-8", errors="replace") as log:
                log.write("=== opencode-guard ===\n")
                log.write(f"started_utc={utc_now()}\n")
                log.write(f"cwd={Path.cwd()}\n")
                log.write(f"command={command_for_log(command)}\n")
                log.write(f"timeout_seconds={args.timeout}\n")
                log.write(f"lock_file={lock_path}\n")
                log.write(f"heavy_command={heavy_command}\n")
                log.write(f"snapshot_before={json.dumps(summarize(snapshot, decision), sort_keys=True)}\n")
                log.flush()

                completion_since_ms = int(time.time() * 1000)
                try:
                    process = subprocess.Popen(
                        command,
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        text=True,
                        bufsize=1,
                        start_new_session=True,
                    )
                except OSError as exc:
                    log.write(f"guard: cannot start command: {exc}\n")
                    log.flush()
                    return EXIT_REFUSE
                if args.pid_file is not None:
                    write_pid_file(args.pid_file, process.pid, log)
                assert process.stdout is not None
                pump = threading.Thread(
                    target=pump_output,
                    args=(process.stdout, log),
                    daemon=True,
                )
                pump.start()

                watcher: SessionCompletionWatcher | None = None
                if (args.session_id or args.session_title) and args.session_poll_seconds > 0:
                    watcher = SessionCompletionWatcher(
                        session_id=args.session_id,
                        session_title=args.session_title,
                        cwd=Path.cwd(),
                        since_ms=completion_since_ms,
                        poll_seconds=args.session_poll_seconds,
                        idle_seconds=args.session_idle_seconds,
                        confirm_seconds=args.session_confirm_seconds,
                        export_timeout=args.session_export_timeout,
                        log=log,
                    )
                    watcher.start()

                started = time.monotonic()
                deadline = started + args.timeout
                reason = "exit"
                exit_code = 0
                completion: dict | None = None
                try:
                    while True:
                        polled = process.poll()
                        if polled is not None:
                            exit_code = polled
                            reason = "exit"
                            break
                        if stop_signal["value"] is not None:
                            reason = "signal"
                            break
                        if watcher is not None and watcher.current_evidence():
                            evidence = watcher.confirm_now()
                            if evidence:
                                completion = evidence
                                reason = "complete"
                                break
                            # The session changed between observations. Keep
                            # waiting instead of stopping potentially active work.
                            watcher.clear_evidence()
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            reason = "timeout"
                            break
                        try:
                            exit_code = process.wait(timeout=min(1.0, remaining))
                            reason = "exit"
                            break
                        except subprocess.TimeoutExpired:
                            continue
                finally:
                    if watcher is not None:
                        watcher.stop()
                        watcher.join(timeout=2)
                    if reason != "exit":
                        log.write(f"guard: {reason} after {time.monotonic() - started:.1f}s\n")
                        log.flush()
                        stop_group(process, args.term_grace, qortium_pids, log)
                    for sig, handler in previous_handlers.items():
                        signal.signal(sig, handler)

                pump.join(timeout=3)
                duration = time.monotonic() - started
                if reason == "complete":
                    exit_code = 0
                    evidence = completion or {}
                    log.write(
                        "guard: SESSION_COMPLETE exit=0 "
                        f"message={evidence.get('message_id')} "
                        f"finish={evidence.get('finish')} active_tools=0 duration={duration:.1f}s\n"
                    )
                    log.write(
                        "guard: session completion is not acceptance; "
                        "acceptance criteria and failure detectors still decide the job state\n"
                    )
                    log.flush()
                    if args.completion_file is not None:
                        write_completion_file(
                            args.completion_file,
                            evidence,
                            "session_completed_cli_stopped",
                        )
                        log.write(f"guard: wrote completion evidence {args.completion_file}\n")
                        log.flush()
                elif reason == "timeout":
                    exit_code = EXIT_TIMEOUT
                    log.write(f"guard: TIMEOUT exit={exit_code} duration={duration:.1f}s\n")
                    log.write("guard: no graceful checkpoint is guaranteed; session history is preserved\n")
                    log.flush()
                    if heavy_command:
                        session_hint(log)
                elif reason == "signal":
                    signum = int(stop_signal["value"] or signal.SIGTERM)
                    exit_code = 128 + signum
                    log.write(f"guard: SIGNAL={signum} exit={exit_code} duration={duration:.1f}s\n")
                    log.flush()
                    if heavy_command:
                        session_hint(log)
                else:
                    log.write(f"guard: child exit={exit_code} duration={duration:.1f}s\n")
                    if exit_code == 0:
                        log.write(
                            "guard: exit 0 is not acceptance; require the task report, expected diff and checks\n"
                        )
                    log.flush()
                try:
                    after = collect_snapshot(
                        args.workspace,
                        args.proc_root,
                        args.qortium_pattern,
                        args.heavy_rss_mib,
                    )
                    after_decision = evaluate(
                        after,
                        args.warn_ram_gib,
                        args.refuse_ram_gib,
                        args.warn_load5,
                        args.warn_disk_gib,
                        heavy_command,
                    )
                    log.write(
                        f"snapshot_after={json.dumps(summarize(after, after_decision), sort_keys=True)}\n"
                    )
                except GuardError as exc:
                    log.write(f"guard: could not collect post-run snapshot: {exc}\n")
                log.write(f"log={log_path}\n")
                log.write("=== end ===\n")
                log.flush()
                return exit_code
    except GuardError as exc:
        print(f"opencode-guard: REFUSE: {exc}", file=sys.stderr)
        return EXIT_REFUSE


def check_command(args: argparse.Namespace) -> int:
    snapshot = collect_snapshot(
        args.workspace,
        args.proc_root,
        args.qortium_pattern,
        args.heavy_rss_mib,
    )
    decision = evaluate(
        snapshot,
        args.warn_ram_gib,
        args.refuse_ram_gib,
        args.warn_load5,
        args.warn_disk_gib,
        False,
    )
    if args.json:
        print(json.dumps(summarize(snapshot, decision), indent=2, sort_keys=True))
    else:
        print_summary(snapshot, decision)
    return decision.exit_code


def add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--workspace",
        type=Path,
        default=DEFAULT_WORKSPACE,
        help="workspace used for disk checks and default logs (default: %(default)s)",
    )
    parser.add_argument(
        "--proc-root",
        type=Path,
        default=DEFAULT_PROC,
        help="procfs root for memory, load and process inspection (default: %(default)s)",
    )
    parser.add_argument("--warn-ram-gib", type=float, default=3.0)
    parser.add_argument("--refuse-ram-gib", type=float, default=1.5)
    parser.add_argument("--warn-load5", type=float, default=5.0)
    parser.add_argument("--warn-disk-gib", type=float, default=20.0)
    parser.add_argument("--heavy-rss-mib", type=int, default=128)
    parser.add_argument("--qortium-pattern", default="qortium.jar")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Boundary guard for authorized unattended OpenCode executions.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="mode", required=True)

    check = subparsers.add_parser("check", help="run a resource and one-session preflight")
    add_common_arguments(check)
    check.add_argument("--json", action="store_true", help="print machine-readable JSON")
    check.set_defaults(func=check_command)

    run = subparsers.add_parser("run", help="run one command with preflight and a wall-clock limit")
    add_common_arguments(run)
    run.add_argument(
        "--timeout",
        type=parse_duration,
        default=MAX_TIMEOUT_SECONDS,
        help="wall-clock limit, e.g. 8h, 480m or 28800s (maximum 8h; default 8h)",
    )
    run.add_argument("--log", type=Path, default=None, help="log path (default: workspace/logs/...)")
    run.add_argument("--lock-file", type=Path, default=None)
    run.add_argument("--pid-file", type=Path, default=None, help="write the child PID/PGID as JSON")
    run.add_argument(
        "--completion-file",
        type=Path,
        default=None,
        help="write structured session-completion evidence as JSON",
    )
    run.add_argument("--session-id", default=None, help="OpenCode session id to watch for completion")
    run.add_argument(
        "--session-title",
        default=None,
        help="OpenCode session title used to discover the session id for a new run",
    )
    run.add_argument(
        "--session-poll-seconds",
        type=float,
        default=SESSION_POLL_SECONDS,
        help="poll interval for the completion watcher (0 disables it)",
    )
    run.add_argument(
        "--session-idle-seconds",
        type=float,
        default=SESSION_IDLE_SECONDS,
        help="required session quiescence before checking structured completion",
    )
    run.add_argument(
        "--session-confirm-seconds",
        type=float,
        default=SESSION_CONFIRM_SECONDS,
        help="delay between the two agreeing completion observations",
    )
    run.add_argument(
        "--session-export-timeout",
        type=int,
        default=session_state.SESSION_EXPORT_TIMEOUT,
        help="timeout for opencode export during completion checks",
    )
    run.add_argument("--term-grace", type=float, default=10.0, help="seconds before SIGKILL")
    run.add_argument("command", nargs=argparse.REMAINDER)
    run.set_defaults(func=run_command)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    command = getattr(args, "command", [])
    if args.mode == "run":
        if command and command[0] == "--":
            command = command[1:]
        if not command:
            parser.error("run requires a command after --")
    try:
        return int(args.func(args, command) if args.mode == "run" else args.func(args))
    except GuardError as exc:
        print(f"opencode-guard: REFUSE: {exc}", file=sys.stderr)
        return EXIT_REFUSE
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
