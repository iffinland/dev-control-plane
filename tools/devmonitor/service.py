"""Single-instance polling loop for the Qortium Dev Monitor.

The service is owner-started in the foreground. It uses outbound long polling,
persists the next offset only after an update is handled or dead-lettered, and
stops through a flag file. It never installs a service, starts a listener or
signals processes by name.
"""

from __future__ import annotations

import fcntl
import os
import signal
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .api import (
    TelegramApi,
    TelegramFatalError,
    TelegramRateLimited,
    TelegramTransientError,
    backoff_seconds,
)
from .config import MonitorConfig, ensure_state_dir
from .redact import redact_error, redact_text
from .state import MonitorState
from .timings import TimingRecorder, default_recorder


class AlreadyRunning(RuntimeError):
    """Another monitor instance holds the state lock."""


class MonitorShutdown(BaseException):
    """Raised by the signal handler to interrupt a blocking poll safely."""

    def __init__(self, signum: int) -> None:
        super().__init__(signum)
        self.signum = signum


def install_shutdown_handlers(service: "MonitorService") -> dict[int, object]:
    """Install SIGTERM/SIGINT handlers that end the loop without a traceback."""

    previous: dict[int, object] = {}

    def _handle(signum: int, _frame: object) -> None:
        service.mark_shutdown(signum)
        raise MonitorShutdown(signum)

    for signum in (signal.SIGTERM, signal.SIGINT):
        previous[signum] = signal.signal(signum, _handle)
    return previous


def restore_signal_handlers(previous: dict[int, object]) -> None:
    for signum, handler in previous.items():
        try:
            signal.signal(signum, handler)  # type: ignore[arg-type]
        except (OSError, ValueError):
            pass


