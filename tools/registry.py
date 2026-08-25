from agent.state import AgentState
from tools.arguments import ORDER_FACTS_ARGUMENT_SCHEMA, normalize_order_facts_arguments
from tools.base import Tool
from tools.schemas import ToolResult


class ToolRegistry:
    """An explicit allowlist. No reflection or automatic function exposure is used."""

    def __init__(self, tools: list[Tool]) -> None:
        self._tools = {tool.name: tool for tool in tools}

    @property
    def allowed_names(self) -> tuple[str, ...]:
        return tuple(self._tools)

    @property
    def available_tools(self) -> tuple[dict[str, object], ...]:
        descriptions = {
            "get_order_facts": "Read trusted order, team, activity, and reference facts for an external order number.",
        }
        return tuple(
            {
                "name": name,
                "description": descriptions.get(name, "Registered business tool."),
                "parameters_schema": ORDER_FACTS_ARGUMENT_SCHEMA if name == "get_order_facts" else {},
            }
            for name in self._tools
        )

    def validate_arguments(self, name: str, arguments: object) -> dict[str, str] | None:
        if name not in self._tools:
            return None
        if name == "get_order_facts":
            return normalize_order_facts_arguments(arguments)
        return None

    def call(self, name: str, state: AgentState) -> ToolResult:
        if name not in state.capability.allowed_tools or name not in self._tools:
            return ToolResult.infrastructure_failure(
                "TOOL_NOT_ALLOWED", "该工具不在当前 Agent 白名单中。", retryable=False, source="tool_registry"
            )
        return self._tools[name].run(state)
