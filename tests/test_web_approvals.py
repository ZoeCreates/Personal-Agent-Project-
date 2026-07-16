from __future__ import annotations

import importlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import core.security.workspace_policy as workspace_policy
from core.security.approval_store import get_approval_store
from core.security.workspace_policy import WorkspacePolicy


class WebApprovalsTest(unittest.TestCase):
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
        get_approval_store().clear()

    def tearDown(self):
        get_approval_store().clear()
        workspace_policy._default_policy = self.previous_policy
        self.temp_dir.cleanup()

    def test_approval_api_lists_and_approves_pending_tool(self):
        target = self.workspace_root / "existing.txt"
        target.write_text("old", encoding="utf-8")
        approval = get_approval_store().create(
            user_id="web_user",
            tool_name="write_file",
            args={"path": "existing.txt", "content": "new", "overwrite": True},
            reason="overwrite",
            risk="medium",
        )

        audit_path = Path(self.temp_dir.name) / "web_audit.jsonl"
        with patch.dict(
            "os.environ",
            {
                "MY_AGENT_DISABLE_MCP": "true",
                "MY_AGENT_TOOL_AUDIT_FILE": str(audit_path),
            },
        ):
            web_ui = importlib.import_module("web_ui")
            client = web_ui.app.test_client()

            list_response = client.get("/api/approvals?status=pending")
            self.assertEqual(list_response.status_code, 200)
            self.assertEqual(
                list_response.get_json()["approvals"][0]["id"],
                approval.id,
            )

            approve_response = client.post(f"/api/approvals/{approval.id}/approve")
            self.assertEqual(approve_response.status_code, 200)

        self.assertEqual(target.read_text(encoding="utf-8"), "new")
        payload = approve_response.get_json()["approval"]
        self.assertEqual(payload["status"], "executed")
        self.assertIn("已写入", payload["result"])

    def test_pages_expose_approval_ui(self):
        with patch.dict("os.environ", {"MY_AGENT_DISABLE_MCP": "true"}):
            web_ui = importlib.import_module("web_ui")
            client = web_ui.app.test_client()

            index_html = client.get("/").get_data(as_text=True)
            settings_html = client.get("/settings").get_data(as_text=True)

        self.assertIn("approval-banner", index_html)
        self.assertIn("Tool Approvals", settings_html)
        self.assertIn("Recent decisions", settings_html)


if __name__ == "__main__":
    unittest.main()
