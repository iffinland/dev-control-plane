#!/usr/bin/env python3
"""Project registry parser and validation tests."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

from devmonitor.projects import (  # noqa: E402
    Registry,
    RegistryError,
    parse_registry,
    validate_projects,
)


REGISTRY = """# Project registry

## Registered projects

| ID | Platform | Verified local path | Project-level `AGENTS.md` | Canonical context | Central report root |
| --- | --- | --- | --- | --- | --- |
| `demo/one` | Qortal | `{one}` | Yes | Pending | `{docs_one}/` |
| `demo/two` | Qortium | `{two}` | No; inherits | Pending | `{docs_two}/` |

## Platform source references

| ID | Platform | Verified local path | Role |
| --- | --- | --- | --- |
| `source/ref` | Qortal | `{one}` | reference only |

## Deferred registry entries

- `demo/deferred` - not verified
"""


class ProjectTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="qdm-projects-")
        self.root = Path(self.temporary.name)
        self.projects_root = self.root / "projects"
        self.projects_root.mkdir()
        self.one = self.projects_root / "one"
        self.two = self.projects_root / "two"
        self.one.mkdir()
        self.two.mkdir()
        self.docs_one = self.root / "docs" / "one"
        self.docs_one.mkdir(parents=True)
        self.docs_two = self.root / "docs" / "two"
        self.registry_path = self.root / "PROJECT-REGISTRY.md"
        self.registry_path.write_text(
            REGISTRY.format(
                one=self.one, two=self.two, docs_one=self.docs_one, docs_two=self.docs_two
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_parses_only_registered_projects(self) -> None:
        projects = parse_registry(self.registry_path)
        self.assertEqual([item.project_id for item in projects], ["demo/one", "demo/two"])
        self.assertTrue(projects[0].has_project_agents)
        self.assertFalse(projects[1].has_project_agents)

    def test_source_references_and_deferred_are_not_projects(self) -> None:
        identifiers = {item.project_id for item in parse_registry(self.registry_path)}
        self.assertNotIn("source/ref", identifiers)
        self.assertNotIn("demo/deferred", identifiers)

    def test_repository_must_be_under_allowed_roots(self) -> None:
        projects = parse_registry(self.registry_path)
        validated = validate_projects(projects, [self.root / "elsewhere"])
        self.assertFalse(validated[0].repo_available)
        self.assertIn("outside allowed", validated[0].reason)

    def test_missing_repository_and_docs_state(self) -> None:
        projects = parse_registry(self.registry_path)
        self.two.rmdir()
        self.docs_one.rmdir()
        validated = validate_projects(projects, [self.projects_root])
        self.assertTrue(validated[0].repo_available)
        self.assertFalse(validated[0].docs_available)
        self.assertFalse(validated[1].repo_available)

    def test_registry_cache_refreshes_after_change(self) -> None:
        clock_values = [100.0, 101.0, 1000.0]
        registry = Registry(
            self.registry_path,
            (self.projects_root,),
            ttl_seconds=30,
            _clock=lambda: clock_values.pop(0),
        )
        first = registry.load()
        self.assertEqual(len(first), 2)
        text = self.registry_path.read_text(encoding="utf-8")
        self.registry_path.write_text(
            text.replace("`demo/two` | Qortium | `" + str(self.two) + "`", "`demo/two` | Qortium | `/missing/path`"),
            encoding="utf-8",
        )
        second = registry.load(force=True)
        self.assertFalse(second[1].repo_available)

    def test_missing_registry_section_fails_closed(self) -> None:
        self.registry_path.write_text("# empty\n", encoding="utf-8")
        with self.assertRaises(RegistryError):
            parse_registry(self.registry_path)

    def test_missing_file_fails_closed(self) -> None:
        with self.assertRaises(RegistryError):
            parse_registry(self.root / "missing.md")


class RegisteredProjectDocumentTests(unittest.TestCase):
    """Guard the live registry entry that makes My File Office routable."""

    def test_my_file_office_is_registered_with_delivery_policy(self) -> None:
        projects = {
            project.project_id: project
            for project in parse_registry(TOOLS.parent / "PROJECT-REGISTRY.md")
        }
        project = projects.get("qortium/my-private-room")
        self.assertIsNotNone(project)
        assert project is not None
        self.assertEqual(
            project.repo_path,
            Path("/home/iffi/dev-workspace/projects/my-private-room"),
        )
        self.assertTrue(project.has_project_agents)
        self.assertEqual(
            project.central_root,
            Path("/home/iffi/dev-workspace/docs/my-private-room"),
        )
        self.assertEqual(project.delivery.remote, "origin")
        self.assertEqual(
            project.delivery.github_repository, "iffinland/my-private-room"
        )
        self.assertEqual(project.delivery.branch_pattern, "agent/*")
        self.assertIn(
            (project.delivery.automatic_push or "").casefold(), {"yes", "true", "1"}
        )


if __name__ == "__main__":
    unittest.main()
