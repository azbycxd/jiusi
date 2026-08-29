from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field

from agent.state import AgentState
from guardrails.auth_context import AuthContext
from tools.schemas import ToolResult


class RepeatPolicy(BaseModel):
    """Per-Tool limit for identical model-requested calls within one task."""

    repeatable: bool = False
    max_same_call: int = Field(default=1, ge=1)

    @property
    def allowed_same_call_count(self) -> int:
        """Non-repeatable Tools always permit exactly their initial call."""
        return self.max_same_call if self.repeatable else 1


@runtime_checkable
class AgentTool(Protocol):
    """Self-described Tool contract; registry infrastructure owns no business metadata."""

    name: str
    description: str
    arguments_schema: type[BaseModel]
    repeat_policy: RepeatPolicy

    def run(self, state: AgentState, arguments: BaseModel) -> ToolResult: ...


class MarketClient(Protocol):
    """High-level Java order-facts client boundary used by the business Tool."""

    def get_order_facts(self, auth: AuthContext, out_trade_no: str) -> ToolResult: ...


class JoinableTeamFactsClient(Protocol):
    """High-level Java joinable-team-facts boundary used by the business Tool."""

    def get_joinable_team_facts(self, auth: AuthContext, activity_id: int) -> ToolResult: ...
