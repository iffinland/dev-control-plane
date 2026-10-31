"""Optional local control-unlock passphrase hashing.

The passphrase is never stored in plaintext. The owner-local configuration holds
only a salted scrypt hash in the form::

    scrypt$<n>$<r>$<p>$<salt-b64>$<hash-b64>

The monitor verifies an unlock message in memory and keeps only a short-lived
unlock marker for the current process. Nothing about the passphrase is written to
monitor state, audit rows, logs or Telegram messages.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
from typing import Iterable

HASH_PREFIX = "scrypt"
DEFAULT_N = 1 << 14
DEFAULT_R = 8
DEFAULT_P = 1
DKLEN = 32
MAX_N = 1 << 20
MAX_R = 32
MAX_P = 16
_HASH_RE = re.compile(r"^scrypt\$(\d+)\$(\d+)\$(\d+)\$([A-Za-z0-9+/=]+)\$([A-Za-z0-9+/=]+)$")


class PassphraseError(ValueError):
    """A passphrase hash is malformed or cannot be used safely."""


def _b64encode(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _b64decode(value: str) -> bytes:
    try:
        return base64.b64decode(value.encode("ascii"), validate=True)
    except (ValueError, UnicodeEncodeError) as exc:
        raise PassphraseError("passphrase hash contains invalid base64") from exc


def hash_passphrase(
    passphrase: str,
    *,
    salt: bytes | None = None,
    n: int = DEFAULT_N,
    r: int = DEFAULT_R,
    p: int = DEFAULT_P,
) -> str:
    if not isinstance(passphrase, str) or not passphrase:
        raise PassphraseError("passphrase must not be empty")
    if n < 2 or n > MAX_N or n & (n - 1):
        raise PassphraseError("scrypt n must be a power of two")
    if not 1 <= r <= MAX_R or not 1 <= p <= MAX_P:
        raise PassphraseError("scrypt r/p are outside the supported range")
    salt = os.urandom(16) if salt is None else salt
    if len(salt) < 8:
        raise PassphraseError("passphrase salt is too short")
    digest = hashlib.scrypt(
        passphrase.encode("utf-8"),
        salt=salt,
        n=n,
        r=r,
        p=p,
        dklen=DKLEN,
        maxmem=128 * 1024 * 1024,
    )
    return f"{HASH_PREFIX}${n}${r}${p}${_b64encode(salt)}${_b64encode(digest)}"


def parse_hash(value: str) -> tuple[int, int, int, bytes, bytes]:
    if not isinstance(value, str):
        raise PassphraseError("passphrase hash must be a string")
    match = _HASH_RE.match(value.strip())
    if not match:
        raise PassphraseError("passphrase hash must use scrypt$n$r$p$salt$hash")
    n, r, p = (int(part) for part in match.group(1, 2, 3))
    if n < 2 or n > MAX_N or n & (n - 1):
        raise PassphraseError("passphrase hash has an invalid scrypt n")
    if not 1 <= r <= MAX_R or not 1 <= p <= MAX_P:
        raise PassphraseError("passphrase hash has invalid scrypt r/p")
    salt = _b64decode(match.group(4))
    digest = _b64decode(match.group(5))
    if len(salt) < 8 or len(digest) == 0:
        raise PassphraseError("passphrase hash is incomplete")
    return n, r, p, salt, digest


def is_valid_hash(value: object) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        parse_hash(value)
    except PassphraseError:
        return False
    return True


def verify_passphrase(passphrase: str, encoded: str) -> bool:
    """Return True only for a matching passphrase; never raise on malformed input."""

    if not isinstance(passphrase, str) or not passphrase:
        return False
    try:
        n, r, p, salt, expected = parse_hash(encoded)
        actual = hashlib.scrypt(
            passphrase.encode("utf-8"),
            salt=salt,
            n=n,
            r=r,
            p=p,
            dklen=len(expected),
            maxmem=128 * 1024 * 1024,
        )
    except (PassphraseError, ValueError, OSError):
        return False
    return hmac.compare_digest(actual, expected)


def redact_passphrase(value: str, passphrases: Iterable[str] = ()) -> str:
    """Defense in depth: strip any configured passphrase from outbound text."""

    text = value
    for item in passphrases:
        if item:
            text = text.replace(item, "<redacted>")
    return text
