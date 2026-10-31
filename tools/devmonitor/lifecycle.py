"""STARTED/RESUMED and terminal lifecycle notifications with deduplication.

The existing Workflow v3 notification module only sends terminal states. This
watcher reads ``events.jsonl`` with a persisted ``(inode, offset, hash)`` cursor
and adds lifecycle notifications without modifying Workflow v3. Every send is
claimed in durable monitor state first, so a restart, replay or duplicate event
cannot send the same notification twice.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from . import menus, render
from .config import MonitorConfig
from .jobs import JobError, JobFacade
from .projects import Registry, RegistryError
from .state import MonitorState

TERMINAL_STATES = frozenset({"SUCCESS", "FAILED", "BLOCKED", "TIMEOUT"})
ALERT_EVENTS = frozenset({"reconciled_stale", "worker_lock_conflict", "worker_error"})
FIRST_RUN_TERMINAL_LOOKBACK_SECONDS = 3600


def _timestamp(value: object) -> float | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        ).timestamp()
    except ValueError:
        return None


class LifecycleNotifier:
    def __init__(
        self,
        config: MonitorConfig,
        state: MonitorState,
        jobs: JobFacade,
        api,
        registry: Registry,
        *,
        clock=time.time,
    ) -> None:
        self.config = config
        self.state = state
        self.jobs = jobs
        self.api = api
        self.registry = registry
        self.clock = clock

    # ---- explicit notifications --------------------------------------------------
    def notify_started(self, job: dict, *, project_id: str | None = None) -> bool:
        job_id = str(job.get("id") or "")
        if not job_id:
            return False
        key = f"started:{job_id}"
        if not self.state.claim_notification(key, job_id, "STARTED"):
            return False
        return self._send(job, render.lifecycle_started_text(job, project_id))

    def notify_resumed(self, job: dict) -> bool:
        job_id = str(job.get("id") or "")
        if not job_id:
            return False
        resume_count = int(job.get("resume_count") or 1)
        key = f"resumed:{job_id}:{resume_count}"
        if not self.state.claim_notification(key, job_id, "RESUMED"):
            return False
        return self._send(job, render.lifecycle_resumed_text(job))

    # ---- polling -----------------------------------------------------------------
    def poll(self) -> list[str]:
        sent: list[str] = []
        first_run = self.state.get_meta("lifecycle_initialized") != "1"
        try:
            jobs = self.jobs.list_jobs()
        except JobError:
            return sent
        projects = self._projects()
        for job in jobs:
            job_id = str(job.get("id") or "")
            if not job_id:
                continue
            state = str(job.get("state") or "")
            terminal = state in TERMINAL_STATES
            cursor = self.state.get_event_cursor(job_id)
            try:
                if cursor is None:
                    batch = self.jobs.job_events(job_id, start_at_end=terminal)
                else:
                    batch = self.jobs.job_events(
                        job_id,
                        inode=int(cursor.get("inode") or 0),
                        offset=int(cursor.get("offset") or 0),
                    )
            except JobError:
                continue
            if not terminal:
                for event in batch.events:
                    kind = str(event.get("event") or "")
                    if kind == "attempt_started" and "resume=False" in str(event.get("detail") or ""):
                        if self.notify_started(
                            job, project_id=self._project_id(job, projects)
                        ):
                            sent.append("STARTED")
                    elif kind == "resume_requested":
                        if self.notify_resumed(job):
                            sent.append("RESUMED")
                    elif kind == "attempt_started" and "resume=True" in str(event.get("detail") or ""):
                        if self.notify_resumed(job):
                            sent.append("RESUMED")
                    elif kind in ALERT_EVENTS:
                        if self._send_alert(job, kind, str(event.get("detail") or "")):
                            sent.append(kind.upper())
            else:
                for event in batch.events:
                    kind = str(event.get("event") or "")
                    if kind in ALERT_EVENTS and not first_run:
                        if self._send_alert(job, kind, str(event.get("detail") or "")):
                            sent.append(kind.upper())
                if self._terminal(job, first_run=first_run):
                    sent.append(f"TERMINAL:{state}")
            self.state.set_event_cursor(
                job_id,
                batch.inode,
                batch.offset,
                batch.last_event_hash,
            )
        self.state.set_meta("lifecycle_initialized", "1")
        return sent

    # ---- helpers -----------------------------------------------------------------
    def _projects(self):
        try:
            return list(self.registry.load())
        except RegistryError:
            return []

    def _project_id(self, job: dict, projects) -> str | None:
        try:
            repo = str(job.get("repo") or "")
            if not repo:
                return None
            real = job.get("repo_real")
            if not real:
                from pathlib import Path

                try:
                    real = Path(repo).resolve(strict=True)
                except OSError:
                    real = Path(repo).resolve()
            for project in projects:
                if project.repo_real is not None and project.repo_real == real:
                    return project.project_id
        except OSError:
            return None
        return None

    def _send_alert(self, job: dict, kind: str, detail: str) -> bool:
        job_id = str(job.get("id") or "")
        key = f"alert:{kind}:{job_id}:{detail[:80]}"
        if not self.state.claim_notification(key, job_id, kind.upper()):
            return False
        return self._send(job, render.lifecycle_alert_text(job, kind, detail))

    def _terminal(self, job: dict, *, first_run: bool) -> bool:
        job_id = str(job.get("id") or "")
        state = str(job.get("state") or "")
        ended = job.get("ended_at") or job.get("attempt_ended_at")
        age = self._age_seconds(ended)
        if first_run and age is not None and age > FIRST_RUN_TERMINAL_LOOKBACK_SECONDS:
            # Do not replay historical terminal notifications when the monitor is
            # first initialized. Future transitions still notify.
            self.state.claim_notification(
                f"terminal:{job_id}:{state}:{ended or job.get('attempt_number')}",
                job_id,
                f"TERMINAL:{state}",
            )
            return False
        try:
            record = self.jobs.job_record(job_id)
        except JobError:
            return False
        notifications_enabled = record.get("notifications_enabled")
        notifications = record.get("notifications")
        if not isinstance(notifications, list):
            notifications = []
        if notifications_enabled is True and notifications:
            # The existing Workflow v3 final notification is authoritative. Never
            # duplicate it, and never spam retries for a previously failed send.
            return False
        if notifications_enabled is True and not notifications:
            if age is None or age < float(self.config.terminal_grace_seconds):
                return False
            if not self.config.relay_external_final:
                return False
        if notifications_enabled is None or notifications_enabled is False:
            pass
        key = f"terminal:{job_id}:{state}:{ended or job.get('attempt_number')}"
        if not self.state.claim_notification(key, job_id, f"TERMINAL:{state}"):
            return False
        status = job
        try:
            status = self.jobs.job_status(job_id)
        except JobError:
            status = job
        return self._send(job, render.lifecycle_terminal_text(status, state))

    def _age_seconds(self, ended: object) -> float | None:
        stamp = _timestamp(ended)
        if stamp is None:
            return None
        return max(0.0, float(self.clock()) - stamp)

    def _send(self, job: dict, text: str) -> bool:
        job_id = str(job.get("id") or "")
        chat_id = self.config.notification_chat_id
        ref = self.state.get_or_create_job_ref(job_id, chat_id) if job_id else ""
        control = self.config.control_enabled
        resumable = str(job.get("state")) != "RUNNING" or job.get("worker_alive") is not True
        markup = menus.job_menu(ref, control=control, resumable=resumable) if ref else menus.back_to_main()
        try:
            self.api.send_message(chat_id, text, markup)
        except Exception:  # noqa: BLE001 - a notification failure must not stop polling
            return False
        return True
