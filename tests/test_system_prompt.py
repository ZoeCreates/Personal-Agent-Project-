from __future__ import annotations

import unittest

from core.loop import AgentLoop


class SystemPromptTest(unittest.TestCase):
    def test_file_tool_rules_are_in_system_prompt(self):
        prompt = AgentLoop(user_id="test-user", runner=None).build_system_prompt()

        self.assertIn("For file operations, you MUST use the file tools", prompt)
        self.assertIn("Never claim that you created, wrote, updated", prompt)
        self.assertIn("Do not label the user's own file-operation request", prompt)


if __name__ == "__main__":
    unittest.main()
