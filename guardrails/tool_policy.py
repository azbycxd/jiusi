from agent.state import AgentState


def is_tool_allowed(state: AgentState, tool_name: str) -> bool:
    return tool_name in state.capability.allowed_tools