class MonitorService:
    def __init__(
        self,
        config: MonitorConfig,
        api: TelegramApi,
        state: MonitorState,
        router,
        *,
        lifecycle=None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        log: Callable[[str], None] | None = None,
        timings: TimingRecorder | None = None,
    ) -> None:
        self.config = config
        self.api = api
        self.state = state
        self.router = router
        self.lifecycle = lifecycle
        self.sleep = sleep
        self.clock = clock
        self.log = log or (lambda _message: None)
        self.timings = timings or default_recorder()
        self._last_lifecycle: float | None = None
        self._shutdown_requested = False
        self.state_dir = ensure_state_dir(config.state_dir)
        self.lock_path = self.state_dir / "monitor.lock"
        self.stop_path = self.state_dir / "monitor.stop"
        self._lock_handle = None

    # ---- single instance and stop flag ------------------------------------------
    def _acquire_lock(self) -> None:
        handle = self.lock_path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            handle.close()
            raise AlreadyRunning("another Qortium Dev Monitor instance is already running") from exc
        handle.seek(0)
        handle.truncate()
        handle.write(f"pid={os.getpid()} started={int(time.time())}\n")
        handle.flush()
        try:
            os.chmod(self.lock_path, 0o600)
        except OSError:
            pass
        self._lock_handle = handle

    def _release_lock(self) -> None:
        handle = self._lock_handle
        self._lock_handle = None
        if handle is None:
            return
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()

    def stop_requested(self) -> bool:
        return self._shutdown_requested or self.stop_path.exists()

    def mark_shutdown(self, signum: int) -> None:
        self._shutdown_requested = True
        self.log(f"shutdown requested by signal {signum}")

    def _emit_timings(self) -> None:
        for line in self.timings.drain_log_lines():
            self.log(line)

    def request_stop(self) -> None:
        ensure_state_dir(self.state_dir)
        self.stop_path.write_text(f"stop requested at {int(time.time())}\n", encoding="utf-8")
        try:
            os.chmod(self.stop_path, 0o600)
        except OSError:
            pass

    def clear_stop(self) -> None:
        try:
            self.stop_path.unlink()
        except FileNotFoundError:
            pass

    # ---- loop --------------------------------------------------------------------
    def run(self, max_iterations: int | None = None) -> None:
        self._acquire_lock()
        self.clear_stop()
        iterations = 0
        transient_attempt = 0
        try:
            while not self.stop_requested():
                if max_iterations is not None and iterations >= max_iterations:
                    break
                iterations += 1
                self._emit_timings()
                updates: list[dict] = []
                try:
                    with self.timings.measure("poll:getUpdates"):
                        updates = self.api.get_updates(
                            self.state.next_offset(), self.config.poll_timeout_seconds
                        )
                    transient_attempt = 0
                    # Answer all queued callbacks before any handler can block the
                    # loop. Otherwise a slow first action expires the rest.
                    with self.timings.measure("ack:batch"):
                        self.router.acknowledge_updates(updates)
                    self._emit_timings()
                    for update in updates:
                        if self.stop_requested():
                            break
                        kind = _update_kind(update)
                        with self.timings.measure(f"update:{kind}"):
                            self.process_update(update)
                        self._emit_timings()
                    with self.timings.measure("sqlite:prune"):
                        self.state.prune(
                            owner_message_retention_seconds=(
                                self.config.owner_message_retention_seconds
                            )
                        )
                    self._poll_lifecycle()
                except TelegramRateLimited as exc:
                    delay = max(1.0, exc.retry_after)
                    self.log(f"rate limited; waiting {delay:.0f}s")
                    self.sleep(delay)
                except TelegramTransientError as exc:
                    transient_attempt += 1
                    delay = backoff_seconds(transient_attempt)
                    self.log(f"transient Telegram error; retrying in {delay:.1f}s")
                    self.sleep(delay)
                except TelegramFatalError:
                    raise
                # A long poll normally already waited; only add an idle pause when
                # Telegram returned an empty batch immediately.
                if not updates:
                    self.sleep(0.1)
        finally:
            self._emit_timings()
            self._release_lock()

    def _poll_lifecycle(self) -> None:
        if self.lifecycle is None:
            return
        now = self.clock()
        if (
            self._last_lifecycle is not None
            and now - self._last_lifecycle < self.config.lifecycle_poll_seconds
        ):
            return
        self._last_lifecycle = now
        try:
            with self.timings.measure("lifecycle:poll"):
                self.lifecycle.poll()
        except Exception as exc:  # noqa: BLE001 - lifecycle must not stop polling
            self.log(f"lifecycle poll failed: {exc.__class__.__name__}")

    def process_update(self, update: dict) -> None:
        if not isinstance(update, dict):
            return
        update_id = update.get("update_id")
        if isinstance(update_id, bool) or not isinstance(update_id, int):
            return
        if not self.state.claim_update(update_id):
            # The action already ran. Stop the spinner for a callback that was
            # never acknowledged in this process, but never re-run the action.
            self.router.acknowledge_update(update)
            self.state.set_offset(update_id + 1)
            return
        try:
            self.router.handle(update)
        except (TelegramRateLimited, TelegramTransientError, TelegramFatalError) as exc:
            # The update was claimed before dispatch. A handler may already have
            # committed a state change or an action before the outbound Telegram
            # call failed. Releasing the claim would replay the whole action on
            # retry and could duplicate a wizard transition, queued instruction or
            # job action. Keep the durable claim, advance past the update, and let
            # the loop back off; a later redelivery is acknowledged only.
            self.state.set_offset(update_id + 1)
            if isinstance(exc, TelegramTransientError):
                self.state.record_audit(
                    "update_transient",
                    "error",
                    update_id=update_id,
                    detail=redact_error(exc, self.config.secrets),
                )
                self.log(
                    f"transient Telegram error while handling update {update_id}: "
                    f"{redact_error(exc, self.config.secrets)}"
                )
            raise
        except Exception as exc:  # noqa: BLE001 - dead-letter one bad update
            self.state.record_audit(
                "update_dead_letter",
                "error",
                update_id=update_id,
                detail=redact_error(exc, self.config.secrets),
            )
            self.log(f"dead-lettered update {update_id}: {redact_error(exc, self.config.secrets)}")
            self.state.set_offset(update_id + 1)
            return
        self.state.set_offset(update_id + 1)


def _update_kind(update: object) -> str:
    if not isinstance(update, dict):
        return "unsupported"
    if isinstance(update.get("callback_query"), dict):
        return "callback_query"
    if isinstance(update.get("message"), dict):
        return "message"
    return "unsupported"


def monitor_running(state_dir: str | Path) -> bool:
    directory = ensure_state_dir(state_dir)
    lock_path = directory / "monitor.lock"
    if not lock_path.exists():
        return False
    try:
        handle = lock_path.open("a+", encoding="utf-8")
    except OSError:
        return False
    try:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        return False
    finally:
        handle.close()


