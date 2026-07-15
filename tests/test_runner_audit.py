from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from core.context import AgentContext
from core.runner import AgentRunner


class FakeResponse:
    def __init__(self, content="", tool_calls=None, blocks=None):
        self.content = content
        self.tool_calls = tool_calls or []
        self._blocks = blocks or []

    def __iter__(self):
        return iter(self._blocks)


class FakeLLM:
    def __init__(self):
        self.calls = 0

    def chat(self, messages, tools=None):
        self.calls += 1
        if self.calls == 1:
            return FakeResponse(
                tool_calls=[
                    SimpleNamespace(
                        id="tool-1",
                        function=SimpleNamespace(
                            name="calculator",
                            arguments={"expression": "2 + 2"},
                        ),
                    )
                ],
                blocks=[SimpleNamespace(type="tool_use")],
            )
        return FakeResponse(content="4")


class RunnerAuditTest(unittest.TestCase):
    def test_runner_writes_tool_audit_log(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            audit_path = Path(temp_dir) / "tool_audit.jsonl"
            context = AgentContext(
                user_id="test-user",
                user_input="calculate",
                system_prompt="system",
                history=[],
                tools=[],
                mcp=None,
            )

            with patch.dict("os.environ", {"MY_AGENT_TOOL_AUDIT_FILE": str(audit_path)}):
                result = AgentRunner(llm=FakeLLM()).run(context)

            self.assertEqual(result.content, "4")
            entry = json.loads(audit_path.read_text(encoding="utf-8").splitlines()[0])
            self.assertEqual(entry["user_id"], "test-user")
            self.assertEqual(entry["tool_name"], "calculator")
            self.assertTrue(entry["allowed"])
            self.assertTrue(entry["success"])
            self.assertEqual(entry["result_preview"], "4")


if __name__ == "__main__":
    unittest.main()
