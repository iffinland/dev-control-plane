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
from typing import Any

from .redact import redact_text

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
"""


def _now() -> int:
    return int(time.time())


class MonitorState:
    """Single-writer SQLite state used only by the monitor loop."""

    def __init__(self, path: str | Path, *, clock=_now) -> None:
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.path.parent, 0o700)
        except OSError:
            pass
        self.clock = clock
        self.connection = sqlite3.connect(str(self.path), isolation_level=None)
        self.connection.row_factory = sqlite3.Row
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

    def set_meta(self, key: str, value: str) -> None:
        self.connection.execute(
            "INSERT INTO meta(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, str(value)),
        )

    def next_offset(self) -> int:
        try:
            return int(self.get_meta("update_offset", "0") or 0)
        except (TypeError, ValueError):
            return 0

    def set_offset(self, value: int) -> None:
        # Telegram update IDs are ordered. Never let a replayed older update move
        # the durable offset backwards and cause unnecessary re-delivery.
        self.set_meta("update_offset", str(max(self.next_offset(), max(0, int(value)))))
        self.set_meta("last_poll_at", str(self.clock()))

    def claim_update(self, update_id: int) -> bool:
        cursor = self.connection.execute(
            "INSERT OR IGNORE INTO seen_updates(update_id, received_at) VALUES(?, ?)",
            (int(update_id), self.clock()),
        )
        return cursor.rowcount == 1

    def release_update(self, update_id: int) -> None:
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
        row = self.connection.execute(
            "SELECT * FROM confirmations WHERE nonce = ? AND user_id = ? AND chat_id = ? "
            "AND action = ?",
            (nonce, int(user_id), int(chat_id), action),
        ).fetchone()
        if not row:
            return None
        now = self.clock()
        if row["used_at"] is not None or int(row["expires_at"]) < now:
            return None
        self.connection.execute(
            "UPDATE confirmations SET used_at = ? WHERE nonce = ?", (now, nonce)
        )
        try:
            payload = json.loads(row["payload_json"])
        except json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else None

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

    def prune(self, *, seen_retention_seconds: int = 7 * 86400) -> None:
        now = self.clock()
        self.connection.execute("DELETE FROM browses WHERE expires_at < ?", (now,))
        self.connection.execute(
            "DELETE FROM confirmations WHERE expires_at < ?", (now,)
        )
        self.connection.execute(
            "DELETE FROM seen_updates WHERE received_at < ?",
            (now - int(seen_retention_seconds),),
        )

    def snapshot(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for table in ("seen_updates", "job_refs", "browses", "confirmations", "audit"):
            row = self.connection.execute(f"SELECT COUNT(*) AS count FROM {table}").fetchone()
            counts[table] = int(row["count"]) if row else 0
        return {
            "path": str(self.path),
            "update_offset": self.next_offset(),
            "last_poll_at": self.get_meta("last_poll_at"),
            "counts": counts,
        }