@dataclass(frozen=True)
class MonitorInstance:
    """Observed state of the monitor's single-instance lock.

    ``state`` is one of ``stopped``, ``stale``, ``running``, ``competing`` or
    ``unknown``. Only ``running`` proves a live, verified monitor owns the lock;
    only ``stopped`` and ``stale`` are ready for a new monitor to start.
    """

    state: str
    lock_path: Path
    lock_present: bool
    pid: int | None = None
    started: int | None = None
    holder_pid: int | None = None
    competing_pids: tuple[int, ...] = ()
    detail: str = ""

    @property
    def running(self) -> bool:
        return self.state == "running"

    @property
    def healthy(self) -> bool:
        return self.state == "running"

    @property
    def start_ready(self) -> bool:
        return self.state in {"stopped", "stale"}


def _read_lock_metadata(lock_path: Path) -> tuple[int | None, int | None]:
    try:
        text = lock_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None, None
    pid: int | None = None
    started: int | None = None
    for token in text.split():
        key, separator, value = token.partition("=")
        if not separator:
            continue
        try:
            number = int(value)
        except ValueError:
            continue
        if number <= 0:
            continue
        if key == "pid":
            pid = number
        elif key == "started":
            started = number
    return pid, started


def _process_state(pid: int) -> str | None:
    """Return the Linux process state letter, or None when it is not running."""

    try:
        raw = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    close = raw.rfind(")")
    if close < 0:
        return None
    fields = raw[close + 1 :].split()
    return fields[0] if fields else None


def _process_cmdline(pid: int) -> list[str]:
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return []
    return [
        part.decode("utf-8", "replace") for part in raw.split(b"\0") if part
    ]


def _process_environ(pid: int) -> dict[str, str]:
    try:
        raw = Path(f"/proc/{pid}/environ").read_bytes()
    except OSError:
        return {}
    result: dict[str, str] = {}
    for item in raw.split(b"\0"):
        key, separator, value = item.partition(b"=")
        if not separator:
            continue
        result[key.decode("utf-8", "replace")] = value.decode("utf-8", "replace")
    return result


def _is_monitor_command(argv: list[str]) -> bool:
    if not argv:
        return False
    executable = any(Path(item).name == "dev_monitor.py" for item in argv)
    return executable and "run" in argv[1:]


def _declared_state_dir(argv: list[str], environ: dict[str, str]) -> Path | None:
    for index, item in enumerate(argv):
        if item == "--state-dir" and index + 1 < len(argv):
            return Path(argv[index + 1]).expanduser().resolve(strict=False)
        if item.startswith("--state-dir="):
            return Path(item.split("=", 1)[1]).expanduser().resolve(strict=False)
    value = environ.get("DEV_MONITOR_STATE")
    if value:
        return Path(value).expanduser().resolve(strict=False)
    control_state = environ.get("DEV_CONTROL_PLANE_STATE")
    if control_state:
        return (Path(control_state).expanduser() / "monitor").resolve(strict=False)
    xdg_state = environ.get("XDG_STATE_HOME")
    if xdg_state:
        return (
            Path(xdg_state).expanduser() / "dev-control-plane" / "monitor"
        ).resolve(strict=False)
    return (Path.home() / ".local/state/dev-control-plane/monitor").resolve(
        strict=False
    )


def _lock_holder_pids(lock_path: Path) -> tuple[int, ...]:
    """Return the PIDs that actually hold the lock according to /proc/locks."""

    try:
        info = lock_path.stat()
        lines = Path("/proc/locks").read_text(
            encoding="utf-8", errors="replace"
        ).splitlines()
    except OSError:
        return ()
    holders: set[int] = set()
    for line in lines:
        fields = line.split()
        # A leading ``->`` marks a waiting lock request, not a granted holder.
        if "->" in fields:
            continue
        for index, token in enumerate(fields):
            pieces = token.split(":")
            if len(pieces) != 3:
                continue
            try:
                major = int(pieces[0], 16)
                minor = int(pieces[1], 16)
                inode = int(pieces[2], 10)
                pid = int(fields[index - 1])
            except (IndexError, ValueError):
                continue
            if pid <= 0:
                continue
            if inode != info.st_ino:
                continue
            if major != os.major(info.st_dev) or minor != os.minor(info.st_dev):
                continue
            holders.add(pid)
    return tuple(sorted(holders))


