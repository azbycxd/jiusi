from typing import Protocol

from agent.state import AgentState
from guardrails.auth_context import AuthContext
from tools.schemas import ToolResult


class Tool(Protocol):
    name: str

    def run(self, state: AgentState) -> ToolResult: ...


class MarketClient(Protocol):
    """High-level Java order-facts client boundary used by the business Tool."""

    def get_order_facts(self, auth: AuthContext, out_trade_no: str) -> ToolResult: ...
