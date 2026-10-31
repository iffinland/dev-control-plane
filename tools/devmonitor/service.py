"""Single-instance polling loop for the Qortium Dev Monitor.

The service is owner-started in the foreground. It uses outbound long polling,
persists the next offset only after an update is handled or dead-lettered, and
stops through a flag file. It never installs a service, starts a listener or
signals processes by name.
"""

from __future__ import annotations

import fcntl
import os
import time
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


class AlreadyRunning(RuntimeError):
    """Another monitor instance holds the state lock."""


class MonitorService:
    def __init__(
        self,
        config: MonitorConfig,
        api: TelegramApi,
        state: MonitorState,
        router,
        *,
        sleep: Callable[[float], None] = time.sleep,
        log: Callable[[str], None] | None = None,
    ) -> None:
        self.config = config
        self.api = api
        self.state = state
        self.router = router
        self.sleep = sleep
        self.log = log or (lambda _message: None)
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
        return self.stop_path.exists()

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
                try:
                    updates = self.api.get_updates(
                        self.state.next_offset(), self.config.poll_timeout_seconds
                    )
                    transient_attempt = 0
                    for update in updates:
                        if self.stop_requested():
                            break
                        self.process_update(update)
                    self.state.prune()
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
                self.sleep(0.1)
        finally:
            self._release_lock()

    def process_update(self, update: dict) -> None:
        if not isinstance(update, dict):
            return
        update_id = update.get("update_id")
        if isinstance(update_id, bool) or not isinstance(update_id, int):
            return
        if not self.state.claim_update(update_id):
            self.state.set_offset(update_id + 1)
            return
        try:
            self.router.handle(update)
        except (TelegramRateLimited, TelegramTransientError, TelegramFatalError):
            # A transient outbound failure is retried by the loop; a fatal error
            # stops the monitor. In both cases leave the offset unmoved.
            self.state.release_update(update_id)
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


def check_monitor(config: MonitorConfig, api: TelegramApi, registry, documents) -> tuple[bool, list[str]]:
    """Validate the monitor without starting the polling loop."""

    lines: list[str] = []
    ok = True
    directory = ensure_state_dir(config.state_dir)
    lines.append(f"config: {config.config_path}")
    lines.append(f"mode: {config.mode}")
    lines.append(f"authorized users: {len(config.authorized_user_ids)}")
    lines.append(f"allowed chats: {len(config.allowed_chat_ids)}")
    lines.append(f"monitor state: {directory}")
    if monitor_running(directory):
        lines.append("lock: FAILED - another monitor instance is running")
        ok = False
    else:
        lines.append("lock: free")

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
