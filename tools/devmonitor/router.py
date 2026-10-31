"""Update routing, menus and read-only renderers for the monitor."""

from __future__ import annotations

from typing import Any

from . import auth, menus, render
from .api import (
    TelegramApi,
    TelegramFatalError,
    TelegramRequestError,
    TelegramStaleCallback,
)
from .config import MonitorConfig
from .documents import DocumentError, DocumentLibrary
from .jobs import JobError, JobFacade, validate_job_id
from .projects import Registry, RegistryError
from .redact import redact_text
from .state import MonitorState
from .timings import TimingRecorder, default_recorder

JOBS_PAGE_SIZE = 6
PREVIEW_BYTES = 20000
RATE_LIMIT_ACTIONS = 30
RATE_LIMIT_WINDOW = 60
SAFE_COMMAND_LABELS = frozenset(
    {
        "start",
        "menu",
        "help",
        "jobs",
        "job",
        "status",
        "projects",
        "docs",
        "start_job",
        "resume",
        "cancel",
        "accept",
        "lock",
        "unlock",
    }
)
SAFE_CALLBACK_LABELS = frozenset({"m", "h", "p", "d", "jl", "j", "b", "x"})


class Router:
    def __init__(
        self,
        config: MonitorConfig,
        state: MonitorState,
        api: TelegramApi,
        jobs: JobFacade,
        registry: Registry,
        documents: DocumentLibrary,
        *,
        timings: TimingRecorder | None = None,
    ) -> None:
        self.config = config
        self.state = state
        self.api = api
        self.jobs = jobs
        self.registry = registry
        self.documents = documents
        self.timings = timings or default_recorder()
        self._acked_callbacks: set[str] = set()

    # ---- callback acknowledgements -----------------------------------------------
    def acknowledge_updates(self, updates: list[dict]) -> None:
        """Acknowledge every authorized callback in a polling batch immediately.

        Telegram callback query IDs expire. Processing updates strictly in order
        means a slow handler for the first click can delay the acknowledgement of
        later clicks in the same batch until they are no longer valid. Acknowledging
        the whole batch before any read-only action runs avoids that head-of-line
        blocking while keeping the actual action handling sequential.
        """

        self._acked_callbacks = set()
        for update in updates:
            if not isinstance(update, dict):
                continue
            kind, event = auth.extract_event(update)
            if kind != "callback_query" or event is None:
                continue
            decision = auth.authorize(update, self.config)
            if decision.allowed:
                self._acknowledge(event, decision)

    def acknowledge_update(self, update: dict) -> None:
        """Acknowledge one callback update without dispatching its action."""

        if not isinstance(update, dict):
            return
        kind, event = auth.extract_event(update)
        if kind != "callback_query" or event is None:
            return
        decision = auth.authorize(update, self.config)
        if decision.allowed:
            self._acknowledge(event, decision)

    # ---- public entry point ------------------------------------------------------
    def handle(self, update: dict) -> None:
        decision = auth.authorize(update, self.config)
        kind, event = auth.extract_event(update)
        if not decision.allowed:
            self._deny(decision, kind, event)
            return
        assert kind is not None and event is not None
        if not self.state.hit_rate_limit(
            f"user:{decision.user_id}", RATE_LIMIT_ACTIONS, RATE_LIMIT_WINDOW
        ):
            self._audit(decision, "rate_limited", "refused")
            if kind == "callback_query":
                self._answer(event, "Rate limit exceeded; try again shortly.", decision)
            else:
                self._send(decision.chat_id or 0, "Rate limit exceeded; try again shortly.")
            return

        if kind == "message":
            self._handle_message(event, decision)
        else:
            self._handle_callback(event, decision)

    # ---- authorization denials ---------------------------------------------------
    def _deny(self, decision: auth.AuthDecision, kind: str | None, event: dict | None) -> None:
        self._audit(decision, "denied", decision.reason)
        if kind == "callback_query" and event is not None:
            try:
                self._answer(event, "Access denied.", decision)
            except Exception:  # noqa: BLE001 - denial must not break the loop
                return
            return
        if kind == "message" and decision.chat_type == "private" and decision.chat_id:
            try:
                self.api.send_message(decision.chat_id, "Access denied.")
            except Exception:  # noqa: BLE001
                pass

    # ---- message commands --------------------------------------------------------
    def _handle_message(self, message: dict, decision: auth.AuthDecision) -> None:
        text = message.get("text") or message.get("caption") or ""
        chat_id = decision.chat_id or 0
        if not isinstance(text, str) or not text.startswith("/"):
            self._audit(decision, "message_ignored", "ignored")
            self._send(chat_id, "P1 is read-only. Use /menu to browse jobs, projects and documents.")
            return
        tokens = text.split()
        command = tokens[0][1:].split("@", 1)[0].lower()
        args = tokens[1:]
        label = command if command in SAFE_COMMAND_LABELS else "other"
        with self.timings.measure(f"action:command:{label}"):
            try:
                self._dispatch_command(command, args, decision)
            except (JobError, RegistryError, DocumentError, ValueError) as exc:
                self._audit(decision, f"command:{command}", "error", str(exc))
                self._send(chat_id, self._safe(f"Request failed: {exc}"), menus.back_to_main())

    def _dispatch_command(self, command: str, args: list[str], decision: auth.AuthDecision) -> None:
        chat_id = decision.chat_id or 0
        if command in {"start", "menu"}:
            self._send(chat_id, render.main_menu_text(self.config), menus.main_menu())
        elif command == "help":
            self._send(chat_id, render.help_text(self.config), menus.back_to_main())
        elif command == "jobs":
            page = _int_arg(args, 0, 0)
            self._show_jobs(chat_id, page, decision)
        elif command == "job":
            if not args:
                raise JobError("usage: /job <reference>")
            ref, job_id = self._resolve_job(args[0], chat_id)
            self._send_job(chat_id, ref, job_id, decision)
        elif command == "status":
            if args:
                ref, job_id = self._resolve_job(args[0], chat_id)
            else:
                ref, job_id = self._latest_job(chat_id)
            self._send_job(chat_id, ref, job_id, decision)
        elif command == "projects":
            self._show_projects(chat_id, decision)
        elif command == "docs":
            self._show_document_roots(chat_id, decision)
        elif command in {"start_job", "resume", "cancel", "accept", "lock", "unlock"}:
            self._send(
                chat_id,
                "That action is not available in P1. The monitor is read-only.",
                menus.back_to_main(),
            )
        else:
            self._send(
                chat_id,
                f"Unknown command: /{command}\n\n" + render.help_text(self.config),
                menus.back_to_main(),
            )
        self._audit(decision, f"command:{command}", "ok")

    # ---- callbacks ---------------------------------------------------------------
    def _handle_callback(self, callback: dict, decision: auth.AuthDecision) -> None:
        callback_id = str(callback.get("id") or "")
        if callback_id:
            # Best-effort and already pre-acknowledged in the polling batch. A
            # stale or rejected acknowledgement must not abort the read-only action.
            self._answer(callback, None, decision)
        data = callback.get("data")
        if not isinstance(data, str) or not data:
            self._audit(decision, "callback", "ignored", "missing data")
            return
        head = data.split(":", 1)[0]
        label = head if head in SAFE_CALLBACK_LABELS else "other"
        with self.timings.measure(f"action:callback:{label}"):
            try:
                self._dispatch_callback(callback, decision, data)
            except (JobError, RegistryError, DocumentError, ValueError) as exc:
                self._audit(decision, f"callback:{head}", "error", str(exc))
                self._edit(
                    callback,
                    decision,
                    self._safe(f"Request failed: {exc}"),
                    menus.back_to_main(),
                )

    def _dispatch_callback(self, callback: dict, decision: auth.AuthDecision, data: str) -> None:
        parts = data.split(":")
        head = parts[0]
        chat_id = decision.chat_id or 0
        if head == "m":
            self._edit(callback, decision, render.main_menu_text(self.config), menus.main_menu())
        elif head == "h":
            self._edit(callback, decision, render.help_text(self.config), menus.back_to_main())
        elif head == "p":
            self._show_projects(chat_id, decision, callback=callback)
        elif head == "d":
            self._show_document_roots(chat_id, decision, callback=callback)
        elif head == "jl":
            page = _int_arg(parts[1:], 0, 0)
            self._show_jobs(chat_id, page, decision, callback=callback)
        elif head == "j":
            self._callback_job(callback, decision, parts)
        elif head == "b":
            self._callback_browse(callback, decision, parts)
        elif head == "x":
            self._callback_confirmation(callback, decision, parts)
        else:
            self._edit(callback, decision, "Unknown action.", menus.back_to_main())
        self._audit(decision, f"callback:{head}", "ok")

    def _callback_job(self, callback: dict, decision: auth.AuthDecision, parts: list[str]) -> None:
        chat_id = decision.chat_id or 0
        if len(parts) < 2:
            raise JobError("missing job reference")
        job_id = self.state.resolve_job_ref(parts[1], chat_id)
        if not job_id:
            raise JobError("job reference is unknown or expired")
        action = parts[2] if len(parts) > 2 else ""
        if action in {"", "r"}:
            self._edit_job(callback, decision, parts[1], job_id)
        elif action in {"lr", "lw"}:
            self._show_log(callback, decision, parts[1], job_id, "run" if action == "lr" else "worker")
        elif action == "p":
            self._show_report(callback, decision, parts[1], job_id)
        elif action == "dr":
            self._download_report(callback, decision, job_id)
        elif action in {"dlr", "dlw"}:
            self._download_log(callback, decision, job_id, "run" if action == "dlr" else "worker")
        else:
            raise JobError("unknown job action")

    def _callback_browse(self, callback: dict, decision: auth.AuthDecision, parts: list[str]) -> None:
        if len(parts) < 2:
            raise DocumentError("missing browse reference")
        browse = self.state.get_browse(parts[1], decision.user_id or 0, decision.chat_id or 0)
        if not browse:
            self._edit(
                callback,
                decision,
                "This document browser has expired. Open /docs again.",
                menus.back_to_main(),
            )
            return
        root_id = str(browse["root_id"])
        rel_dir = str(browse["rel_dir"])
        page = int(browse["page"])
        action = parts[2] if len(parts) > 2 else "list"

        if action == "list":
            self._render_listing(callback, decision, browse, root_id, rel_dir, page)
        elif action in {"p", "n"}:
            new_page = page - 1 if action == "p" else page + 1
            self.state.update_browse(parts[1], page=max(0, new_page))
            self._render_listing(callback, decision, browse, root_id, rel_dir, max(0, new_page))
        elif action == "u":
            parent = "/".join(rel_dir.split("/")[:-1]) if rel_dir else ""
            self.state.update_browse(parts[1], rel_dir=parent, page=0)
            browse["rel_dir"] = parent
            self._render_listing(callback, decision, browse, root_id, parent, 0)
        elif action in {"o", "v", "d"}:
            index = _int_arg(parts[3:], 0, 0) if len(parts) > 3 else 0
            listing = self.documents.list_dir(root_id, rel_dir, page)
            if index >= len(listing.entries):
                raise DocumentError("document entry is no longer available")
            entry = listing.entries[index]
            if action == "o":
                if not entry.is_dir:
                    raise DocumentError("not a directory")
                self.state.update_browse(parts[1], rel_dir=entry.rel_path, page=0)
                browse["rel_dir"] = entry.rel_path
                self._render_listing(callback, decision, browse, root_id, entry.rel_path, 0)
            elif action == "v":
                if entry.is_dir:
                    raise DocumentError("not a file")
                self._preview(callback, decision, browse, root_id, entry.rel_path, index)
            else:
                if entry.is_dir:
                    raise DocumentError("not a file")
                self._download_document(callback, decision, browse, root_id, entry, index)
        else:
            raise DocumentError("unknown browse action")

    def _callback_confirmation(self, callback: dict, decision: auth.AuthDecision, parts: list[str]) -> None:
        if len(parts) < 3:
            raise ValueError("malformed confirmation")
        nonce, choice = parts[1], parts[2]
        if choice not in {"y", "n"}:
            raise ValueError("malformed confirmation")
        payload = self.state.consume_confirmation(
            nonce, decision.user_id or 0, decision.chat_id or 0, "download_binary"
        )
        if not payload:
            self._edit(
                callback, decision, "Confirmation expired or already used.", menus.back_to_main()
            )
            return
        if choice == "n":
            self._edit(callback, decision, "Cancelled.", menus.back_to_main())
            return
        root_id = str(payload.get("root_id") or "")
        rel_path = str(payload.get("rel_path") or "")
        download = self.documents.open_download(
            root_id,
            rel_path,
            self.config.max_binary_download_bytes,
            allow_binary=True,
            secrets=self.config.secrets,
        )
        self.api.send_document(
            decision.chat_id or 0,
            download.name,
            download.data,
            caption=f"Document: {download.rel_path} ({download.size} bytes)",
            mime_type=download.media_type,
        )
        self._edit(callback, decision, "Document sent.", menus.back_to_main())

    # ---- views -------------------------------------------------------------------
    def _show_jobs(
        self,
        chat_id: int,
        page: int,
        decision: auth.AuthDecision,
        *,
        callback: dict | None = None,
    ) -> None:
        jobs = self.jobs.list_jobs()
        total_pages = max(1, (len(jobs) + JOBS_PAGE_SIZE - 1) // JOBS_PAGE_SIZE)
        page = max(0, min(int(page), total_pages - 1))
        start = page * JOBS_PAGE_SIZE
        selected = jobs[start : start + JOBS_PAGE_SIZE]
        refs = [(self.state.get_or_create_job_ref(job["id"], chat_id), _job_button(job)) for job in selected]
        text = render.jobs_list_text(selected, page=page, total_pages=total_pages)
        markup = menus.jobs_menu(refs, page=page, total_pages=total_pages)
        if callback:
            self._edit(callback, decision, text, markup)
        else:
            self._send(chat_id, text, markup)

    def _send_job(self, chat_id: int, ref: str, job_id: str, decision: auth.AuthDecision) -> None:
        payload = self.jobs.job_status(job_id)
        result = self._send(chat_id, render.job_status_text(payload), menus.job_menu(ref))
        message_id = result.get("message_id") if isinstance(result, dict) else None
        if isinstance(message_id, int):
            self.state.set_message_ref(job_id, chat_id, "job", message_id)

    def _edit_job(self, callback: dict, decision: auth.AuthDecision, ref: str, job_id: str) -> None:
        payload = self.jobs.job_status(job_id)
        self._edit(callback, decision, render.job_status_text(payload), menus.job_menu(ref))

    def _show_log(
        self, callback: dict, decision: auth.AuthDecision, ref: str, job_id: str, kind: str
    ) -> None:
        payload = self.jobs.job_status(job_id)
        log = self.jobs.job_log(job_id, kind, secrets=self.config.secrets)
        self._edit(callback, decision, render.logs_text(payload, log), menus.log_menu(ref, kind))

    def _show_report(self, callback: dict, decision: auth.AuthDecision, ref: str, job_id: str) -> None:
        payload = self.jobs.job_status(job_id)
        report = self.jobs.job_report(job_id, secrets=self.config.secrets)
        self._edit(callback, decision, render.report_text(payload, report), menus.report_menu(ref))

    def _download_report(self, callback: dict, decision: auth.AuthDecision, job_id: str) -> None:
        report = self.jobs.job_report(job_id, secrets=self.config.secrets)
        name = f"{job_id[:20]}-report.redacted.md"
        self.api.send_document(
            decision.chat_id or 0,
            name,
            report.text.encode("utf-8"),
            caption="Redacted report copy. Source report.md is unchanged.",
            mime_type="text/markdown",
        )

    def _download_log(
        self, callback: dict, decision: auth.AuthDecision, job_id: str, kind: str
    ) -> None:
        log = self.jobs.job_log(job_id, kind, secrets=self.config.secrets)
        name = f"{job_id[:20]}-{kind}.redacted.log"
        self.api.send_document(
            decision.chat_id or 0,
            name,
            log.text.encode("utf-8"),
            caption="Redacted log window. Source log is unchanged.",
            mime_type="text/plain",
        )

    def _show_projects(
        self,
        chat_id: int,
        decision: auth.AuthDecision,
        *,
        callback: dict | None = None,
    ) -> None:
        try:
            projects = self.registry.load()
            text = render.projects_text(projects)
        except RegistryError as exc:
            text = render.projects_text([], str(exc))
        markup = menus.projects_menu()
        if callback:
            self._edit(callback, decision, text, markup)
        else:
            self._send(chat_id, text, markup)

    def _show_document_roots(
        self,
        chat_id: int,
        decision: auth.AuthDecision,
        *,
        callback: dict | None = None,
    ) -> None:
        available = [root for root in self.documents.roots if self.documents.root_available(root)]
        if not available:
            text = "No document roots are currently available."
            markup = menus.back_to_main()
        else:
            pairs: list[tuple[str, str]] = []
            for root in available:
                browse_id = self.state.create_browse(
                    decision.user_id or 0, chat_id, root.root_id, "", 0
                )
                pairs.append((browse_id, root.label))
            text = render.documents_roots_text(available)
            markup = menus.document_roots_menu(pairs)
        if callback:
            self._edit(callback, decision, text, markup)
        else:
            self._send(chat_id, text, markup)

    def _render_listing(
        self,
        callback: dict,
        decision: auth.AuthDecision,
        browse: dict,
        root_id: str,
        rel_dir: str,
        page: int,
    ) -> None:
        browse_id = str(browse["browse_id"])
        listing = self.documents.list_dir(root_id, rel_dir, page)
        entries = [
            (index, entry.name, entry.is_dir) for index, entry in enumerate(listing.entries)
        ]
        self.state.update_browse(browse_id, page=listing.page)
        self._edit(
            callback,
            decision,
            render.listing_text(listing),
            menus.document_listing_menu(
                browse_id, entries, page=listing.page, total_pages=listing.total_pages
            ),
        )

    def _preview(
        self,
        callback: dict,
        decision: auth.AuthDecision,
        browse: dict,
        root_id: str,
        rel_path: str,
        index: int,
    ) -> None:
        browse_id = str(browse["browse_id"])
        try:
            preview = self.documents.preview(
                root_id, rel_path, PREVIEW_BYTES, self.config.secrets
            )
            text = render.preview_text(preview)
            can_download = True
        except DocumentError as exc:
            lowered = str(exc).lower()
            if "binary" in lowered:
                text = (
                    f"{rel_path}\n"
                    "Binary document preview is not available. "
                    + (
                        "A confirmed download is offered below."
                        if self.config.allow_binary_downloads
                        else "Binary downloads are disabled."
                    )
                )
                can_download = self.config.allow_binary_downloads
            elif "larger than" in lowered:
                text = (
                    f"{rel_path}\n"
                    "The preview exceeds the inline size limit. "
                    "Download a redacted text copy instead."
                )
                can_download = True
            else:
                raise
        self._edit(
            callback,
            decision,
            text,
            menus.document_preview_menu(browse_id, index, can_download=can_download),
        )

    def _download_document(
        self,
        callback: dict,
        decision: auth.AuthDecision,
        browse: dict,
        root_id: str,
        entry: Any,
        index: int,
    ) -> None:
        browse_id = str(browse["browse_id"])
        if not entry.text_kind:
            download = None
        else:
            try:
                download = self.documents.open_download(
                    root_id,
                    entry.rel_path,
                    self.config.max_text_download_bytes,
                    allow_binary=False,
                    secrets=self.config.secrets,
                )
            except DocumentError as exc:
                if "binary downloads are disabled" not in str(exc).lower():
                    raise
                download = None
        if download is None:
            if not self.config.allow_binary_downloads:
                self._edit(
                    callback,
                    decision,
                    "Binary downloads are disabled by configuration.",
                    menus.document_preview_menu(browse_id, index, can_download=False),
                )
                return
            nonce = self.state.create_confirmation(
                decision.user_id or 0,
                decision.chat_id or 0,
                "download_binary",
                {"root_id": root_id, "rel_path": entry.rel_path},
            )
            self._edit(
                callback,
                decision,
                render.confirmation_text(entry.name, entry.size),
                menus.confirmation_menu(nonce),
            )
            return
        caption = (
            f"Redacted text copy of {download.rel_path} ({download.size} bytes). "
            "Source file is unchanged."
        )
        self.api.send_document(
            decision.chat_id or 0,
            download.name,
            download.data,
            caption=caption,
            mime_type="text/plain",
        )
        self._edit(callback, decision, "Redacted text copy sent.", menus.back_to_main())

    # ---- job helpers -------------------------------------------------------------
    def _resolve_job(self, identifier: str, chat_id: int) -> tuple[str, str]:
        ref = self.state.resolve_job_ref(identifier, chat_id)
        if ref:
            return identifier, ref
        candidate = validate_job_id(identifier)
        self.jobs.job_status(candidate)
        return self.state.get_or_create_job_ref(candidate, chat_id), candidate

    def _latest_job(self, chat_id: int) -> tuple[str, str]:
        jobs = self.jobs.list_jobs()
        if not jobs:
            raise JobError("no development jobs exist yet")
        job_id = str(jobs[0]["id"])
        return self.state.get_or_create_job_ref(job_id, chat_id), job_id

    # ---- transport helpers -------------------------------------------------------
    def _safe(self, text: object, limit: int | None = None) -> str:
        return redact_text(text, self.config.secrets, limit or self.config.max_inline_chars)

    def _send(self, chat_id: int, text: str, markup: dict | None = None) -> dict:
        parts = render.chunk_text(self._safe(text), self.config.max_inline_chars)
        result: dict = {}
        for index, part in enumerate(parts):
            result = self.api.send_message(
                chat_id, part, markup if index == len(parts) - 1 else None
            )
        return result

    def _edit(
        self,
        callback: dict,
        decision: auth.AuthDecision,
        text: str,
        markup: dict | None = None,
    ) -> None:
        chat_id = decision.chat_id or 0
        message = callback.get("message") if isinstance(callback.get("message"), dict) else {}
        message_id = message.get("message_id")
        parts = render.chunk_text(self._safe(text), self.config.max_inline_chars)
        if not isinstance(message_id, int):
            self._send(chat_id, text, markup)
            return
        try:
            self.api.edit_message_text(
                chat_id, message_id, parts[0], markup if len(parts) == 1 else None
            )
        except (TelegramFatalError, TelegramRequestError) as exc:
            lowered = str(exc).lower()
            if "not modified" in lowered:
                return
            if "not found" in lowered or "message to edit" in lowered:
                self._send(chat_id, text, markup)
                return
            raise
        for index, part in enumerate(parts[1:], start=1):
            self.api.send_message(
                chat_id, part, markup if index == len(parts) - 1 else None
            )

    def _acknowledge(self, callback: dict, decision: auth.AuthDecision) -> bool:
        return self._answer(callback, None, decision)

    def _answer(
        self,
        callback: dict,
        text: str | None,
        decision: auth.AuthDecision | None = None,
    ) -> bool:
        callback_id = callback.get("id")
        if not isinstance(callback_id, str) or not callback_id:
            return False
        if callback_id in self._acked_callbacks:
            return True
        try:
            self.api.answer_callback_query(callback_id, self._safe(text) if text else None)
        except TelegramRequestError as exc:
            # An acknowledgement is a UI convenience. Expired/already-used query
            # IDs and other request rejections must not dead-letter the update or
            # prevent its read-only action from running.
            self._remember_ack(callback_id)
            if decision is not None:
                result = "stale" if isinstance(exc, TelegramStaleCallback) else "error"
                self._audit(decision, "callback_ack", result, str(exc))
            return False
        self._remember_ack(callback_id)
        return True

    def _remember_ack(self, callback_id: str) -> None:
        self._acked_callbacks.add(callback_id)
        if len(self._acked_callbacks) > 1024:
            self._acked_callbacks = {callback_id}

    def _audit(
        self,
        decision: auth.AuthDecision,
        action: str,
        result: str,
        detail: str = "",
    ) -> None:
        self.state.record_audit(
            action,
            result,
            user_id=decision.user_id,
            chat_id=decision.chat_id,
            update_id=decision.update_id,
            detail=self._safe(detail, 500) if detail else "",
        )


def _job_button(job: dict) -> str:
    state = str(job.get("state") or "UNKNOWN")
    identifier = str(job.get("id") or "")
    short = identifier[:8] if len(identifier) > 8 else identifier
    return f"{state} {short}"


def _int_arg(values: list[str], index: int, default: int) -> int:
    try:
        return int(values[index])
    except (IndexError, TypeError, ValueError):
        return default
