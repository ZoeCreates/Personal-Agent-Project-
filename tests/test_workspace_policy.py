from __future__ import annotations

import tempfile
import unittest
from os import pathsep
from pathlib import Path
from unittest.mock import patch

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
        self.assertIn("outside allowed roots", decision.reason)

    def test_checks_nested_mcp_path_arguments(self):
        decision = self.policy.check_mcp_tool(
            "filesystem__write_file",
            {"edits": [{"path": "safe.txt"}]},
        )

        self.assertTrue(decision.allowed)

    def test_env_roots_configure_read_and_write_policy(self):
        inputs_root = Path(self.temp_dir.name) / "inputs"
        inputs_root.mkdir()
        with patch.dict(
            "os.environ",
            {
                "MY_AGENT_WORKSPACE_ROOT": str(self.workspace_root),
                "MY_AGENT_READ_ROOTS": pathsep.join(
                    [str(self.project_root), str(inputs_root)]
                ),
                "MY_AGENT_WRITE_ROOTS": str(self.workspace_root),
                "MY_AGENT_RESTRICT_MCP_TO_WORKSPACE": "false",
            },
        ):
            policy = WorkspacePolicy(project_root=self.project_root)

        self.assertTrue(policy.check_path(inputs_root / "source.txt", READ).allowed)
        self.assertTrue(policy.check_path(inputs_root / "source.txt", WRITE).denied)
        self.assertEqual(
            policy.mcp_filesystem_root(),
            Path(self.temp_dir.name).resolve(strict=False),
        )

    def test_mcp_respects_configured_read_and_write_roots(self):
        inputs_root = Path(self.temp_dir.name) / "inputs"
        inputs_root.mkdir()
        policy = WorkspacePolicy(
            project_root=self.project_root,
            workspace_root=self.workspace_root,
            read_roots=(self.project_root, inputs_root),
            write_roots=(self.workspace_root,),
            restrict_mcp_to_workspace=False,
        )

        read_path = (
            inputs_root.resolve(strict=False).relative_to(policy.mcp_filesystem_root())
            / "source.txt"
        )
        denied_write_path = (
            inputs_root.resolve(strict=False).relative_to(policy.mcp_filesystem_root())
            / "out.txt"
        )
        allowed_write_path = (
            self.workspace_root.resolve(strict=False).relative_to(policy.mcp_filesystem_root())
            / "out.txt"
        )

        self.assertTrue(
            policy.check_mcp_tool("filesystem__read_file", {"path": str(read_path)}).allowed
        )
        self.assertTrue(
            policy.check_mcp_tool(
                "filesystem__write_file", {"path": str(denied_write_path)}
            ).denied
        )
        self.assertTrue(
            policy.check_mcp_tool(
                "filesystem__write_file", {"path": str(allowed_write_path)}
            ).allowed
        )


if __name__ == "__main__":
    unittest.main()
