"""Configuration loading and validation for the Qortium Dev Monitor.

The monitor reuses the owner-local Workflow v3 Telegram configuration file but
reads it more strictly: the file must not be group/world accessible and the
nested ``monitor`` object must carry numeric user and chat allowlists.
"""

from __future__ import annotations

import json
import os
import re
import stat
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping

from devjob import notify, store

from .passphrase import is_valid_hash

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
CONTROL_PLANE_ROOT = PACKAGE_ROOT.parent
MODES = ("read_only", "control")
DEFAULT_API_BASE = "https://api.telegram.org"
DEFAULT_ALLOWED_REPO_ROOTS = (
    Path("/home/iffi/dev-workspace/projects"),
    CONTROL_PLANE_ROOT,
)


class ConfigError(RuntimeError):
    """The monitor configuration is missing, insecure or invalid."""


def _as_int_list(value: Any, field_name: str) -> tuple[int, ...]:
    if not isinstance(value, list) or not value:
        raise ConfigError(f"monitor.{field_name} must be a non-empty list of numeric IDs")
    result: list[int] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, int):
            raise ConfigError(f"monitor.{field_name} must contain integers, not {type(item).__name__}")
        result.append(item)
    return tuple(sorted(set(result)))


def _as_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    return bool(value)


def _as_number(value: Any, default: float, minimum: float, maximum: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(maximum, number))


def _as_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return max(minimum, min(maximum, number))


