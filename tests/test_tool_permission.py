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
from core.security.approval_store import EXECUTED, PENDING, get_approval_store
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
        get_approval_store().clear()

    def tearDown(self):
        get_approval_store().clear()
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

        self.assertIn("Approval ID:", result.content)
        self.assertEqual(target.read_text(encoding="utf-8"), "old")
        entry = json.loads(audit_path.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(entry["tool_name"], "write_file")
        self.assertFalse(entry["allowed"])
        self.assertFalse(entry["success"])
        self.assertIn("需要用户确认", entry["result_preview"])
        approvals = get_approval_store().list(user_id="test-user", status=PENDING)
        self.assertEqual(len(approvals), 1)
        self.assertEqual(approvals[0]["tool_name"], "write_file")
        self.assertIn("Approval ID:", result.content)

    def test_runner_stops_after_creating_approval(self):
        target = self.workspace_root / "existing.txt"
        target.write_text("old", encoding="utf-8")
        audit_path = Path(self.temp_dir.name) / "audit.jsonl"
        fake_llm = FakeLLM(
            "write_file",
            {"path": "existing.txt", "content": "new", "overwrite": True},
        )
        context = AgentContext(
            user_id="test-user",
            user_input="overwrite",
            system_prompt="system",
            history=[],
            tools=[],
            mcp=None,
        )

        with patch.dict("os.environ", {"MY_AGENT_TOOL_AUDIT_FILE": str(audit_path)}):
            result = AgentRunner(llm=fake_llm).run(context)

        self.assertEqual(fake_llm.calls, 1)
        self.assertIn("Approval ID:", result.content)
        self.assertEqual(
            len(get_approval_store().list(user_id="test-user", status=PENDING)),
            1,
        )

    def test_approved_execution_runs_tool_and_updates_file(self):
        target = self.workspace_root / "existing.txt"
        target.write_text("old", encoding="utf-8")
        store = get_approval_store()
        approval = store.create(
            user_id="test-user",
            tool_name="write_file",
            args={"path": "existing.txt", "content": "new", "overwrite": True},
            reason="overwrite",
            risk="medium",
        )

        audit_path = Path(self.temp_dir.name) / "approved_audit.jsonl"
        with patch.dict("os.environ", {"MY_AGENT_TOOL_AUDIT_FILE": str(audit_path)}):
            result, trace = AgentRunner.execute_tool_after_approval(
                user_id="test-user",
                tool_name=approval.tool_name,
                args=approval.args,
            )
        store.mark_executed(approval.id, result=result, error="" if trace.success else result)

        self.assertTrue(trace.success)
        self.assertIn("已写入", result)
        self.assertEqual(target.read_text(encoding="utf-8"), "new")
        updated = store.get(approval.id)
        self.assertIsNotNone(updated)
        self.assertEqual(updated.status, EXECUTED)

    def test_approved_execution_still_denies_outside_workspace(self):
        outside = Path(self.temp_dir.name) / "outside.txt"

        audit_path = Path(self.temp_dir.name) / "denied_audit.jsonl"
        with patch.dict("os.environ", {"MY_AGENT_TOOL_AUDIT_FILE": str(audit_path)}):
            result, trace = AgentRunner.execute_tool_after_approval(
                user_id="test-user",
                tool_name="write_file",
                args={"path": str(outside), "content": "no", "overwrite": True},
            )

        self.assertFalse(trace.success)
        self.assertIn("工具被权限策略拒绝", result)
        self.assertFalse(outside.exists())


if __name__ == "__main__":
    unittest.main()
