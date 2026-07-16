from __future__ import annotations

import json
import os
import time
from types import SimpleNamespace
from typing import Iterator

from core.context import AgentContext, RunnerResult, ToolTrace
from core.llm import AnthropicResponse, LLMClient
from core.security.approval_store import get_approval_store
from core.security.tool_permission import get_tool_permission_gate
from core.tools import TOOL_FUNCTIONS
from core.tool_audit import log_tool_call


class AgentRunner:
    """Model-facing loop: call the LLM, execute tools, and return the final answer."""

    def __init__(self, llm: LLMClient | None = None, max_tool_steps: int | None = None):
        self.llm = llm or LLMClient()
        self.max_tool_steps = max_tool_steps or int(os.getenv("MAX_TOOL_STEPS", "12"))

    def run(self, context: AgentContext) -> RunnerResult:
        messages = context.messages
        traces: list[ToolTrace] = []

        response = self.llm.chat(messages, tools=context.tools)
        tool_steps = 0

        while response.tool_calls:
            tool_steps += 1
            if tool_steps > self.max_tool_steps:
                return RunnerResult(
                    content="工具调用次数过多，我先停下来避免无限循环。",
                    tool_traces=traces,
                )

            messages.append({"role": "assistant", "content": list(response)})

            for tool_call in response.tool_calls:
                result, trace = self._execute_tool(context, tool_call)
                traces.append(trace)
                messages.append(self._tool_result_message(tool_call.id, result))
                if self._is_approval_waiting_result(result):
                    return RunnerResult(content=result, tool_traces=traces)

            response = self.llm.chat(messages, tools=context.tools)

        return RunnerResult(content=response.content or "", tool_traces=traces)

    def stream(self, context: AgentContext) -> Iterator[tuple[str, object]]:
        messages = context.messages
        tool_steps = 0

        while True:
            with self.llm.stream_chat(messages, tools=context.tools) as stream:
                accumulated_text = ""
                for text in stream.text_stream:
                    accumulated_text += text
                    yield ("text", text)
                final = stream.get_final_message()
                wrapped = AnthropicResponse(final)

            if not wrapped.tool_calls:
                yield ("final", accumulated_text)
                yield ("done", None)
                break

            tool_steps += 1
            if tool_steps > self.max_tool_steps:
                message = "工具调用次数过多，我先停下来避免无限循环。"
                yield ("text", message)
                yield ("final", message)
                yield ("done", None)
                break

            tool_names = [tc.function.name for tc in wrapped.tool_calls]
            yield ("tool", f"Using: {', '.join(tool_names)}")

            messages.append({"role": "assistant", "content": list(wrapped)})
            for tool_call in wrapped.tool_calls:
                result, _trace = self._execute_tool(context, tool_call)
                messages.append(self._tool_result_message(tool_call.id, result))
                if self._is_approval_waiting_result(result):
                    yield ("text", result)
                    yield ("final", result)
                    yield ("done", None)
                    return

    def _execute_tool(self, context: AgentContext, tool_call) -> tuple[str, ToolTrace]:
        name = tool_call.function.name
        args = self._parse_args(tool_call.function.arguments)

        return self._execute_tool_by_name(
            context=context,
            name=name,
            args=args,
        )

    @staticmethod
    def execute_tool_after_approval(
        *,
        user_id: str,
        tool_name: str,
        args: dict,
        mcp=None,
    ) -> tuple[str, ToolTrace]:
        context = SimpleNamespace(user_id=user_id, mcp=mcp)
        return AgentRunner._execute_tool_by_name(
            context=context,
            name=tool_name,
            args=dict(args or {}),
            approved=True,
        )

    @staticmethod
    def _execute_tool_by_name(
        *,
        context,
        name: str,
        args: dict,
        approved: bool = False,
    ) -> tuple[str, ToolTrace]:
        if name == "set_reminder":
            args["user_id"] = context.user_id

        print(f"  [工具调用] {name}({args})")

        start = time.perf_counter()
        success = True
        error = ""
        allowed = True
        try:
            permission = get_tool_permission_gate().check(name, args, approved=approved)
            if permission.denied:
                success = False
                allowed = False
                error = permission.reason
                result = f"工具被权限策略拒绝: {permission.reason}"
            elif permission.requires_approval:
                approval = get_approval_store().create(
                    user_id=context.user_id,
                    tool_name=name,
                    args=args,
                    reason=permission.reason,
                    risk=permission.risk,
                )
                success = False
                allowed = False
                error = permission.reason
                result = (
                    "工具需要用户确认后才能执行: "
                    f"{permission.reason}\nApproval ID: {approval.id}"
                )
            else:
                func = TOOL_FUNCTIONS.get(name)
                if func:
                    result = func(**args)
                elif context.mcp and name in context.mcp.tool_map:
                    result = context.mcp.call_tool_sync(name, args)
                else:
                    success = False
                    result = f"未知工具: {name}"
        except Exception as exc:
            success = False
            error = str(exc)
            result = f"工具执行失败: {exc}"

        result = str(result)
        if result.startswith("工具被 workspace policy 拒绝:"):
            allowed = False
        if result.startswith("工具被权限策略拒绝:"):
            allowed = False
        if result.startswith("工具需要用户确认后才能执行:"):
            allowed = False
        if not allowed:
            success = False
            error = result
        duration_ms = int((time.perf_counter() - start) * 1000)
        log_tool_call(
            user_id=context.user_id,
            tool_name=name,
            args=args,
            allowed=allowed,
            success=success,
            result=result,
            duration_ms=duration_ms,
            error=error,
        )
        print(f"  [工具结果] {result}")
        return result, ToolTrace(name=name, args=args, result=result, success=success)

    @staticmethod
    def _parse_args(raw) -> dict:
        if isinstance(raw, dict):
            return dict(raw)
        if not raw:
            return {}
        parsed = json.loads(raw)
        return parsed or {}

    @staticmethod
    def _tool_result_message(tool_call_id: str, result: str) -> dict:
        return {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_call_id,
                    "content": result,
                }
            ],
        }

    @staticmethod
    def _is_approval_waiting_result(result: str) -> bool:
        return str(result).startswith("工具需要用户确认后才能执行:")
