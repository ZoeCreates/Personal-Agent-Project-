from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import core.security.workspace_policy as workspace_policy
from core.security.workspace_policy import WorkspacePolicy
from core.tools import list_files, read_file, write_file


class FileToolsTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.project_root = root / "project"
        self.workspace_root = self.project_root / "workspace"
        self.project_root.mkdir()
        self.workspace_root.mkdir()
        self.previous_policy = workspace_policy._default_policy
        workspace_policy._default_policy = WorkspacePolicy(
            project_root=self.project_root,
            workspace_root=self.workspace_root,
        )

    def tearDown(self):
        workspace_policy._default_policy = self.previous_policy
        self.temp_dir.cleanup()

    def test_write_and_read_file_inside_workspace(self):
        write_result = write_file("notes/today.txt", "hello workspace")

        self.assertIn("已写入", write_result)
        self.assertEqual(read_file("notes/today.txt"), "hello workspace")

    def test_write_file_denies_paths_outside_workspace(self):
        outside = Path(self.temp_dir.name) / "outside.txt"

        result = write_file(str(outside), "nope")

        self.assertIn("文件写入被拒绝", result)
        self.assertFalse(outside.exists())

    def test_write_file_requires_overwrite_for_existing_file(self):
        target = self.workspace_root / "existing.txt"
        target.write_text("old", encoding="utf-8")

        result = write_file("existing.txt", "new")

        self.assertIn("overwrite=true", result)
        self.assertEqual(target.read_text(encoding="utf-8"), "old")

    def test_read_file_allows_project_read_but_denies_sensitive_file(self):
        source = self.project_root / "README.md"
        source.write_text("project notes", encoding="utf-8")
        secret = self.workspace_root / ".env"
        secret.write_text("TOKEN=secret", encoding="utf-8")

        self.assertEqual(read_file(str(source)), "project notes")
        self.assertIn("文件读取被拒绝", read_file(".env"))

    def test_list_files_skips_sensitive_entries(self):
        (self.workspace_root / "safe.txt").write_text("ok", encoding="utf-8")
        (self.workspace_root / ".env").write_text("TOKEN=secret", encoding="utf-8")

        result = list_files(".")

        self.assertIn("safe.txt", result)
        self.assertNotIn(".env", result)
        self.assertIn("跳过 1 个受保护路径", result)


if __name__ == "__main__":
    unittest.main()
