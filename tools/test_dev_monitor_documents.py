#!/usr/bin/env python3
"""Descriptor-based document resolver tests: traversal, symlinks and redaction."""

from __future__ import annotations

import hashlib
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

from devmonitor.documents import (  # noqa: E402
    DocumentError,
    DocumentLibrary,
    DocumentRoot,
    validate_relative,
)
from devmonitor.timings import TimingRecorder  # noqa: E402

SECRET = "s3cr3t-" + "value-" + "123456"


class DocumentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="qdm-docs-")
        self.root = Path(self.temporary.name) / "docs"
        self.root.mkdir()
        self.outside = Path(self.temporary.name) / "outside"
        self.outside.mkdir()
        (self.outside / "outside.txt").write_text("outside\n", encoding="utf-8")
        self.library = DocumentLibrary([DocumentRoot("docs", "docs", self.root)])
        self.reports = self.root / "reports"
        self.reports.mkdir()
        (self.reports / "note.md").write_text(
            "# Note\n\n" + "pass" + "word=" + SECRET + "\n", encoding="utf-8"
        )
        (self.reports / "data.json").write_text('{"ok": true}\n', encoding="utf-8")
        self.binary = self.reports / "image.png"
        self.binary.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
        (self.root / ".secret.md").write_text("hidden\n", encoding="utf-8")
        git_dir = self.root / ".git"
        git_dir.mkdir()
        (git_dir / "config").write_text("[core]\n", encoding="utf-8")
        (self.root / ".env").write_text("A=B\n", encoding="utf-8")
        (self.root / "key.pem").write_text("key\n", encoding="utf-8")
        credentials = self.root / "credentials"
        credentials.mkdir()
        (credentials / "token.txt").write_text("token\n", encoding="utf-8")
        os.symlink(self.outside, self.root / "linkdir")
        os.symlink(self.outside / "outside.txt", self.root / "file-link")
        if hasattr(os, "mkfifo"):
            os.mkfifo(self.root / "pipe")
        (self.root / "large.txt").write_text("x" * 200, encoding="utf-8")

    def tearDown(self) -> None:
        self.temporary.cleanup()


    def test_document_operations_publish_secret_free_timings(self) -> None:
        recorder = TimingRecorder(slow_seconds=10.0)
        library = DocumentLibrary(
            [DocumentRoot("docs", "docs", self.root)], timings=recorder
        )
        library.list_dir("docs", "reports", 0)
        library.preview("docs", "reports/note.md", 4096)
        labels = {item["label"] for item in recorder.snapshot()["labels"]}
        self.assertEqual(labels, {"docs:list", "docs:preview"})
        self.assertNotIn(SECRET, repr(recorder.snapshot()))

    def test_validate_relative_rejects_traversal_and_absolute_paths(self) -> None:
        bad = [
            "../etc/passwd",
            "/etc/passwd",
            "a/../../b",
            "a//b",
            "a\\b",
            "%2e%2e/secret",
            "a/%2f/b",
            "",
            "a/./b",
        ]
        for value in bad:
            with self.subTest(value=value):
                with self.assertRaises(DocumentError):
                    validate_relative(value)

    def test_root_listing_excludes_hidden_symlinks_and_sensitive_names(self) -> None:
        listing = self.library.list_dir("docs", "", 0)
        names = {entry.name for entry in listing.entries}
        self.assertIn("reports", names)
        self.assertNotIn(".git", names)
        self.assertNotIn(".env", names)
        self.assertNotIn(".secret.md", names)
        self.assertNotIn("key.pem", names)
        self.assertNotIn("credentials", names)
        self.assertNotIn("linkdir", names)
        self.assertNotIn("file-link", names)
        self.assertNotIn("pipe", names)

    def test_symlink_file_and_directory_are_refused(self) -> None:
        with self.assertRaises(DocumentError):
            self.library.preview("docs", "file-link", 1024)
        with self.assertRaises(DocumentError):
            self.library.preview("docs", "linkdir/outside.txt", 1024)

    def test_denied_names_cannot_be_opened_directly(self) -> None:
        for value in ("key.pem", "credentials/token.txt"):
            with self.subTest(value=value):
                with self.assertRaises(DocumentError):
                    self.library.preview("docs", value, 1024)

    def test_preview_is_redacted(self) -> None:
        preview = self.library.preview("docs", "reports/note.md", 4096)
        self.assertIn("# Note", preview.text)
        self.assertNotIn(SECRET, preview.text)
        self.assertIn("<redacted>", preview.text)

    def test_text_download_is_redacted_and_source_is_unchanged(self) -> None:
        source = self.reports / "note.md"
        before = hashlib.sha256(source.read_bytes()).hexdigest()
        before_stat = source.stat()
        download = self.library.open_download(
            "docs", "reports/note.md", 4096, secrets=(SECRET,)
        )
        after = hashlib.sha256(source.read_bytes()).hexdigest()
        self.assertEqual(before, after)
        self.assertEqual(before_stat.st_mtime_ns, source.stat().st_mtime_ns)
        self.assertTrue(download.is_text)
        self.assertTrue(download.redacted)
        self.assertIn(".redacted", download.name)
        self.assertNotIn(SECRET.encode(), download.data)

    def test_binary_download_is_disabled_by_default(self) -> None:
        with self.assertRaises(DocumentError):
            self.library.open_download("docs", "reports/image.png", 4096)
        allowed = self.library.open_download(
            "docs", "reports/image.png", 4096, allow_binary=True
        )
        self.assertFalse(allowed.is_text)
        self.assertEqual(allowed.data, self.binary.read_bytes())

    def test_binary_preview_is_refused(self) -> None:
        with self.assertRaises(DocumentError):
            self.library.preview("docs", "reports/image.png", 4096)

    def test_oversized_file_is_refused(self) -> None:
        with self.assertRaises(DocumentError):
            self.library.preview("docs", "large.txt", 10)
        with self.assertRaises(DocumentError):
            self.library.open_download("docs", "large.txt", 10)

    def test_fifo_is_not_listed_or_opened(self) -> None:
        if not hasattr(os, "mkfifo"):
            self.skipTest("mkfifo not available")
        listing = self.library.list_dir("docs", "", 0)
        self.assertNotIn("pipe", {entry.name for entry in listing.entries})
        with self.assertRaises(DocumentError):
            self.library.preview("docs", "pipe", 1024)

    def test_browsing_does_not_change_tree_metadata(self) -> None:
        before = {
            path: (path.stat().st_mode, path.stat().st_size, path.stat().st_mtime_ns)
            for path in self.root.rglob("*")
        }
        self.library.list_dir("docs", "", 0)
        self.library.preview("docs", "reports/note.md", 4096)
        self.library.open_download("docs", "reports/note.md", 4096)
        after = {
            path: (path.stat().st_mode, path.stat().st_size, path.stat().st_mtime_ns)
            for path in self.root.rglob("*")
        }
        self.assertEqual(before, after)

    def test_pagination(self) -> None:
        for index in range(10):
            (self.root / f"page-{index:02d}.md").write_text("x\n", encoding="utf-8")
        first = self.library.list_dir("docs", "", 0)
        second = self.library.list_dir("docs", "", 1)
        self.assertGreater(first.total_pages, 1)
        self.assertEqual(len(first.entries), 8)
        self.assertGreater(len(second.entries), 0)
        self.assertNotEqual(
            {entry.name for entry in first.entries},
            {entry.name for entry in second.entries},
        )

    def test_root_symlink_is_refused(self) -> None:
        link = Path(self.temporary.name) / "root-link"
        os.symlink(self.root, link)
        library = DocumentLibrary([DocumentRoot("linked", "linked", link)])
        with self.assertRaises(DocumentError):
            library.list_dir("linked", "", 0)


if __name__ == "__main__":
    unittest.main()
