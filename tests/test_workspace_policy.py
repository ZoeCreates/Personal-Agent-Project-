from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.security.workspace_policy import READ, WRITE, WorkspacePolicy


class WorkspacePolicyTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.project_root = root / "project"
        self.workspace_root = self.project_root / "workspace"
        self.project_root.mkdir()
        self.workspace_root.mkdir()
        self.policy = WorkspacePolicy(
            project_root=self.project_root,
            workspace_root=self.workspace_root,
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_allows_workspace_read_and_write(self):
        target = self.workspace_root / "notes.txt"

        self.assertTrue(self.policy.check_path(target, READ).allowed)
        self.assertTrue(self.policy.check_path(target, WRITE).allowed)

    def test_allows_project_read_but_denies_project_write(self):
        target = self.project_root / "core.py"

        self.assertTrue(self.policy.check_path(target, READ).allowed)
        decision = self.policy.check_path(target, WRITE)
        self.assertTrue(decision.denied)
        self.assertIn("outside allowed roots", decision.reason)

    def test_denies_sensitive_paths_even_inside_project(self):
        decision = self.policy.check_path(self.project_root / ".env", READ)

        self.assertTrue(decision.denied)
        self.assertIn("sensitive", decision.reason)

    def test_denies_path_traversal_outside_workspace_for_mcp_filesystem(self):
        decision = self.policy.check_mcp_tool(
            "filesystem__read_file",
            {"path": "../core.py"},
        )

        self.assertTrue(decision.denied)
        self.assertIn("outside workspace root", decision.reason)

    def test_checks_nested_mcp_path_arguments(self):
        decision = self.policy.check_mcp_tool(
            "filesystem__write_file",
            {"edits": [{"path": "safe.txt"}]},
        )

        self.assertTrue(decision.allowed)


if __name__ == "__main__":
    unittest.main()
