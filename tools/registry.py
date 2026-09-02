from pydantic import BaseModel, ValidationError

from agent.state import AgentState
from tools.base import AgentTool, RepeatPolicy
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

    def repeat_policy(self, name: str) -> RepeatPolicy | None:
        """Return a Tool-owned repeat contract without knowing its business semantics."""
        tool = self.get(name)
        return tool.repeat_policy if tool is not None else None

    def diagnosis_dimension(self, name: str) -> str | None:
        """Return optional internal completion metadata; never part of Tool arguments."""
        value = getattr(self.get(name), "diagnosis_dimension", None)
        return value if isinstance(value, str) and value else None

    def diagnosis_dimensions(self, allowed_tools: tuple[str, ...]) -> tuple[str, ...]:
        """Expose only registered, currently allowed dimensions in registry order."""
        dimensions: list[str] = []
        for name in self.allowed_names:
            if name not in allowed_tools:
                continue
            dimension = self.diagnosis_dimension(name)
            if dimension is not None and dimension not in dimensions:
                dimensions.append(dimension)
        return tuple(dimensions)

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
