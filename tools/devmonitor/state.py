"""Private SQLite state for the Qortium Dev Monitor.

The database stores polling offsets, update deduplication, opaque server-side
references, short-lived browser/confirmation state, rate-limit buckets and a
sanitized audit trail. It never stores prompts, raw messages or credentials.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any, Sequence

from .redact import redact_text
from .timings import TimingRecorder, default_recorder

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS seen_updates (
    update_id INTEGER PRIMARY KEY,
    received_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS message_refs (
    job_id TEXT NOT NULL,
    chat_id INTEGER NOT NULL,
    kind TEXT NOT NULL,
    message_id INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    PRIMARY KEY (job_id, chat_id, kind)
);
CREATE TABLE IF NOT EXISTS job_refs (
    ref TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    chat_id INTEGER NOT NULL,
    updated_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS browses (
    browse_id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    chat_id INTEGER NOT NULL,
    root_id TEXT NOT NULL,
    rel_dir TEXT NOT NULL,
    page INTEGER NOT NULL,
    created_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS confirmations (
    nonce TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    chat_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL,
    used_at INTEGER
);
CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    user_id INTEGER,
    chat_id INTEGER,
    update_id INTEGER,
    action TEXT NOT NULL,
    job_id TEXT,
    result TEXT NOT NULL,
    detail_redacted TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS rate_limits (
    bucket TEXT PRIMARY KEY,
    window_start INTEGER NOT NULL,
    count INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS event_cursors (
    job_id TEXT PRIMARY KEY,
    inode INTEGER NOT NULL,
    offset INTEGER NOT NULL,
    last_event_hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS wizards (
    wizard_id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    chat_id INTEGER NOT NULL,
    kind TEXT NOT NULL,
    step TEXT NOT NULL,
    state_json TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS notification_log (
    key TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS owner_messages (
    message_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    user_id INTEGER NOT NULL,
    chat_id INTEGER NOT NULL,
    body TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    delivery_state TEXT NOT NULL DEFAULT 'queued',
    delivered_at INTEGER,
    delivered_attempt INTEGER,
    last_error_redacted TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS owner_messages_job
    ON owner_messages(job_id, created_at);
"""


def _now() -> int:
    return int(time.time())


