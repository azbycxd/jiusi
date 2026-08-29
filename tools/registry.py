from pydantic import BaseModel, ValidationError

from agent.state import AgentState
from tools.base import AgentTool
from tools.schemas import ToolResult


class ToolRegistry:
    """An explicit allowlist. No reflection or automatic function exposure is used."""

    def __init__(self, tools: list[AgentTool]) -> None:
        self._tools: dict[str, AgentTool] = {}
        for tool in tools:
            self.register(tool)

    def register(self, tool: AgentTool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Duplicate Tool name: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> AgentTool | None:
        return self._tools.get(name)

    @property
    def allowed_names(self) -> tuple[str, ...]:
        return tuple(self._tools)

    @property
    def available_tools(self) -> tuple[dict[str, object], ...]:
        return tuple(
            {
                "name": tool.name,
                "description": tool.description,
                "parameters_schema": tool.arguments_schema.model_json_schema(by_alias=True),
            }
            for tool in self._tools.values()
        )

    def validate_arguments(self, name: str, arguments: object) -> BaseModel | None:
        tool = self.get(name)
        if tool is None:
            return None
        try:
            return tool.arguments_schema.model_validate(arguments)
        except ValidationError:
            return None

    def legacy_invocation(self, state: AgentState) -> tuple[str, BaseModel] | None:
        """Find one Tool-owned V1 compatibility adapter without knowing its business schema."""
        candidates: list[tuple[str, BaseModel]] = []
        for tool in self._tools.values():
            argument_factory = getattr(tool, "arguments_from_legacy_state", None)
            if not callable(argument_factory):
                continue
            arguments = argument_factory(state)
            if isinstance(arguments, tool.arguments_schema):
                candidates.append((tool.name, arguments))
        return candidates[0] if len(candidates) == 1 else None

    def call(self, name: str, state: AgentState, arguments: BaseModel) -> ToolResult:
        tool = self.get(name)
        if name not in state.capability.allowed_tools or tool is None:
            return ToolResult.infrastructure_failure(
                "TOOL_NOT_ALLOWED", "该工具不在当前 Agent 白名单中。", retryable=False, source="tool_registry"
            )
        if not isinstance(arguments, tool.arguments_schema):
            return ToolResult.infrastructure_failure(
                "TOOL_ARGUMENTS_INVALID", "工具参数不符合契约。", retryable=False, source="tool_registry"
            )
        return tool.run(state, arguments)