def _monitor_pids_for_state_dir(directory: Path) -> tuple[int, ...]:
    target = directory.resolve(strict=False)
    matches: set[int] = set()
    try:
        entries = list(Path("/proc").iterdir())
    except OSError:
        return ()
    for entry in entries:
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        state = _process_state(pid)
        if state is None or state in {"Z", "X"}:
            continue
        argv = _process_cmdline(pid)
        if not _is_monitor_command(argv):
            continue
        declared = _declared_state_dir(argv, _process_environ(pid))
        if declared == target:
            matches.add(pid)
    return tuple(sorted(matches))


def inspect_monitor_instance(state_dir: str | Path) -> MonitorInstance:
    """Inspect the single-instance lock without signalling any process.

    The result separates "can a new monitor start?" from "is the already running
    monitor healthy?". A missing lock is ``stopped``; an unheld lock file is
    ``stale``; a lock held by a verified live ``dev_monitor.py run`` process is
    ``running``; a lock held by anything that cannot be verified is ``unknown``;
    and more than one monitor process targeting the same state directory is
    ``competing``. Unknown and competing states fail closed.
    """

    directory = ensure_state_dir(state_dir)
    lock_path = directory / "monitor.lock"
    if not lock_path.exists():
        return MonitorInstance("stopped", lock_path, False)
    claimed_pid, claimed_started = _read_lock_metadata(lock_path)
    try:
        handle = lock_path.open("a+", encoding="utf-8")
    except OSError as exc:
        return MonitorInstance(
            "unknown",
            lock_path,
            True,
            claimed_pid,
            claimed_started,
            detail=f"lock file cannot be inspected: {exc.__class__.__name__}",
        )
    held = False
    try:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            held = True
        else:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()
    if not held:
        return MonitorInstance(
            "stale",
            lock_path,
            True,
            claimed_pid,
            claimed_started,
            detail="lock file is not held by a live process",
        )
    holders = _lock_holder_pids(lock_path)
    if len(holders) != 1:
        if not holders:
            detail = "lock is held but its owner could not be verified"
        else:
            detail = "lock has multiple verified holders: pids=" + ",".join(
                str(pid) for pid in holders
            )
        return MonitorInstance(
            "unknown",
            lock_path,
            True,
            claimed_pid,
            claimed_started,
            competing_pids=holders,
            detail=detail,
        )
    holder = holders[0]
    process_state = _process_state(holder)
    if process_state is None or process_state in {"Z", "X"}:
        return MonitorInstance(
            "unknown",
            lock_path,
            True,
            claimed_pid,
            claimed_started,
            holder_pid=holder,
            detail="lock owner is no longer a live process",
        )
    if not _is_monitor_command(_process_cmdline(holder)):
        return MonitorInstance(
            "unknown",
            lock_path,
            True,
            claimed_pid,
            claimed_started,
            holder_pid=holder,
            detail="lock owner is not a Qortium Dev Monitor run process",
        )
    competing = tuple(
        pid for pid in _monitor_pids_for_state_dir(directory) if pid != holder
    )
    if competing:
        return MonitorInstance(
            "competing",
            lock_path,
            True,
            claimed_pid,
            claimed_started,
            holder_pid=holder,
            competing_pids=competing,
            detail="multiple monitor run processes target this state directory",
        )
    detail = ""
    if claimed_pid is not None and claimed_pid != holder:
        detail = "lock metadata pid differs from the verified lock owner"
    return MonitorInstance(
        "running",
        lock_path,
        True,
        claimed_pid,
        claimed_started,
        holder_pid=holder,
        detail=detail,
    )


