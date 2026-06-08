import json
from core.llm import LLMClient
from core.tools import TOOLS, TOOL_FUNCTIONS
from core.memory import save_message, load_history

class Agent:
    def __init__(self, user_id: str = "default"):
        self.llm = LLMClient()
        self.user_id = user_id
        self.system_prompt = "You are a helpful AI assistant. You have access to tools that provide real-time data. When you use a tool and get a result, trust the result and answer directly without disclaimers."

    def run(self, user_input: str) -> str:
        # 保存用户消息
        save_message(self.user_id, "user", user_input)

        # 从数据库读取历史
        history = load_history(self.user_id)
        if history:
            print(f"  [记忆加载] 用户 {self.user_id}，读取 {len(history)} 条历史")
        messages = [{"role": "system", "content": self.system_prompt}] + history

        # 第一次调用，带工具
        response = self.llm.chat(messages, tools=TOOLS)

        # 如果 LLM 决定调用工具
        while response.tool_calls:
            messages.append(response)

            for tool_call in response.tool_calls:
                name = tool_call.function.name
                raw = tool_call.function.arguments
                args = json.loads(raw) if raw else {}
                if args is None:
                    args = {}

                print(f"  [工具调用] {name}({args})")

                func = TOOL_FUNCTIONS.get(name)
                result = func(**args) if func else f"未知工具: {name}"

                print(f"  [工具结果] {result}")

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result
                })

            response = self.llm.chat(messages)

        # 保存 AI 回复
        save_message(self.user_id, "assistant", response.content)

        return response.content
