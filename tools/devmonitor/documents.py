"""Descriptor-based, read-only document browsing for the monitor.

The resolver never trusts a path from Telegram or a job record. It validates a
relative component list, walks every directory with ``O_NOFOLLOW`` and opens the
final file with ``O_NOFOLLOW``. Only regular files are readable. Text previews
and text downloads are redacted; the source tree is never modified.
"""

from __future__ import annotations

import errno
import hashlib
import mimetypes
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

from .redact import redact_text
from .timings import TimingRecorder, default_recorder

MAX_COMPONENTS = 32
MAX_RELATIVE_LENGTH = 1024
PAGE_SIZE = 8
READ_CHUNK = 65536

HIDDEN_PREFIX = "."
DENIED_NAMES = {"secrets", "credentials"}
DENIED_SUFFIXES = (
    ".pem",
    ".key",
    ".p12",
    ".pfx",
    ".jks",
    ".kdbx",
    ".so",
    ".dll",
    ".dylib",
    ".exe",
    ".bin",
    ".o",
    ".a",
    ".zip",
    ".tar",
    ".gz",
    ".tgz",
    ".bz2",
    ".xz",
    ".7z",
    ".rar",
    ".jar",
    ".class",
    ".pyc",
    ".svg",
    ".html",
    ".htm",
)
TEXT_SUFFIXES = (
    ".md",
    ".markdown",
    ".txt",
    ".json",
    ".jsonl",
    ".log",
    ".csv",
    ".tsv",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".conf",
    ".xml",
    ".rst",
)
BINARY_IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf")


class DocumentError(RuntimeError):
    """A document path was refused or could not be read safely."""


@dataclass(frozen=True)
class DocumentRoot:
    root_id: str
    label: str
    path: Path

    def available(self) -> bool:
        try:
            info = os.lstat(self.path)
        except OSError:
            return False
        return stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode)


@dataclass(frozen=True)
class DocumentEntry:
    name: str
    rel_path: str
    is_dir: bool
    size: int
    text_kind: bool


@dataclass(frozen=True)
class Listing:
    root_id: str
    rel_dir: str
    entries: tuple[DocumentEntry, ...]
    page: int
    page_size: int
    total_entries: int
    total_pages: int


@dataclass(frozen=True)
class Preview:
    name: str
    rel_path: str
    size: int
    text: str


@dataclass(frozen=True)
class Download:
    name: str
    rel_path: str
    data: bytes
    media_type: str
    is_text: bool
    size: int
    redacted: bool


def _safe_component(component: str) -> bool:
    if not component or component in {".", ".."}:
        return False
    if component.startswith(HIDDEN_PREFIX):
        return False
    if "/" in component or "\\" in component or "%" in component:
        return False
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in component):
        return False
    return True


def _denied_name(name: str, *, is_dir: bool) -> bool:
    lowered = name.lower()
    if lowered.startswith(HIDDEN_PREFIX):
        return True
    if lowered in DENIED_NAMES:
        return True
    if lowered == ".env" or lowered.startswith(".env."):
        return True
    if lowered.startswith("id_rsa") or lowered.startswith("id_ed25519"):
        return True
    if not is_dir:
        for suffix in DENIED_SUFFIXES:
            if lowered.endswith(suffix):
                return True
    return False


