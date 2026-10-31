"""Credential redaction and control-character sanitizing.

Redaction is applied at every outbound boundary: Telegram messages, edited
messages, log and report previews, text attachments, audit detail and error
text. It is pattern based; the owner-only chat and the docs policy remain the
primary controls.
"""

from __future__ import annotations

import re
from typing import Iterable, Sequence

REDACTED = "<redacted>"
PRIVATE_KEY = "<redacted-private-key>"

_ANSI_RE = re.compile(r"\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

_BOT_TOKEN_RE = re.compile(r"\b\d{5,}:[A-Za-z0-9_-]{20,}\b")
_BOT_PREFIX_RE = re.compile(r"(?i)\bbot[0-9A-Za-z:_-]{8,}")
_AUTH_BEARER_RE = re.compile(r"(?i)(authorization\s*:\s*bearer\s+)\S+")
_PRIVATE_KEY_BLOCK_RE = re.compile(
    r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?-----END [A-Z0-9 ]*PRIVATE KEY-----",
    re.DOTALL,
)
_URL_USERINFO_RE = re.compile(r"([A-Za-z][A-Za-z0-9+.-]*://)[^/\s:@]+:[^/\s@]+@")
_GITHUB_TOKEN_RE = re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{60,})\b")
_AWS_KEY_RE = re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")
_SLACK_TOKEN_RE = re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")
_OPENAI_KEY_RE = re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")
_JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")
_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(token|secret|password|passwd|passphrase|api[_-]?key|"
    r"access[_-]?token|auth[_-]?token|secret[_-]?key|client[_-]?secret)\b"
    r"(\s*[:=]\s*)([\"']?)([^\s\"',;]{3,})"
)
_ENV_SECRET_RE = re.compile(
    r"(?im)^([A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD|PASSWD|API_KEY|ACCESS_KEY|"
    r"CLIENT_SECRET)[A-Z0-9_]*)\s*=\s*(.+)$"
)
_LONG_SENSITIVE_VALUE_RE = re.compile(
    r"(?i)(\b(?:token|secret|password|passphrase|api[_-]?key)\b\s*[:=]\s*)"
    r"[A-Za-z0-9+/=_-]{24,}"
)


def sanitize_control(text: object) -> str:
    """Remove ANSI escapes and non-printable control characters.

    Newlines and tabs are preserved. This runs before redaction so a secret
    cannot hide behind an escape sequence.
    """

    value = str(text)
    value = _ANSI_RE.sub("", value)
    value = _CONTROL_RE.sub("", value)
    return value


def _replace_exact(value: str, secret: str) -> str:
    if not secret:
        return value
    return value.replace(secret, REDACTED)


def redact_text(
    text: object,
    secrets: Iterable[str] | str | None = None,
    limit: int | None = None,
) -> str:
    """Redact credentials, sanitize control characters, then cap the length.

    Redaction runs before truncation so a token is never cut into a fragment
    that no longer matches a known pattern.
    """

    value = sanitize_control(text)
    if isinstance(secrets, str):
        secret_list: Sequence[str] = (secrets,)
    else:
        secret_list = tuple(secrets or ())
    for secret in sorted({item for item in secret_list if item}, key=len, reverse=True):
        value = _replace_exact(value, secret)
    value = _PRIVATE_KEY_BLOCK_RE.sub(PRIVATE_KEY, value)
    value = _AUTH_BEARER_RE.sub(r"\1" + REDACTED, value)
    value = _URL_USERINFO_RE.sub(r"\1" + REDACTED + "@", value)
    value = _BOT_TOKEN_RE.sub(REDACTED, value)
    value = _BOT_PREFIX_RE.sub("bot" + REDACTED, value)
    value = _GITHUB_TOKEN_RE.sub(REDACTED, value)
    value = _AWS_KEY_RE.sub(REDACTED, value)
    value = _SLACK_TOKEN_RE.sub(REDACTED, value)
    value = _OPENAI_KEY_RE.sub(REDACTED, value)
    value = _JWT_RE.sub(REDACTED, value)
    value = _ENV_SECRET_RE.sub(r"\1=" + REDACTED, value)
    value = _LONG_SENSITIVE_VALUE_RE.sub(r"\1" + REDACTED, value)
    value = _ASSIGNMENT_RE.sub(
        lambda match: match.group(1) + match.group(2) + match.group(3) + REDACTED,
        value,
    )
    if limit is not None and len(value) > max(0, limit):
        value = value[: max(0, limit)] + "\n... [truncated]"
    return value


def redact_error(exc: BaseException, secrets: Iterable[str] | str | None = None) -> str:
    """Return a short sanitized exception description safe for chat or audit."""

    return redact_text(f"{exc.__class__.__name__}: {exc}", secrets, 500)


def contains_secret(text: object, secrets: Iterable[str] | str | None = None) -> bool:
    """Return True when a known secret value is still present verbatim."""

    value = str(text)
    if isinstance(secrets, str):
        secret_list: Sequence[str] = (secrets,)
    else:
        secret_list = tuple(secrets or ())
    return any(secret and secret in value for secret in secret_list)
