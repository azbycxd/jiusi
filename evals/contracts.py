from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ExpectedFinalAction(str, Enum):
    ANSWER = "ANSWER"
    HANDOFF = "HANDOFF"


class EvalCase(BaseModel):
    """Strict, data-only contract for one deterministic or live Agent evaluation."""

    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=1)
    category: str = Field(min_length=1)
    user_query: str = Field(min_length=1)
    description: str = Field(min_length=1)
    requires_live_java: bool = False
    requires_live_provider: bool = False
    expected_final_action: ExpectedFinalAction
    required_tools: tuple[str, ...] = ()
    forbidden_tools: tuple[str, ...] = ()
    allowed_tool_orders: tuple[tuple[str, ...], ...] = ()
    required_evidence_prefixes: tuple[str, ...] = ()
    forbidden_evidence_prefixes: tuple[str, ...] = ()
    max_tool_calls: int = Field(default=3, ge=0)
    expected_business_constraints: dict[str, Any] = Field(default_factory=dict)
    expected_guard_error: str | None = None
    deterministic_fixture: str = "normal"
    notes: str = ""

    @field_validator("case_id", "category", "user_query", "description")
    @classmethod
    def required_text_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("required text must not be blank")
        return value


class ToolCallRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: str
    arguments: dict[str, Any]


class EvalExecution(BaseModel):
    """Safe post-execution view consumed by deterministic assertions."""

    model_config = ConfigDict(extra="forbid")

    final_action: ExpectedFinalAction | None = None
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    observations: list[dict[str, Any]] = Field(default_factory=list)
    used_evidence: list[str] = Field(default_factory=list)
    final_answer: str = ""
    model_call_count: int = 0
    model_retry_count: int = 0
    retry_count: int = 0
    guard_errors: list[str] = Field(default_factory=list)
    infrastructure_error: str | None = None


class EvalCaseStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    INFRA_FAILURE = "INFRA_FAILURE"


class EvalCaseResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    category: str
    status: EvalCaseStatus
    final_action: ExpectedFinalAction | None
    tool_sequence: list[str]
    tool_call_count: int
    model_call_count: int
    observation_count: int
    used_evidence: list[str]
    failure_reasons: list[str] = Field(default_factory=list)
    failure_types: list[str] = Field(default_factory=list)
    failure_classification: str = "PASS"
    guard_errors: list[str] = Field(default_factory=list)
    model_attempt_blocked_by_guard: bool = False
    provider_retry_count: int = 0