def check_monitor(
    config: MonitorConfig,
    api: TelegramApi,
    registry,
    documents,
    *,
    expect: str = "auto",
    instance: MonitorInstance | None = None,
) -> tuple[bool, list[str]]:
    """Validate the monitor without starting the polling loop.

    ``expect="auto"`` reports both health and start readiness and fails only on
    unverifiable/competing ownership or a real check failure. ``expect="start"``
    additionally requires that a new monitor could acquire the lock, while
    ``expect="running"`` additionally requires a verified healthy instance.
    """

    if expect not in {"auto", "start", "running"}:
        raise ValueError("expect must be auto, start or running")
    lines: list[str] = []
    ok = True
    directory = ensure_state_dir(config.state_dir)
    lines.append(f"config: {config.config_path}")
    lines.append(f"mode: {config.mode}")
    if config.control_enabled:
        lines.append("control: enabled; mutating actions require explicit confirmation")
        if config.control_passphrase_hash:
            lines.append("control unlock: passphrase configured")
        else:
            lines.append("control unlock: not configured; relying on the numeric allowlist")
    lines.append(f"authorized users: {len(config.authorized_user_ids)}")
    lines.append(f"allowed chats: {len(config.allowed_chat_ids)}")
    lines.append(f"monitor state: {directory}")
    observed = instance or inspect_monitor_instance(directory)
    if observed.state == "stopped":
        lines.append("lock: free")
        lines.append("preflight: ready to start a new monitor")
    elif observed.state == "stale":
        metadata = ""
        if observed.pid is not None:
            metadata = f" (previous pid={observed.pid}"
            if observed.started is not None:
                metadata += f", started={observed.started}"
            metadata += ")"
        lines.append(f"lock: stale - lock file is not held by a live process{metadata}")
        lines.append(
            "preflight: ready to start a new monitor; the next start replaces the stale lock file"
        )
    elif observed.state == "running":
        lines.append(
            f"lock: ok - held by live monitor pid={observed.holder_pid}"
            + (f", started={observed.started}" if observed.started is not None else "")
        )
        if observed.detail:
            lines.append(f"lock warning: {observed.detail}")
        lines.append(
            "preflight: NOT ready - a live monitor owns the lock; a second instance is refused"
        )
    elif observed.state == "competing":
        pids = ",".join(str(pid) for pid in observed.competing_pids) or "unknown"
        lines.append(
            "lock: FAILED - competing monitor processes target this state directory; "+
            f"owner pid={observed.holder_pid}, competing pids={pids}"
        )
        lines.append("preflight: NOT ready - competing instances must be resolved by the owner")
        ok = False
    else:
        lines.append(f"lock: FAILED - {observed.detail or 'lock owner is unknown'}")
        lines.append("preflight: NOT ready - lock ownership cannot be verified")
        ok = False
    if expect == "running":
        if not observed.healthy:
            lines.append("expectation: FAILED - no verified healthy monitor instance is running")
            ok = False
        else:
            lines.append("expectation: healthy running monitor verified")
    elif expect == "start":
        if not observed.start_ready:
            lines.append(
                "expectation: FAILED - preflight for starting a new monitor is not ready"
            )
            ok = False
        else:
            lines.append("expectation: preflight for a new monitor is ready")

    try:
        me = api.get_me()
        username = me.get("username") or "(no username)"
        lines.append(f"telegram getMe: ok ({redact_text(username, config.secrets)})")
    except Exception as exc:  # noqa: BLE001
        lines.append(f"telegram getMe: FAILED - {redact_error(exc, config.secrets)}")
        ok = False
    try:
        webhook = api.get_webhook_info()
        url = webhook.get("url") or ""
        if url:
            lines.append("telegram webhook: FAILED - a webhook is configured; clear it explicitly")
            ok = False
        else:
            lines.append("telegram webhook: none")
    except Exception as exc:  # noqa: BLE001
        lines.append(f"telegram webhook: FAILED - {redact_error(exc, config.secrets)}")
        ok = False

    try:
        projects = registry.load(force=True)
        available = sum(1 for project in projects if project.repo_available)
        docs_available = sum(1 for project in projects if project.docs_available)
        lines.append(
            f"registry: ok ({len(projects)} projects, {available} repositories, "
            f"{docs_available} docs roots)"
        )
    except Exception as exc:  # noqa: BLE001
        lines.append(f"registry: FAILED - {redact_error(exc, config.secrets)}")
        ok = False

    if not documents.roots:
        lines.append("docs roots: none configured")
    for root in documents.roots:
        if not documents.root_available(root):
            lines.append(f"docs root {root.label}: unavailable")
            continue
        try:
            documents.list_dir(root.root_id, "", 0)
            lines.append(f"docs root {root.label}: ok")
        except Exception as exc:  # noqa: BLE001
            lines.append(
                f"docs root {root.label}: FAILED - {redact_error(exc, config.secrets)}"
            )
            ok = False

    if config.warnings:
        for warning in config.warnings:
            lines.append(f"warning: {redact_text(warning, config.secrets)}")
    return ok, lines
