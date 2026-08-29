from typing import Protocol, runtime_checkable

from pydantic import BaseModel

from agent.state import AgentState
from guardrails.auth_context import AuthContext
from tools.schemas import ToolResult


@runtime_checkable
class AgentTool(Protocol):
    """Self-described Tool contract; registry infrastructure owns no business metadata."""

    name: str
    description: str
    arguments_schema: type[BaseModel]

    def run(self, state: AgentState, arguments: BaseModel) -> ToolResult: ...


class MarketClient(Protocol):
    """High-level Java order-facts client boundary used by the business Tool."""

    def get_order_facts(self, auth: AuthContext, out_trade_no: str) -> ToolResult: ...
