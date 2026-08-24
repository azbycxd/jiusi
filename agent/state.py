from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from tools.schemas import ToolResult


class AgentStatus(str, Enum):
    RUNNING = "RUNNING"
    WAITING_USER = "WAITING_USER"
    FINISHED = "FINISHED"
    FAILED = "FAILED"
    HANDOFF = "HANDOFF"


class Intent(str, Enum):
    ORDER_DIAGNOSIS = "ORDER_DIAGNOSIS"
    UNKNOWN = "UNKNOWN"


class CapabilityState(BaseModel):
    """What the agent is permitted to do; never inferred by scanning code."""

    allowed_tools: tuple[str, ...] = ("get_order_diagnosis",)


class ContextState(BaseModel):
    """Information visible to the next controlled reasoning step for this task."""

    user_query: str = ""
    intent: Intent = Intent.UNKNOWN
    out_trade_no: str | None = None
    team_id: str | None = None
    activity_id: str | None = None
    missing_fields: list[str] = Field(default_factory=list)
    tool_results: list[ToolResult] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    diagnosis_code: str | None = None


class ControlState(BaseModel):
    """Execution limits and lifecycle, separate from the task context."""

    status: AgentStatus = AgentStatus.RUNNING
    retry_count: int = 0
    tool_call_count: int = 0
    iteration_count: int = 0
    max_iterations: int = 6
    max_tool_calls: int = 3
    max_retries: int = 1
    tool_timeout_seconds: float = 2.0
    needs_human: bool = False
    final_answer: str | None = None


class AgentState(BaseModel):
    """Per-session task state. Identity comes only from trusted request context."""

    session_id: str
    authenticated_user_id: str
    capability: CapabilityState = Field(default_factory=CapabilityState)
    context: ContextState = Field(default_factory=ContextState)
    control: ControlState = Field(default_factory=ControlState)

    @property
    def user_query(self) -> str: return self.context.user_query
    @property
    def intent(self) -> Intent: return self.context.intent
    @property
    def out_trade_no(self) -> str | None: return self.context.out_trade_no
    @property
    def missing_fields(self) -> list[str]: return self.context.missing_fields
    @property
    def tool_results(self) -> list[ToolResult]: return self.context.tool_results
    @property
    def evidence(self) -> list[dict[str, Any]]: return self.context.evidence
    @property
    def diagnosis_code(self) -> str | None: return self.context.diagnosis_code
    @property
    def retry_count(self) -> int: return self.control.retry_count
    @property
    def tool_call_count(self) -> int: return self.control.tool_call_count
    @property
    def iteration_count(self) -> int: return self.control.iteration_count
    @property
    def needs_human(self) -> bool: return self.control.needs_human
    @property
    def final_answer(self) -> str | None: return self.control.final_answer
    @property
    def status(self) -> AgentStatus: return self.control.status
