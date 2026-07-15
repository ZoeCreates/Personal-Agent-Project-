import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from core.security.workspace_policy import WorkspacePolicy, get_workspace_policy


class MCPClient:
    def __init__(self, policy: WorkspacePolicy | None = None):
        self.tools = []
        self.tool_map = {}  # tool_name -> (server_params, original_name)
        self.policy = policy or get_workspace_policy()

    async def connect(self, server_name: str, command: str, args: list, env: dict = None):
        """连接 MCP Server，加载工具列表"""
        server_params = StdioServerParameters(command=command, args=args, env=env)

        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools_result = await session.list_tools()
                for tool in tools_result.tools:
                    tool_name = f"{server_name}__{tool.name}"
                    self.tool_map[tool_name] = (server_params, tool.name)
                    self.tools.append({
                        "type": "function",
                        "function": {
                            "name": tool_name,
                            "description": tool.description or "",
                            "parameters": tool.inputSchema or {"type": "object", "properties": {}}
                        }
                    })
                print(f"  [MCP] 连接 {server_name}，加载 {len(tools_result.tools)} 个工具")

    async def call_tool(self, tool_name: str, args: dict) -> str:
        if tool_name not in self.tool_map:
            return f"未知工具: {tool_name}"
        decision = self.policy.check_mcp_tool(tool_name, args or {})
        if not decision.allowed:
            return f"工具被 workspace policy 拒绝: {decision.reason}"
        server_params, original_name = self.tool_map[tool_name]
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(original_name, args)
                return str(result.content[0].text if result.content else "无结果")

    def call_tool_sync(self, tool_name: str, args: dict) -> str:
        return asyncio.run(self.call_tool(tool_name, args))
