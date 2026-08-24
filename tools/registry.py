from agent.state import AgentState
from tools.base import Tool
from tools.schemas import ToolResult


class ToolRegistry:
    """An explicit allowlist. No reflection or automatic function exposure is used."""

    def __init__(self, tools: list[Tool]) -> None:
        self._tools = {tool.name: tool for tool in tools}

    @property
    def allowed_names(self) -> tuple[str, ...]:
        return tuple(self._tools)

    def call(self, name: str, state: AgentState) -> ToolResult:
        if name not in state.capability.allowed_tools or name not in self._tools:
            return ToolResult.infrastructure_failure(
                "TOOL_NOT_ALLOWED", "该工具不在当前 Agent 白名单中。", retryable=False, source="tool_registry"
            )
        return self._tools[name].run(state)