def validate_relative(relative: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    if not isinstance(relative, str):
        raise DocumentError("document path must be text")
    if len(relative) > MAX_RELATIVE_LENGTH:
        raise DocumentError("document path is too long")
    if "\x00" in relative:
        raise DocumentError("document path contains a NUL byte")
    if "\\" in relative:
        raise DocumentError("backslashes are not allowed in document paths")
    if relative.startswith("/") or re.match(r"^[A-Za-z]:", relative):
        raise DocumentError("absolute paths are not allowed")
    if relative == "":
        if allow_empty:
            return ()
        raise DocumentError("empty document path")
    components = tuple(relative.split("/"))
    if len(components) > MAX_COMPONENTS:
        raise DocumentError("document path has too many components")
    for component in components:
        if not _safe_component(component):
            raise DocumentError(f"refused document path component: {component!r}")
        lowered = component.lower()
        if lowered in DENIED_NAMES or lowered.startswith(("id_rsa", "id_ed25519")):
            raise DocumentError(f"refused sensitive document path component: {component!r}")
    return components


def safe_filename(name: str) -> str:
    cleaned = re.sub(r"[\x00-\x1f\x7f/\\]", "_", str(name)).strip().strip(".")
    cleaned = cleaned[:120]
    return cleaned or "document"


def _text_name(name: str) -> str:
    path = Path(safe_filename(name))
    suffix = path.suffix
    stem = path.stem if suffix else path.name
    marker = f"{stem}.redacted{suffix or '.txt'}"
    return safe_filename(marker)


def _open_root(path: Path) -> int:
    try:
        if os.path.islink(path):
            raise DocumentError("document root may not be a symlink")
        return os.open(
            path,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
        )
    except DocumentError:
        raise
    except OSError as exc:
        raise DocumentError(f"document root is not accessible: {exc.strerror or exc}") from exc


def _open_dir_from(fd: int, component: str) -> int:
    try:
        return os.open(
            component,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
            dir_fd=fd,
        )
    except OSError as exc:
        if exc.errno in {errno.ELOOP, errno.ENOTDIR, errno.ENOENT}:
            raise DocumentError(f"refused directory component: {component!r}") from exc
        raise DocumentError(f"could not open directory: {exc.strerror or exc}") from exc


def _open_file_from(fd: int, component: str) -> tuple[int, os.stat_result]:
    try:
        file_fd = os.open(
            component,
            os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK,
            dir_fd=fd,
        )
    except OSError as exc:
        if exc.errno in {errno.ELOOP, errno.ENOENT, errno.ENOTDIR}:
            raise DocumentError(f"refused file component: {component!r}") from exc
        raise DocumentError(f"could not open document: {exc.strerror or exc}") from exc
    try:
        info = os.fstat(file_fd)
    except OSError:
        os.close(file_fd)
        raise
    if not stat.S_ISREG(info.st_mode):
        os.close(file_fd)
        raise DocumentError("only regular files are readable")
    return file_fd, info


def _walk_dir(root: Path, components: Sequence[str]) -> int:
    fd = _open_root(root)
    try:
        for component in components:
            next_fd = _open_dir_from(fd, component)
            os.close(fd)
            fd = next_fd
        return fd
    except Exception:
        os.close(fd)
        raise


def _walk_parent(root: Path, components: Sequence[str]) -> tuple[int, str]:
    if not components:
        raise DocumentError("a document file path is required")
    parent_fd = _walk_dir(root, components[:-1])
    return parent_fd, components[-1]


def _list_fd(fd: int, rel_dir: str) -> list[DocumentEntry]:
    entries: list[DocumentEntry] = []
    try:
        names = os.listdir(fd)
    except OSError as exc:
        raise DocumentError(f"could not list directory: {exc.strerror or exc}") from exc
    for name in names:
        try:
            info = os.stat(name, dir_fd=fd, follow_symlinks=False)
        except OSError:
            continue
        if stat.S_ISLNK(info.st_mode):
            continue
        is_dir = stat.S_ISDIR(info.st_mode)
        if not is_dir and not stat.S_ISREG(info.st_mode):
            continue
        if _denied_name(name, is_dir=is_dir):
            continue
        rel_path = f"{rel_dir}/{name}" if rel_dir else name
        entries.append(
            DocumentEntry(
                name=name,
                rel_path=rel_path,
                is_dir=is_dir,
                size=int(info.st_size) if not is_dir else 0,
                text_kind=(not is_dir) and name.lower().endswith(TEXT_SUFFIXES),
            )
        )
    entries.sort(key=lambda item: (not item.is_dir, item.name.casefold()))
    return entries


def _read_fd(fd: int, info: os.stat_result, max_bytes: int) -> bytes:
    if info.st_size > max_bytes:
        raise DocumentError(
            f"document is larger than the {max_bytes} byte read limit"
        )
    remaining = min(int(info.st_size), max_bytes)
    chunks: list[bytes] = []
    while remaining > 0:
        chunk = os.read(fd, min(READ_CHUNK, remaining))
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _looks_text(name: str, data: bytes) -> bool:
    if name.lower().endswith(TEXT_SUFFIXES):
        return True
    if name.lower().endswith(BINARY_IMAGE_SUFFIXES):
        return False
    return b"\x00" not in data[:4096]


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return cleaned[:48].strip("-") or "root"


def _root_id(prefix: str, label: str, path: Path) -> str:
    digest = hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:6]
    return f"{prefix}-{_slug(label)}-{digest}"


