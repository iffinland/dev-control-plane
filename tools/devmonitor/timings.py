"""Bounded, secret-free timing diagnostics for the Qortium Dev Monitor.

The recorder keeps only fixed operation labels, numeric durations, outcome
categories and timestamps. Message text, prompts, paths, chat/user IDs, tokens
and exception messages are never stored or logged. Labels are sanitized again at
record time so an accidental caller mistake cannot leak content.

Diagnostics are deliberately lightweight: aggregation is in memory, slow samples
are logged through the service logger (normally the systemd journal) and periodic
summaries are bounded. No timing data is written to the SQLite state database, so
diagnostics cannot add fsync pressure to the update loop.
"""

from __future__ import annotations

import re
import time
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Callable, Iterator

DEFAULT_CAPACITY = 512
DEFAULT_SLOW_SECONDS = 1.0
DEFAULT_SUMMARY_INTERVAL_SECONDS = 60.0
DEFAULT_SUMMARY_INTERVAL_SAMPLES = 200
DEFAULT_RECENT_SLOW_SAMPLES = 20
MAX_PENDING_LINES = 100
MAX_LABEL_LENGTH = 80

_LABEL_RE = re.compile(r"[^A-Za-z0-9_.:-]+")


def sanitize_label(value: object) -> str:
    """Return a short, safe label containing only identifier-safe characters."""

    cleaned = _LABEL_RE.sub("_", str(value)).strip("_")
    return cleaned[:MAX_LABEL_LENGTH] or "unknown"


def _exception_outcome(exc: BaseException) -> str:
    # Class names are stable identifiers, never exception text.
    return "error:" + sanitize_label(exc.__class__.__name__)


@dataclass(frozen=True)
class TimingSample:
    """One bounded timing sample."""

    label: str
    seconds: float
    outcome: str
    at: float


class TimingRecorder:
    """Collect bounded per-operation timing statistics for one process."""

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], float] = time.time,
        capacity: int = DEFAULT_CAPACITY,
        slow_seconds: float = DEFAULT_SLOW_SECONDS,
        summary_interval_seconds: float = DEFAULT_SUMMARY_INTERVAL_SECONDS,
        summary_interval_samples: int = DEFAULT_SUMMARY_INTERVAL_SAMPLES,
    ) -> None:
        self.clock = clock
        self.wall_clock = wall_clock
        self.capacity = max(16, int(capacity))
        self.slow_seconds = max(0.0, float(slow_seconds))
        self.summary_interval_seconds = max(1.0, float(summary_interval_seconds))
        self.summary_interval_samples = max(1, int(summary_interval_samples))
        self._aggregates: dict[str, dict[str, float]] = {}
        self._samples: deque[TimingSample] = deque(maxlen=self.capacity)
        self._slow_samples: deque[TimingSample] = deque(maxlen=DEFAULT_RECENT_SLOW_SAMPLES)
        self._pending_lines: deque[str] = deque(maxlen=MAX_PENDING_LINES)
        self._samples_since_summary = 0
        self._last_summary_at = self.wall_clock()
        self._active = 0

    # ---- recording ---------------------------------------------------------------
    @contextmanager
    def measure(self, label: str, outcome: str = "ok") -> Iterator[None]:
        """Measure one operation without ever recording payload content."""

        clean = sanitize_label(label)
        started = self.clock()
        self._active += 1
        try:
            yield
        except BaseException as exc:  # noqa: BLE001 - re-raised unchanged
            self._active -= 1
            self.record(clean, self.clock() - started, _exception_outcome(exc))
            raise
        else:
            self._active -= 1
            self.record(clean, self.clock() - started, sanitize_label(outcome))

    def record(self, label: str, seconds: float, outcome: str = "ok") -> None:
        clean = sanitize_label(label)
        safe_outcome = sanitize_label(outcome)
        try:
            duration = max(0.0, float(seconds))
        except (TypeError, ValueError):
            duration = 0.0
        sample = TimingSample(clean, duration, safe_outcome, self.wall_clock())
        self._samples.append(sample)

        aggregate = self._aggregates.get(clean)
        if aggregate is None:
            aggregate = {"count": 0.0, "total": 0.0, "max": 0.0, "slow": 0.0}
            self._aggregates[clean] = aggregate
        aggregate["count"] += 1
        aggregate["total"] += duration
        aggregate["max"] = max(aggregate["max"], duration)
        if duration >= self.slow_seconds:
            aggregate["slow"] += 1
            self._slow_samples.append(sample)
            self._pending_lines.append(
                f"timing slow label={clean} duration_ms={duration * 1000:.1f} "
                f"outcome={safe_outcome}"
            )

        self._samples_since_summary += 1
        now = self.wall_clock()
        if (
            self._samples_since_summary >= self.summary_interval_samples
            or now - self._last_summary_at >= self.summary_interval_seconds
        ):
            self._pending_lines.append(self.summary_line())
            self._samples_since_summary = 0
            self._last_summary_at = now

    # ---- read surfaces -----------------------------------------------------------
    @property
    def active(self) -> int:
        return self._active

    def summary_line(self) -> str:
        if not self._aggregates:
            return "timing summary samples=0 slow=0"
        ranked = sorted(
            self._aggregates.items(),
            key=lambda item: (item[1]["total"], item[1]["max"]),
            reverse=True,
        )[:5]
        total = sum(item["count"] for item in self._aggregates.values())
        slow = sum(item["slow"] for item in self._aggregates.values())
        parts = [
            f"{label}=avg{item['total'] / max(1.0, item['count']) * 1000:.1f}ms/"
            f"max{item['max'] * 1000:.1f}ms/n{int(item['count'])}"
            for label, item in ranked
        ]
        return (
            f"timing summary samples={int(total)} slow={int(slow)} top="
            + ", ".join(parts)
        )

    def drain_log_lines(self) -> list[str]:
        """Return and clear pending slow-event and summary lines."""

        lines = list(self._pending_lines)
        self._pending_lines.clear()
        return lines

    def snapshot(self) -> dict:
        """Return bounded statistics for tests and owner diagnostics."""

        labels = [
            {
                "label": label,
                "count": int(item["count"]),
                "total_ms": round(item["total"] * 1000, 3),
                "avg_ms": round(item["total"] / max(1.0, item["count"]) * 1000, 3),
                "max_ms": round(item["max"] * 1000, 3),
                "slow": int(item["slow"]),
            }
            for label, item in self._aggregates.items()
        ]
        labels.sort(key=lambda item: (item["max_ms"], item["total_ms"]), reverse=True)
        return {
            "slow_threshold_ms": round(self.slow_seconds * 1000, 3),
            "total_samples": int(sum(item["count"] for item in self._aggregates.values())),
            "labels": labels,
            "recent_slow": [
                {
                    "label": sample.label,
                    "duration_ms": round(sample.seconds * 1000, 3),
                    "outcome": sample.outcome,
                }
                for sample in list(self._slow_samples)
            ],
        }

    def reset(self) -> None:
        self._aggregates.clear()
        self._samples.clear()
        self._slow_samples.clear()
        self._pending_lines.clear()
        self._samples_since_summary = 0
        self._last_summary_at = self.wall_clock()


_default = TimingRecorder()


def default_recorder() -> TimingRecorder:
    """Return the process-wide recorder used when no explicit one is supplied."""

    return _default