def _path_list(value: Any, field_name: str) -> tuple[Path, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ConfigError(f"monitor.{field_name} must be a list of paths")
    paths: list[Path] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ConfigError(f"monitor.{field_name} must contain non-empty strings")
        paths.append(Path(item).expanduser())
    return tuple(paths)


def validate_api_base(value: str) -> str:
    """Allow HTTPS, plus loopback HTTP for isolated tests only."""

    candidate = (value or DEFAULT_API_BASE).rstrip("/")
    match = re.match(r"^(https?)://([^/:]+)(?::(\d+))?$", candidate)
    if not match:
        raise ConfigError("monitor API base must be an https URL")
    scheme, host, _port = match.groups()
    if scheme == "https":
        return candidate
    if host in {"127.0.0.1", "localhost", "::1"}:
        return candidate
    raise ConfigError("monitor API base must use https outside loopback tests")


def resolve_config_path(explicit: str | Path | None = None) -> Path:
    if explicit is not None:
        return Path(explicit).expanduser()
    value = os.environ.get("DEV_TELEGRAM_CONFIG")
    if value:
        return Path(value).expanduser()
    return notify.DEFAULT_CONFIG


def resolve_state_dir(explicit: str | Path | None = None) -> Path:
    if explicit is not None:
        return Path(explicit).expanduser()
    value = os.environ.get("DEV_MONITOR_STATE")
    if value:
        return Path(value).expanduser()
    return store.state_root() / "monitor"


def ensure_state_dir(path: str | Path) -> Path:
    directory = Path(path).expanduser()
    directory.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(directory, 0o700)
    except OSError:
        pass
    return directory


def _require_secure_file(path: Path) -> None:
    try:
        info = path.stat()
    except OSError as exc:
        raise ConfigError(f"telegram config cannot be inspected: {exc.__class__.__name__}") from exc
    if not stat.S_ISREG(info.st_mode):
        raise ConfigError("telegram config must be a regular file")
    mode = stat.S_IMODE(info.st_mode)
    if mode & (stat.S_IRWXG | stat.S_IRWXO):
        raise ConfigError(
            "telegram config is group/world accessible; run: chmod 600 <path>"
        )


@dataclass(frozen=True)
class MonitorConfig:
    mode: str
    authorized_user_ids: tuple[int, ...]
    allowed_chat_ids: tuple[int, ...]
    require_private_chat: bool
    bot_token: str
    chat_id: str | None
    poll_timeout_seconds: float
    request_timeout_seconds: float
    document_timeout_seconds: float
    slow_timing_seconds: float
    status_refresh_seconds: float
    max_inline_chars: int
    max_text_download_bytes: int
    max_binary_download_bytes: int
    allow_binary_downloads: bool
    relay_external_final: bool
    queue_owner_messages: bool
    owner_message_max_chars: int
    owner_message_retention_seconds: int
    auto_start_queued: bool
    control_passphrase_hash: str | None
    unlock_ttl_seconds: int
    admission_lock_timeout_seconds: float
    lifecycle_poll_seconds: float
    terminal_grace_seconds: int
    allowed_repo_roots: tuple[Path, ...]
    docs_roots: tuple[Path, ...]
    agent_allowlist: tuple[str, ...]
    model_allowlist: tuple[str, ...]
    api_base: str
    state_dir: Path
    job_state_root: Path
    registry_path: Path
    config_path: Path | None = None
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def secrets(self) -> tuple[str, ...]:
        return (self.bot_token,) if self.bot_token else ()

    @property
    def read_only(self) -> bool:
        return self.mode == "read_only"

    @property
    def control_enabled(self) -> bool:
        """Control actions require an explicit owner-configured control mode."""

        return self.mode == "control"

    @property
    def notification_chat_id(self) -> int:
        try:
            configured = int(self.chat_id) if self.chat_id is not None else None
        except (TypeError, ValueError):
            configured = None
        if configured is not None and configured in self.allowed_chat_ids:
            return configured
        return self.allowed_chat_ids[0]

    def __repr__(self) -> str:
        return (
            "MonitorConfig("
            f"mode={self.mode!r}, "
            f"bot_token={'<set>' if self.bot_token else None}, "
            f"authorized_users={len(self.authorized_user_ids)}, "
            f"allowed_chats={len(self.allowed_chat_ids)}, "
            f"state_dir={str(self.state_dir)!r})"
        )


def load_monitor_config(
    path: str | Path | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    state_dir: str | Path | None = None,
    require_secure: bool = True,
) -> MonitorConfig:
    """Load and validate the monitor configuration without rewriting it."""

    env = dict(os.environ if environ is None else environ)
    config_path = resolve_config_path(path or env.get("DEV_TELEGRAM_CONFIG"))
    if not config_path.is_file():
        raise ConfigError(
            "telegram config not found; set DEV_TELEGRAM_CONFIG or create "
            f"{notify.DEFAULT_CONFIG}"
        )
    if require_secure:
        _require_secure_file(config_path)
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"telegram config could not be read: {exc.__class__.__name__}") from exc
    if not isinstance(data, dict):
        raise ConfigError("telegram config must be a JSON object")

    monitor = data.get("monitor")
    if not isinstance(monitor, dict):
        raise ConfigError("telegram config is missing the nested 'monitor' object")

    mode = str(monitor.get("mode", "read_only"))
    if mode not in MODES:
        raise ConfigError(f"monitor.mode must be one of {', '.join(MODES)}")

    token = env.get("DEV_TELEGRAM_BOT_TOKEN") or data.get("bot_token")
    if not isinstance(token, str) or not token.strip():
        raise ConfigError("bot_token is required for the monitor")

    chat_id_value = env.get("DEV_TELEGRAM_CHAT_ID") or data.get("chat_id")
    chat_id = str(chat_id_value) if chat_id_value not in (None, "") else None

    authorized = _as_int_list(monitor.get("authorized_user_ids"), "authorized_user_ids")
    allowed_chats = _as_int_list(monitor.get("allowed_chat_ids"), "allowed_chat_ids")
    if not set(allowed_chats):
        raise ConfigError("monitor.allowed_chat_ids must be non-empty")

    require_private = _as_bool(monitor.get("require_private_chat", True), True)
    if not require_private:
        raise ConfigError("monitor.require_private_chat must remain true")

    allowed_repo_roots = _path_list(
        monitor.get("allowed_repo_roots"), "allowed_repo_roots"
    ) or DEFAULT_ALLOWED_REPO_ROOTS
    docs_roots = _path_list(monitor.get("docs_roots"), "docs_roots")

    agent_allowlist = monitor.get("agent_allowlist") or []
    model_allowlist = monitor.get("model_allowlist") or []
    if not isinstance(agent_allowlist, list) or not isinstance(model_allowlist, list):
        raise ConfigError("monitor.agent_allowlist and monitor.model_allowlist must be lists")
    agent_allowlist = tuple(str(item).strip() for item in agent_allowlist if str(item).strip())
    model_allowlist = tuple(str(item).strip() for item in model_allowlist if str(item).strip())

    passphrase_hash = monitor.get("control_passphrase_hash")
    if passphrase_hash in (None, ""):
        passphrase_hash = None
    elif not isinstance(passphrase_hash, str) or not is_valid_hash(passphrase_hash):
        raise ConfigError(
            "monitor.control_passphrase_hash must be a scrypt$n$r$p$salt$hash value"
        )

    if mode == "control":
        if not agent_allowlist:
            raise ConfigError("monitor.agent_allowlist must not be empty in control mode")
        if not model_allowlist:
            raise ConfigError("monitor.model_allowlist must not be empty in control mode")

    api_base = validate_api_base(
        env.get("DEV_MONITOR_API_BASE") or str(monitor.get("api_base", DEFAULT_API_BASE))
    )
    monitor_state = resolve_state_dir(state_dir or env.get("DEV_MONITOR_STATE"))
    job_state_root = Path(env.get("DEV_CONTROL_PLANE_STATE") or store.state_root()).expanduser()
    registry_path = Path(
        monitor.get("registry_path") or (CONTROL_PLANE_ROOT / "PROJECT-REGISTRY.md")
    ).expanduser()

    warnings: list[str] = []
    if mode == "read_only" and passphrase_hash:
        warnings.append("control_passphrase_hash is configured but control mode is disabled")
    if mode == "control" and not passphrase_hash:
        warnings.append(
            "control mode relies on the Telegram user/chat allowlist only; "
            "consider control_passphrase_hash"
        )

    return MonitorConfig(
        mode=mode,
        authorized_user_ids=authorized,
        allowed_chat_ids=allowed_chats,
        require_private_chat=require_private,
        bot_token=token.strip(),
        chat_id=chat_id,
        poll_timeout_seconds=_as_number(
            monitor.get("poll_timeout_seconds"), 25.0, 1.0, 50.0
        ),
        request_timeout_seconds=_as_number(
            monitor.get("request_timeout_seconds"), 10.0, 2.0, 30.0
        ),
        document_timeout_seconds=_as_number(
            monitor.get("document_timeout_seconds"), 60.0, 10.0, 300.0
        ),
        slow_timing_seconds=_as_number(
            monitor.get("slow_timing_seconds"), 1.0, 0.1, 30.0
        ),
        status_refresh_seconds=_as_number(
            monitor.get("status_refresh_seconds"), 30.0, 10.0, 600.0
        ),
        max_inline_chars=_as_int(monitor.get("max_inline_chars"), 3500, 500, 4000),
        max_text_download_bytes=_as_int(
            monitor.get("max_text_download_bytes"), 2 * 1024 * 1024, 1024, 8 * 1024 * 1024
        ),
        max_binary_download_bytes=_as_int(
            monitor.get("max_binary_download_bytes"), 10 * 1024 * 1024, 1024, 20 * 1024 * 1024
        ),
        allow_binary_downloads=_as_bool(monitor.get("allow_binary_downloads", False), False),
        relay_external_final=_as_bool(monitor.get("relay_external_final", True), True),
        queue_owner_messages=_as_bool(monitor.get("queue_owner_messages", True), True),
        owner_message_max_chars=_as_int(
            monitor.get("owner_message_max_chars"), 4000, 200, 20000
        ),
        owner_message_retention_seconds=_as_int(
            monitor.get("owner_message_retention_seconds"), 30 * 86400, 3600, 365 * 86400
        ),
        auto_start_queued=_as_bool(monitor.get("auto_start_queued", False), False),
        control_passphrase_hash=passphrase_hash,
        unlock_ttl_seconds=_as_int(monitor.get("unlock_ttl_seconds"), 900, 60, 3600),
        admission_lock_timeout_seconds=_as_number(
            monitor.get("admission_lock_timeout_seconds"), 5.0, 1.0, 30.0
        ),
        lifecycle_poll_seconds=_as_number(
            monitor.get("lifecycle_poll_seconds"), 30.0, 5.0, 600.0
        ),
        terminal_grace_seconds=_as_int(
            monitor.get("terminal_grace_seconds"), 20, 0, 3600
        ),
        allowed_repo_roots=allowed_repo_roots,
        docs_roots=docs_roots,
        agent_allowlist=agent_allowlist,
        model_allowlist=model_allowlist,
        api_base=api_base,
        state_dir=monitor_state,
        job_state_root=job_state_root,
        registry_path=registry_path,
        config_path=config_path,
        warnings=tuple(warnings),
    )


def with_overrides(config: MonitorConfig, **changes: Any) -> MonitorConfig:
    """Helper for tests and narrow runtime adjustments."""

    return replace(config, **changes)
