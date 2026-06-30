import json
import os
from dotenv import load_dotenv
from core.llm import LLMClient, AnthropicResponse

load_dotenv()
from core.tools import TOOLS, TOOL_FUNCTIONS
from core.memory import save_message, load_history
from core.mcp_client import MCPClient


class Agent:
    def __init__(self, user_id: str = "default", mcp: MCPClient = None):
        self.llm = LLMClient()
        self.user_id = user_id
        self.mcp = mcp
        github_username = os.getenv("GITHUB_USERNAME", "unknown")

        from pathlib import Path

        memory_file = Path.home() / ".my-agent" / "MEMORY.md"
        memory_content = (
            memory_file.read_text(encoding="utf-8").strip()
            if memory_file.exists()
            else ""
        )

        self.system_prompt = f"""You are a helpful AI assistant with access to tools including GitHub, file system, web search, stock prices, and more.

User info:
- GitHub username: {github_username}
{chr(10) + '## Long-term memory about this user' + chr(10) + memory_content + chr(10) if memory_content else ''}
Rules:
- Respond ONLY to the user's latest message. Do not continue or assume tasks from previous messages.
- Only use tools when the current message explicitly requires them. A greeting like "hi" never needs tools.
- When using GitHub tools, always use the username "{github_username}" unless the user explicitly mentions a different account.
- You CAN set reminders using the set_reminder tool. When user says "remind me to X at Y", call set_reminder immediately.
- Always summarize tool results in clear, natural language. Never show raw JSON.
- Answer directly and concisely. No disclaimers."""

    def run(self, user_input: str) -> str:
        # 先加载历史，再保存当前消息（避免当前消息被当成孤立消息过滤）
        history = load_history(self.user_id)
        save_message(self.user_id, "user", user_input)
        if history:
            print(f"  [记忆加载] 用户 {self.user_id}，读取 {len(history)} 条历史")
        messages = (
            [{"role": "system", "content": self.system_prompt}]
            + history
            + [{"role": "user", "content": user_input}]
        )

        # 合并内置工具和 MCP 工具
        all_tools = TOOLS + (self.mcp.tools if self.mcp else [])

        # 第一次调用，带工具
        response = self.llm.chat(messages, tools=all_tools)

        # 如果 LLM 决定调用工具
        while response.tool_calls:
            messages.append({"role": "assistant", "content": list(response)})

            for tool_call in response.tool_calls:
                name = tool_call.function.name
                raw = tool_call.function.arguments
                if isinstance(raw, dict):
                    args = raw
                else:
                    args = json.loads(raw) if raw else {}
                if args is None:
                    args = {}

                print(f"  [工具调用] {name}({args})")

                # 自动注入 user_id 给需要它的工具
                if name == "set_reminder":
                    args["user_id"] = self.user_id

                func = TOOL_FUNCTIONS.get(name)
                if func:
                    result = func(**args)
                elif self.mcp and name in self.mcp.tool_map:
                    result = self.mcp.call_tool_sync(name, args)

                else:
                    result = f"未知工具: {name}"

                print(f"  [工具结果] {result}")

                messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": tool_call.id,
                                "content": result,
                            }
                        ],
                    }
                )

            response = self.llm.chat(messages, tools=all_tools)

        # 保存 AI 回复
        final_content = response.content or ""
        if final_content:
            save_message(self.user_id, "assistant", final_content)

        return final_content

    def stream(self, user_input: str):
        """Generator: yields (type, data) tuples for SSE streaming.
        Types: 'text', 'tool', 'done'
        """
        history = load_history(self.user_id)
        save_message(self.user_id, "user", user_input)
        messages = (
            [{"role": "system", "content": self.system_prompt}]
            + history
            + [{"role": "user", "content": user_input}]
        )
        all_tools = TOOLS + (self.mcp.tools if self.mcp else [])

        while True:
            with self.llm.stream_chat(messages, tools=all_tools) as stream:
                accumulated_text = ""
                for text in stream.text_stream:
                    accumulated_text += text
                    yield ("text", text)
                final = stream.get_final_message()
                wrapped = AnthropicResponse(final)

            if not wrapped.tool_calls:
                if accumulated_text:
                    save_message(self.user_id, "assistant", accumulated_text)
                yield ("done", None)
                break

            tool_names = [tc.function.name for tc in wrapped.tool_calls]
            yield ("tool", f"Using: {', '.join(tool_names)}")

            messages.append({"role": "assistant", "content": list(wrapped)})
            for tool_call in wrapped.tool_calls:
                name = tool_call.function.name
                raw = tool_call.function.arguments
                args = raw if isinstance(raw, dict) else json.loads(raw or "{}")
                if args is None:
                    args = {}
                if name == "set_reminder":
                    args["user_id"] = self.user_id
                print(f"  [工具调用] {name}({args})")
                func = TOOL_FUNCTIONS.get(name)
                if func:
                    result = func(**args)
                elif self.mcp and name in self.mcp.tool_map:
                    result = self.mcp.call_tool_sync(name, args)
                else:
                    result = f"未知工具: {name}"
                print(f"  [工具结果] {result}")
                messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": tool_call.id,
                                "content": result,
                            }
                        ],
                    }
                )
