from typing import Protocol

from agent.state import AgentState
from tools.schemas import ToolResult


class Tool(Protocol):
    name: str

    def run(self, state: AgentState) -> ToolResult: ...
