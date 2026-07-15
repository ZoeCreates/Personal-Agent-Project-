from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import core.security.workspace_policy as workspace_policy
from core.context import AgentContext
from core.runner import AgentRunner
from core.security.tool_permission import ToolPermissionGate
from core.security.workspace_policy import DENY, REQUIRE_APPROVAL, WorkspacePolicy


class FakeResponse:
    def __init__(self, content="", tool_calls=None, blocks=None):
        self.content = content
        self.tool_calls = tool_calls or []
        self._blocks = blocks or []

    def __iter__(self):
        return iter(self._blocks)


class FakeLLM:
    def __init__(self, tool_name: str, arguments: dict):
        self.calls = 0
        self.tool_name = tool_name
        self.arguments = arguments

    def chat(self, messages, tools=None):
        self.calls += 1
        if self.calls == 1:
            return FakeResponse(
                tool_calls=[
                    SimpleNamespace(
                        id="tool-1",
                        function=SimpleNamespace(
                            name=self.tool_name,
                            arguments=self.arguments,
                        ),
                    )
                ],
                blocks=[SimpleNamespace(type="tool_use")],
            )
        return FakeResponse(content="done")


class ToolPermissionTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.project_root = root / "project"
        self.workspace_root = self.project_root / "workspace"
        self.project_root.mkdir()
        self.workspace_root.mkdir()
        self.previous_policy = workspace_policy._default_policy
        self.policy = WorkspacePolicy(
            project_root=self.project_root,
            workspace_root=self.workspace_root,
        )
        workspace_policy._default_policy = self.policy

    def tearDown(self):
        workspace_policy._default_policy = self.previous_policy
        self.temp_dir.cleanup()

    def test_gate_allows_new_workspace_write(self):
        decision = ToolPermissionGate(self.policy).check(
            "write_file",
            {"path": "new.txt", "content": "hello"},
        )

        self.assertTrue(decision.allowed)

    def test_gate_requires_approval_for_overwrite(self):
        (self.workspace_root / "existing.txt").write_text("old", encoding="utf-8")

        decision = ToolPermissionGate(self.policy).check(
            "write_file",
            {"path": "existing.txt", "content": "new", "overwrite": True},
        )

        self.assertEqual(decision.action, REQUIRE_APPROVAL)
        self.assertIn("overwrite", decision.reason)

    def test_gate_denies_write_outside_workspace(self):
        decision = ToolPermissionGate(self.policy).check(
            "write_file",
            {"path": str(Path(self.temp_dir.name) / "outside.txt"), "content": "no"},
        )

        self.assertEqual(decision.action, DENY)
        self.assertIn("outside allowed roots", decision.reason)

    def test_runner_does_not_execute_tool_requiring_approval(self):
        target = self.workspace_root / "existing.txt"
        target.write_text("old", encoding="utf-8")
        audit_path = Path(self.temp_dir.name) / "audit.jsonl"
        context = AgentContext(
            user_id="test-user",
            user_input="overwrite",
            system_prompt="system",
            history=[],
            tools=[],
            mcp=None,
        )

        with patch.dict("os.environ", {"MY_AGENT_TOOL_AUDIT_FILE": str(audit_path)}):
            result = AgentRunner(
                llm=FakeLLM(
                    "write_file",
                    {"path": "existing.txt", "content": "new", "overwrite": True},
                )
            ).run(context)

        self.assertEqual(result.content, "done")
        self.assertEqual(target.read_text(encoding="utf-8"), "old")
        entry = json.loads(audit_path.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(entry["tool_name"], "write_file")
        self.assertFalse(entry["allowed"])
        self.assertFalse(entry["success"])
        self.assertIn("需要用户确认", entry["result_preview"])


if __name__ == "__main__":
    unittest.main()
