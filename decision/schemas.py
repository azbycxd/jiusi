from __future__ import annotations

from enum import Enum
from typing import Annotated, Any, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator

from agent.state import Observation


class AgentAction(str, Enum):
    CALL_TOOL = "CALL_TOOL"
    ANSWER = "ANSWER"
    HANDOFF = "HANDOFF"


class AvailableTool(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str
    parameters_schema: dict[str, Any]


class DecisionContext(BaseModel):
    """The complete model-visible context; identity, headers, traces and exceptions are excluded."""

    model_config = ConfigDict(extra="forbid")

    user_query: str
    observations: list[Observation] = Field(default_factory=list)
    available_tools: tuple[AvailableTool, ...]

    @property
    def evidence(self) -> list[dict[str, Any]]:
        """Evidence is derived from observations; it is never an independent State source."""
        return [
            item.model_dump(mode="json")
            for observation in self.observations
            for item in observation.evidence
        ]


class CallToolDecision(BaseModel):
    """Only the fields necessary to request one allowed Tool."""

    model_config = ConfigDict(extra="forbid")

    action: Literal[AgentAction.CALL_TOOL]
    tool_name: str
    tool_arguments: dict[str, Any]


class AnswerDecision(BaseModel):
    """Only the fields necessary to answer from current facts or general capability."""

    model_config = ConfigDict(extra="forbid")

    action: Literal[AgentAction.ANSWER]
    final_answer: str
    used_evidence: list[str] = Field(default_factory=list)

    @field_validator("final_answer")
    @classmethod
    def final_answer_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("ANSWER requires a non-blank final_answer")
        return value


class HandoffDecision(BaseModel):
    """A pure control decision; the harness owns the user-facing fallback text."""

    model_config = ConfigDict(extra="forbid")

    action: Literal[AgentAction.HANDOFF]
    missing_information: list[str] = Field(default_factory=list)


AgentDecision: TypeAlias = Annotated[
    CallToolDecision | AnswerDecision | HandoffDecision,
    Field(discriminator="action"),
]

_AGENT_DECISION_ADAPTER = TypeAdapter(AgentDecision)


def parse_agent_decision(payload: object) -> AgentDecision:
    """Parse the sole action-specific Decision protocol used by the Agent Loop."""
    return _AGENT_DECISION_ADAPTER.validate_python(payload)
