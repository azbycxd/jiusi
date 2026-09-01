from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator

from tools.schemas import Evidence, ToolResult


class AgentStatus(str, Enum):
    RUNNING = "RUNNING"
    WAITING_USER = "WAITING_USER"
    FINISHED = "FINISHED"
    FAILED = "FAILED"
    HANDOFF = "HANDOFF"


class Intent(str, Enum):
    ORDER_FACTS = "ORDER_FACTS"
    UNKNOWN = "UNKNOWN"


class CapabilityState(BaseModel):
    """What the agent is permitted to do; never inferred by scanning code."""

    allowed_tools: tuple[str, ...] = (
        "get_order_facts",
        "get_joinable_team_facts",
        "search_group_buy_rules",
        "get_activity_facts",
        "get_user_eligibility_facts",
    )


def _data_paths(value: object, prefix: str = "") -> dict[str, str]:
    if isinstance(value, list):
        if not value:
            return {prefix: str(value)} if prefix else {}
        paths: dict[str, str] = {}
        for index, child in enumerate(value):
            item_prefix = f"{prefix}.{index}" if prefix else str(index)
            paths.update(_data_paths(child, item_prefix))
        return paths
    if not isinstance(value, dict):
        return {prefix: str(value)} if prefix else {}
    paths: dict[str, str] = {}
    for key, child in value.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        paths.update(_data_paths(child, path))
    return paths


class Observation(BaseModel):
    """Validated, model-visible result of one successful Tool invocation."""

    tool_name: str
    data: dict[str, Any]
    evidence: list[Evidence]

    @model_validator(mode="after")
    def evidence_must_describe_this_observation(self) -> "Observation":
        data_paths = _data_paths(self.data)
        prefix = f"{self.tool_name}."
        for item in self.evidence:
            if not item.kind.startswith(prefix):
                raise ValueError("Observation evidence must use the producing tool prefix")
            data_path = item.kind.removeprefix(prefix)
            if data_path not in data_paths or data_paths[data_path] != item.value:
                raise ValueError("Observation evidence must match normalized observation data")
        return self

    @classmethod
    def from_successful_tool_result(cls, tool_name: str, result: ToolResult) -> "Observation":
        if not result.success:
            raise ValueError("Failed ToolResult cannot produce an Observation")
        return cls(
            tool_name=tool_name,
            data=result.data,
            evidence=[
                item.model_copy(update={"kind": f"{tool_name}.{item.kind}"})
                for item in result.evidence
            ],
        )


class ContextState(BaseModel):
    """Information visible to the next controlled reasoning step for this task."""

    user_query: str = ""
    # V1 compatibility-only routing state. The dynamic Agent Path does not write or read it.
    intent: Intent = Intent.UNKNOWN
    out_trade_no: str | None = None
    team_id: str | None = None
    activity_id: str | None = None
    missing_fields: list[str] = Field(default_factory=list)
    tool_results: list[ToolResult] = Field(default_factory=list)
    observations: list[Observation] = Field(default_factory=list)
    model_decision: dict[str, Any] | None = None
    tool_call_history: list[str] = Field(default_factory=list)
    # Reserved for a later diagnosis stage. Phase 2B facts retrieval never sets it.
    diagnosis_code: str | None = None


class ControlState(BaseModel):
    """Execution limits and lifecycle, separate from the task context."""

    status: AgentStatus = AgentStatus.RUNNING
    # Number of extra calls after the initial Tool call; it is never the total call count.
    retry_count: int = 0
    tool_call_count: int = 0
    iteration_count: int = 0
    max_iterations: int = 6
    max_tool_calls: int = 3
    max_retries: int = 1
    # Model calls are counted independently from Tool calls and Tool retries.
    model_call_count: int = 0
    model_retry_count: int = 0
    max_model_retries: int = 1
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
    def team_id(self) -> str | None: return self.context.team_id
    @property
    def activity_id(self) -> str | None: return self.context.activity_id
    @property
    def missing_fields(self) -> list[str]: return self.context.missing_fields
    @property
    def tool_results(self) -> list[ToolResult]: return self.context.tool_results
    @property
    def observations(self) -> list[Observation]: return self.context.observations
    @property
    def diagnosis_code(self) -> str | None: return self.context.diagnosis_code
    @property
    def retry_count(self) -> int: return self.control.retry_count
    @property
    def tool_call_count(self) -> int: return self.control.tool_call_count
    @property
    def model_call_count(self) -> int: return self.control.model_call_count
    @property
    def model_retry_count(self) -> int: return self.control.model_retry_count
    @property
    def iteration_count(self) -> int: return self.control.iteration_count
    @property
    def needs_human(self) -> bool: return self.control.needs_human
    @property
    def final_answer(self) -> str | None: return self.control.final_answer
    @property
    def status(self) -> AgentStatus: return self.control.status
