from __future__ import annotations

import unittest

from core.providers.anthropic_adapter import AnthropicAdapter
from core.providers.openai_adapter import OpenAIAdapter
from core.tool_intent import preferred_tool_for_latest_user_message


class ToolIntentTest(unittest.TestCase):
    def test_detects_file_write_intent(self):
        tool = preferred_tool_for_latest_user_message(
            [{"role": "user", "content": "Overwrite notes.txt with hello"}],
            {"write_file", "read_file"},
        )

        self.assertEqual(tool, "write_file")

    def test_anthropic_kwargs_force_write_file_for_file_write(self):
        adapter = AnthropicAdapter(api_key="unused", default_model="claude-test")

        kwargs = adapter.build_kwargs(
            [{"role": "user", "content": "Use write_file to overwrite notes.txt"}],
            tools=[_tool_schema("write_file")],
        )

        self.assertEqual(kwargs["tool_choice"], {"type": "tool", "name": "write_file"})

    def test_openai_kwargs_force_write_file_for_file_write(self):
        adapter = OpenAIAdapter(api_key=None, model="test")

        kwargs = adapter._build_openai_kwargs(
            {
                "system": "system",
                "messages": [
                    {"role": "user", "content": "Use write_file to overwrite notes.txt"}
                ],
                "tools": [
                    {
                        "name": "write_file",
                        "description": "write file",
                        "input_schema": {"type": "object", "properties": {}},
                    }
                ],
            }
        )

        self.assertEqual(
            kwargs["tool_choice"],
            {"type": "function", "function": {"name": "write_file"}},
        )


def _tool_schema(name: str):
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": name,
            "parameters": {"type": "object", "properties": {}},
        },
    }


if __name__ == "__main__":
    unittest.main()
