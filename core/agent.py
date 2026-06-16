import json
import os
from dotenv import load_dotenv
from core.llm import LLMClient

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
        self.system_prompt = f"""You are a helpful AI assistant with access to tools including GitHub, file system, web search, stock prices, and more.

User info:
- GitHub username: {github_username}

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
        messages = [{"role": "system", "content": self.system_prompt}] + history + [{"role": "user", "content": user_input}]

        # 合并内置工具和 MCP 工具
        all_tools = TOOLS + (self.mcp.tools if self.mcp else [])

        # 第一次调用，带工具
        response = self.llm.chat(messages, tools=all_tools)

        # 如果 LLM 决定调用工具
        while response.tool_calls:
            messages.append({
                "role": "assistant",
                "content": list(response)
            })

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

                messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": tool_call.id,
                        "content": result
                    }]
                })

            response = self.llm.chat(messages, tools=all_tools)

        # 保存 AI 回复
        final_content = response.content or ""
        if final_content:
            save_message(self.user_id, "assistant", final_content)

        return final_content