class MonitorState:
    """Single-writer SQLite state used only by the monitor loop."""

    def __init__(
        self,
        path: str | Path,
        *,
        clock=_now,
        timings: TimingRecorder | None = None,
    ) -> None:
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.path.parent, 0o700)
        except OSError:
            pass
        self.clock = clock
        self.timings = timings or default_recorder()
        self.connection = sqlite3.connect(
            str(self.path), isolation_level=None, timeout=5.0
        )
        self.connection.row_factory = sqlite3.Row
        # WAL lets the owner's read-only ``dev_monitor.py status`` inspect the
        # database without blocking the single monitor writer. NORMAL keeps
        # writes durable enough for reconstructable UI state while avoiding an
        # fsync per autocommit write. Fall back to the default journal if the
        # filesystem does not support WAL.
        try:
            self.connection.execute("PRAGMA journal_mode=WAL")
            self.connection.execute("PRAGMA synchronous=NORMAL")
        except sqlite3.OperationalError:
            pass
        self.connection.execute("PRAGMA busy_timeout=5000")
        self.connection.executescript(SCHEMA)
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "MonitorState":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    # ---- meta and polling offset -------------------------------------------------
    def get_meta(self, key: str, default: str | None = None) -> str | None:
        row = self.connection.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def _write_meta_pairs(self, pairs: list[tuple[str, object]]) -> None:
        """Write several meta keys in one transaction instead of one commit each."""

        self.connection.execute("BEGIN IMMEDIATE")
        try:
            for key, value in pairs:
                self.connection.execute(
                    "INSERT INTO meta(key, value) VALUES(?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (key, str(value)),
                )
            self.connection.execute("COMMIT")
        except BaseException:
            self.connection.execute("ROLLBACK")
            raise

    def set_meta(self, key: str, value: str) -> None:
        self._write_meta_pairs([(key, value)])

    def next_offset(self) -> int:
        try:
            return int(self.get_meta("update_offset", "0") or 0)
        except (TypeError, ValueError):
            return 0

    def set_offset(self, value: int) -> None:
        # Telegram update IDs are ordered. Never let a replayed older update move
        # the durable offset backwards and cause unnecessary re-delivery.
        with self.timings.measure("sqlite:set_offset"):
            next_value = max(self.next_offset(), max(0, int(value)))
            self._write_meta_pairs(
                [("update_offset", next_value), ("last_poll_at", self.clock())]
            )

    def claim_update(self, update_id: int) -> bool:
        with self.timings.measure("sqlite:claim_update"):
            cursor = self.connection.execute(
                "INSERT OR IGNORE INTO seen_updates(update_id, received_at) VALUES(?, ?)",
                (int(update_id), self.clock()),
            )
            return cursor.rowcount == 1

    def release_update(self, update_id: int) -> None:
        with self.timings.measure("sqlite:release_update"):
            self.connection.execute("DELETE FROM seen_updates WHERE update_id = ?", (int(update_id),))

    # ---- opaque references -------------------------------------------------------
    def get_or_create_job_ref(self, job_id: str, chat_id: int) -> str:
        row = self.connection.execute(
            "SELECT ref FROM job_refs WHERE job_id = ? AND chat_id = ?",
            (job_id, int(chat_id)),
        ).fetchone()
        if row:
            return str(row["ref"])
        ref = uuid.uuid4().hex[:10]
        self.connection.execute(
            "INSERT INTO job_refs(ref, job_id, chat_id, updated_at) VALUES(?, ?, ?, ?)",
            (ref, job_id, int(chat_id), self.clock()),
        )
        return ref

    def resolve_job_ref(self, ref: str, chat_id: int) -> str | None:
        row = self.connection.execute(
            "SELECT job_id FROM job_refs WHERE ref = ? AND chat_id = ?",
            (ref, int(chat_id)),
        ).fetchone()
        return str(row["job_id"]) if row else None

    def set_message_ref(self, job_id: str, chat_id: int, kind: str, message_id: int) -> None:
        self.connection.execute(
            "INSERT INTO message_refs(job_id, chat_id, kind, message_id, updated_at) "
            "VALUES(?, ?, ?, ?, ?) "
            "ON CONFLICT(job_id, chat_id, kind) DO UPDATE SET "
            "message_id = excluded.message_id, updated_at = excluded.updated_at",
            (job_id, int(chat_id), kind, int(message_id), self.clock()),
        )

    def get_message_ref(self, job_id: str, chat_id: int, kind: str) -> int | None:
        row = self.connection.execute(
            "SELECT message_id FROM message_refs WHERE job_id = ? AND chat_id = ? AND kind = ?",
            (job_id, int(chat_id), kind),
        ).fetchone()
        return int(row["message_id"]) if row else None

    # ---- lifecycle event cursors -------------------------------------------------
    def get_event_cursor(self, job_id: str) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT inode, offset, last_event_hash FROM event_cursors WHERE job_id = ?",
            (job_id,),
        ).fetchone()
        return dict(row) if row else None

    def set_event_cursor(
        self, job_id: str, inode: int, offset: int, last_event_hash: str
    ) -> None:
        self.connection.execute(
            "INSERT INTO event_cursors(job_id, inode, offset, last_event_hash) "
            "VALUES(?, ?, ?, ?) ON CONFLICT(job_id) DO UPDATE SET "
            "inode = excluded.inode, offset = excluded.offset, "
            "last_event_hash = excluded.last_event_hash",
            (job_id, int(inode), int(offset), last_event_hash or ""),
        )

    # ---- wizards -----------------------------------------------------------------
    def create_wizard(
        self,
        user_id: int,
        chat_id: int,
        kind: str,
        step: str,
        data: dict[str, Any],
        ttl_seconds: int = 3600,
    ) -> str:
        wizard_id = uuid.uuid4().hex[:12]
        now = self.clock()
        self.connection.execute(
            "INSERT INTO wizards(wizard_id, user_id, chat_id, kind, step, state_json, "
            "created_at, expires_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
            (
                wizard_id,
                int(user_id),
                int(chat_id),
                kind,
                step,
                json.dumps(data, sort_keys=True),
                now,
                now + int(ttl_seconds),
            ),
        )
        return wizard_id

    def get_wizard(self, wizard_id: str, user_id: int, chat_id: int) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM wizards WHERE wizard_id = ? AND user_id = ? AND chat_id = ?",
            (wizard_id, int(user_id), int(chat_id)),
        ).fetchone()
        if not row:
            return None
        if int(row["expires_at"]) < self.clock():
            self.connection.execute("DELETE FROM wizards WHERE wizard_id = ?", (wizard_id,))
            return None
        result = dict(row)
        try:
            data = json.loads(result.pop("state_json"))
        except json.JSONDecodeError:
            self.connection.execute("DELETE FROM wizards WHERE wizard_id = ?", (wizard_id,))
            return None
        result["data"] = data if isinstance(data, dict) else {}
        return result

    def get_active_wizard(self, user_id: int, chat_id: int) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT wizard_id FROM wizards WHERE user_id = ? AND chat_id = ? "
            "AND expires_at >= ? ORDER BY created_at DESC, rowid DESC LIMIT 1",
            (int(user_id), int(chat_id), self.clock()),
        ).fetchone()
        if not row:
            return None
        return self.get_wizard(str(row["wizard_id"]), user_id, chat_id)

    def update_wizard(
        self,
        wizard_id: str,
        user_id: int,
        chat_id: int,
        *,
        step: str | None = None,
        data: dict[str, Any] | None = None,
        ttl_seconds: int | None = None,
    ) -> bool:
        row = self.connection.execute(
            "SELECT state_json FROM wizards WHERE wizard_id = ? AND user_id = ? AND chat_id = ?",
            (wizard_id, int(user_id), int(chat_id)),
        ).fetchone()
        if not row:
            return False
        assignments = ["step = COALESCE(?, step)", "state_json = COALESCE(?, state_json)"]
        values: list[Any] = [
            step,
            json.dumps(data, sort_keys=True) if data is not None else None,
        ]
        if ttl_seconds is not None:
            assignments.append("expires_at = ?")
            values.append(self.clock() + int(ttl_seconds))
        values.extend([wizard_id, int(user_id), int(chat_id)])
        self.connection.execute(
            f"UPDATE wizards SET {', '.join(assignments)} "
            "WHERE wizard_id = ? AND user_id = ? AND chat_id = ?",
            tuple(values),
        )
        return True

    def delete_wizard(self, wizard_id: str, user_id: int | None = None, chat_id: int | None = None) -> None:
        if user_id is None or chat_id is None:
            self.connection.execute("DELETE FROM wizards WHERE wizard_id = ?", (wizard_id,))
        else:
            self.connection.execute(
                "DELETE FROM wizards WHERE wizard_id = ? AND user_id = ? AND chat_id = ?",
                (wizard_id, int(user_id), int(chat_id)),
            )

    # ---- notification deduplication ---------------------------------------------
    def claim_notification(self, key: str, job_id: str, kind: str) -> bool:
        """Atomically claim one lifecycle/terminal notification key."""

        cursor = self.connection.execute(
            "INSERT OR IGNORE INTO notification_log(key, job_id, kind, created_at) "
            "VALUES(?, ?, ?, ?)",
            (key, job_id, kind, self.clock()),
        )
        return cursor.rowcount == 1

    def has_notification(self, key: str) -> bool:
        row = self.connection.execute(
            "SELECT 1 FROM notification_log WHERE key = ?", (key,)
        ).fetchone()
        return row is not None

    # ---- queued owner instructions ----------------------------------------------
    def add_owner_message(
        self,
        job_id: str,
        user_id: int,
        chat_id: int,
        body: str,
    ) -> str:
        """Persist one owner instruction until it is delivered by a resume."""

        message_id = uuid.uuid4().hex[:12]
        self.connection.execute(
            "INSERT INTO owner_messages(message_id, job_id, user_id, chat_id, body, "
            "created_at, delivery_state) VALUES(?, ?, ?, ?, ?, ?, 'queued')",
            (
                message_id,
                job_id,
                int(user_id),
                int(chat_id),
                body,
                self.clock(),
            ),
        )
        return message_id

    def list_owner_messages(
        self,
        job_id: str,
        *,
        pending_only: bool = False,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        query = (
            "SELECT message_id, job_id, user_id, chat_id, body, created_at, "
            "delivery_state, delivered_at, delivered_attempt, last_error_redacted "
            "FROM owner_messages WHERE job_id = ?"
        )
        values: list[Any] = [job_id]
        if pending_only:
            query += " AND delivery_state = 'queued'"
        query += " ORDER BY created_at ASC, rowid ASC LIMIT ?"
        values.append(max(1, int(limit)))
        rows = self.connection.execute(query, tuple(values)).fetchall()
        return [dict(row) for row in rows]

    def count_pending_owner_messages(self, job_id: str) -> int:
        row = self.connection.execute(
            "SELECT COUNT(*) AS count FROM owner_messages "
            "WHERE job_id = ? AND delivery_state = 'queued'",
            (job_id,),
        ).fetchone()
        return int(row["count"]) if row else 0

    def mark_owner_messages_delivered(
        self, message_ids: Sequence[str], attempt_number: int
    ) -> int:
        if not message_ids:
            return 0
        now = self.clock()
        updated = 0
        for message_id in message_ids:
            cursor = self.connection.execute(
                "UPDATE owner_messages SET delivery_state = 'delivered', "
                "delivered_at = ?, delivered_attempt = ?, last_error_redacted = '' "
                "WHERE message_id = ? AND delivery_state = 'queued'",
                (now, int(attempt_number), message_id),
            )
            updated += int(cursor.rowcount or 0)
        return updated

    def record_owner_message_error(self, message_ids: Sequence[str], error: str) -> None:
        for message_id in message_ids:
            self.connection.execute(
                "UPDATE owner_messages SET last_error_redacted = ? "
                "WHERE message_id = ? AND delivery_state = 'queued'",
                (redact_text(error, limit=300), message_id),
            )

    # ---- browser and confirmation state -----------------------------------------
    def create_browse(
        self,
        user_id: int,
        chat_id: int,
        root_id: str,
        rel_dir: str = "",
        page: int = 0,
        ttl_seconds: int = 3600,
    ) -> str:
        browse_id = uuid.uuid4().hex[:12]
        now = self.clock()
        self.connection.execute(
            "INSERT INTO browses(browse_id, user_id, chat_id, root_id, rel_dir, page, "
            "created_at, expires_at) VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
            (
                browse_id,
                int(user_id),
                int(chat_id),
                root_id,
                rel_dir,
                int(page),
                now,
                now + int(ttl_seconds),
            ),
        )
        return browse_id

    def get_browse(self, browse_id: str, user_id: int, chat_id: int) -> dict[str, Any] | None:
        row = self.connection.execute(
            "SELECT * FROM browses WHERE browse_id = ? AND user_id = ? AND chat_id = ?",
            (browse_id, int(user_id), int(chat_id)),
        ).fetchone()
        if not row:
            return None
        if int(row["expires_at"]) < self.clock():
            self.connection.execute("DELETE FROM browses WHERE browse_id = ?", (browse_id,))
            return None
        return dict(row)

    def update_browse(self, browse_id: str, *, rel_dir: str | None = None, page: int | None = None) -> None:
        if rel_dir is not None:
            self.connection.execute(
                "UPDATE browses SET rel_dir = ? WHERE browse_id = ?", (rel_dir, browse_id)
            )
        if page is not None:
            self.connection.execute(
                "UPDATE browses SET page = ? WHERE browse_id = ?", (int(page), browse_id)
            )

    def create_confirmation(
        self,
        user_id: int,
        chat_id: int,
        action: str,
        payload: dict[str, Any],
        ttl_seconds: int = 300,
    ) -> str:
        nonce = uuid.uuid4().hex[:12]
        now = self.clock()
        self.connection.execute(
            "INSERT INTO confirmations(nonce, user_id, chat_id, action, payload_json, "
            "created_at, expires_at) VALUES(?, ?, ?, ?, ?, ?, ?)",
            (
                nonce,
                int(user_id),
                int(chat_id),
                action,
                json.dumps(payload, sort_keys=True),
                now,
                now + int(ttl_seconds),
            ),
        )
        return nonce

    def consume_confirmation(
        self, nonce: str, user_id: int, chat_id: int, action: str
    ) -> dict[str, Any] | None:
        now = self.clock()
        # Claim the nonce and mark it used in one statement. A read-then-write
        # sequence would let two connections consume the same confirmation and
        # could create a duplicate job after a restart or replay.
        cursor = self.connection.execute(
            "UPDATE confirmations SET used_at = ? WHERE nonce = ? AND user_id = ? "
            "AND chat_id = ? AND action = ? AND used_at IS NULL AND expires_at >= ?",
            (now, nonce, int(user_id), int(chat_id), action, now),
        )
        if cursor.rowcount != 1:
            return None
        row = self.connection.execute(
            "SELECT payload_json FROM confirmations WHERE nonce = ?", (nonce,)
        ).fetchone()
        if row is None:
            return None
        try:
            payload = json.loads(row["payload_json"])
        except (TypeError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    def delete_confirmation(
        self, nonce: str, user_id: int, chat_id: int, action: str | None = None
    ) -> bool:
        """Drop an unused confirmation when the owner returns to configuration.

        A preview created before a Back action must not remain a live mutation
        capability: its callback carries the old settings even though the owner
        has since edited them. Used nonces are retained as evidence.
        """

        if not nonce:
            return False
        query = (
            "DELETE FROM confirmations WHERE nonce = ? AND user_id = ? AND chat_id = ? "
            "AND used_at IS NULL"
        )
        values: list[Any] = [nonce, int(user_id), int(chat_id)]
        if action is not None:
            query += " AND action = ?"
            values.append(action)
        cursor = self.connection.execute(query, tuple(values))
        return cursor.rowcount == 1

    def confirmation_action(self, nonce: str, user_id: int, chat_id: int) -> str | None:
        """Return the action of an unused, unexpired confirmation nonce."""

        row = self.connection.execute(
            "SELECT action, used_at, expires_at FROM confirmations "
            "WHERE nonce = ? AND user_id = ? AND chat_id = ?",
            (nonce, int(user_id), int(chat_id)),
        ).fetchone()
        if not row or row["used_at"] is not None:
            return None
        if int(row["expires_at"]) < self.clock():
            return None
        return str(row["action"])

    # ---- audit and rate limiting -------------------------------------------------
    def record_audit(
        self,
        action: str,
        result: str,
        *,
        user_id: int | None = None,
        chat_id: int | None = None,
        update_id: int | None = None,
        job_id: str | None = None,
        detail: str = "",
    ) -> None:
        with self.timings.measure("sqlite:record_audit"):
            self.connection.execute(
                "INSERT INTO audit(ts, user_id, chat_id, update_id, action, job_id, result, "
                "detail_redacted) VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.clock())),
                    user_id,
                    chat_id,
                    update_id,
                    action,
                    job_id,
                    result,
                    redact_text(detail, limit=500),
                ),
            )

    def hit_rate_limit(self, bucket: str, limit: int, window_seconds: int) -> bool:
        """Return True when the action is allowed, False when limited."""

        with self.timings.measure("sqlite:hit_rate_limit"):
            now = self.clock()
            row = self.connection.execute(
                "SELECT window_start, count FROM rate_limits WHERE bucket = ?", (bucket,)
            ).fetchone()
            if not row or now - int(row["window_start"]) >= int(window_seconds):
                self.connection.execute(
                    "INSERT INTO rate_limits(bucket, window_start, count) VALUES(?, ?, 1) "
                    "ON CONFLICT(bucket) DO UPDATE SET window_start = excluded.window_start, "
                    "count = 1",
                    (bucket, now),
                )
                return True
            count = int(row["count"]) + 1
            self.connection.execute(
                "UPDATE rate_limits SET count = ? WHERE bucket = ?", (count, bucket)
            )
            return count <= int(limit)

    def prune(
        self,
        *,
        seen_retention_seconds: int = 7 * 86400,
        owner_message_retention_seconds: int = 30 * 86400,
    ) -> None:
        with self.timings.measure("sqlite:prune"):
            now = self.clock()
            self.connection.execute("DELETE FROM browses WHERE expires_at < ?", (now,))
            self.connection.execute("DELETE FROM wizards WHERE expires_at < ?", (now,))
            self.connection.execute(
                "DELETE FROM confirmations WHERE expires_at < ?", (now,)
            )
            self.connection.execute(
                "DELETE FROM seen_updates WHERE received_at < ?",
                (now - int(seen_retention_seconds),),
            )
            self.connection.execute(
                "DELETE FROM owner_messages WHERE delivery_state = 'delivered' "
                "AND delivered_at IS NOT NULL AND delivered_at < ?",
                (now - int(owner_message_retention_seconds),),
            )

    def snapshot(self) -> dict[str, Any]:
        with self.timings.measure("sqlite:snapshot"):
            counts: dict[str, int] = {}
            for table in (
                "seen_updates",
                "job_refs",
                "browses",
                "confirmations",
                "wizards",
                "notification_log",
                "owner_messages",
                "audit",
            ):
                row = self.connection.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()
                counts[table] = int(row["count"]) if row else 0
            return {
                "path": str(self.path),
                "update_offset": self.next_offset(),
                "last_poll_at": self.get_meta("last_poll_at"),
                "counts": counts,
            }