class DocumentLibrary:
    def __init__(
        self, roots: Iterable[DocumentRoot], *, timings: TimingRecorder | None = None
    ) -> None:
        self.timings = timings or default_recorder()
        by_id: dict[str, DocumentRoot] = {}
        seen_paths: set[str] = set()
        for root in roots:
            identifier = root.root_id
            if identifier in by_id:
                continue
            try:
                key = str(root.path.expanduser().resolve())
            except OSError:
                key = str(root.path)
            if key in seen_paths:
                continue
            seen_paths.add(key)
            by_id[identifier] = DocumentRoot(identifier, root.label, root.path.expanduser())
        self.roots = tuple(by_id.values())

    @classmethod
    def from_sources(
        cls,
        config_roots: Iterable[Path],
        projects: Iterable[object] = (),
        *,
        timings: TimingRecorder | None = None,
    ) -> "DocumentLibrary":
        roots: list[DocumentRoot] = [
            DocumentRoot(
                _root_id("docs", Path(path).name or "docs", Path(path)),
                Path(path).name or "docs",
                Path(path),
            )
            for path in config_roots
        ]
        for item in projects:
            docs_real = getattr(item, "docs_real", None)
            if not docs_real:
                continue
            project = getattr(item, "project", None)
            label = getattr(project, "project_id", None) or Path(docs_real).name
            roots.append(
                DocumentRoot(
                    _root_id("project", str(label), Path(docs_real)),
                    str(label),
                    Path(docs_real),
                )
            )
        return cls(roots, timings=timings)

    def get_root(self, root_id: str) -> DocumentRoot:
        for root in self.roots:
            if root.root_id == root_id:
                return root
        raise DocumentError("unknown document root")

    def root_available(self, root: DocumentRoot) -> bool:
        return root.available()

    def list_dir(self, root_id: str, rel_dir: str = "", page: int = 0) -> Listing:
        with self.timings.measure("docs:list"):
            root = self.get_root(root_id)
            components = validate_relative(rel_dir, allow_empty=True)
            fd = _walk_dir(root.path, components)
            try:
                entries = _list_fd(fd, rel_dir)
            finally:
                os.close(fd)
            total = len(entries)
            total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
            page = max(0, min(int(page), total_pages - 1))
            start = page * PAGE_SIZE
            return Listing(
                root_id=root_id,
                rel_dir=rel_dir,
                entries=tuple(entries[start : start + PAGE_SIZE]),
                page=page,
                page_size=PAGE_SIZE,
                total_entries=total,
                total_pages=total_pages,
            )

    def preview(self, root_id: str, rel_file: str, max_bytes: int, secrets: Iterable[str] = ()) -> Preview:
        with self.timings.measure("docs:preview"):
            root = self.get_root(root_id)
            components = validate_relative(rel_file)
            name = components[-1]
            if _denied_name(name, is_dir=False):
                raise DocumentError("this document type is not previewable")
            parent_fd, final = _walk_parent(root.path, components)
            try:
                file_fd, info = _open_file_from(parent_fd, final)
            finally:
                os.close(parent_fd)
            try:
                data = _read_fd(file_fd, info, max_bytes)
            finally:
                os.close(file_fd)
            if not _looks_text(name, data):
                raise DocumentError("binary documents are download-only")
            text = data.decode("utf-8", "replace")
            return Preview(name=name, rel_path=rel_file, size=len(data), text=redact_text(text, secrets))

    def open_download(
        self,
        root_id: str,
        rel_file: str,
        max_bytes: int,
        *,
        allow_binary: bool = False,
        secrets: Iterable[str] = (),
    ) -> Download:
        with self.timings.measure("docs:download"):
            root = self.get_root(root_id)
            components = validate_relative(rel_file)
            name = components[-1]
            if _denied_name(name, is_dir=False):
                raise DocumentError("this document type is not downloadable")
            parent_fd, final = _walk_parent(root.path, components)
            try:
                file_fd, info = _open_file_from(parent_fd, final)
            finally:
                os.close(parent_fd)
            try:
                data = _read_fd(file_fd, info, max_bytes)
            finally:
                os.close(file_fd)
            is_text = _looks_text(name, data)
            if not is_text and not allow_binary:
                raise DocumentError("binary downloads are disabled")
            media_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
            if is_text:
                redacted = redact_text(data.decode("utf-8", "replace"), secrets)
                return Download(
                    name=_text_name(name),
                    rel_path=rel_file,
                    data=redacted.encode("utf-8"),
                    media_type="text/plain",
                    is_text=True,
                    size=len(data),
                    redacted=True,
                )
            return Download(
                name=safe_filename(name),
                rel_path=rel_file,
                data=data,
                media_type=media_type,
                is_text=False,
                size=len(data),
                redacted=False,
            )


def self_test(root_id: str, library: DocumentLibrary) -> None:
    """Cheap startup/check validation for a configured root."""

    listing = library.list_dir(root_id, "", 0)
    if listing.root_id != root_id:
        raise DocumentError("document resolver self-test failed")
