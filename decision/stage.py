from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from decision.errors import ModelAdapterError
from decision.model import DecisionModel
from decision.normalization import normalize_agent_decision_payload
from decision.schemas import AgentDecision, AvailableTool, DecisionContext, parse_agent_decision
from decision.telemetry import ModelTelemetry
from decision.validation import canonicalize_evidence_paths, validate_evidence


@dataclass(frozen=True)
class DecisionStageResult:
    decision: AgentDecision | None = None
    error_code: str | None = None
    retryable: bool = False
    telemetry: ModelTelemetry | None = None
    started_at: float | None = None


class DecisionStage:
    """Pure model invocation/schema/evidence boundary; it never mutates AgentState."""

    def __init__(self, model: DecisionModel, available_tools: tuple[dict[str, Any], ...]) -> None:
        self._model = model
        self._available_tools = available_tools

    def build_context(self, *, user_query: str, facts: dict, evidence: list[dict]) -> DecisionContext:
        return DecisionContext(
            user_query=user_query,
            facts=facts,
            evidence=evidence,
            available_tools=tuple(AvailableTool.model_validate(tool) for tool in self._available_tools),
        )

    def decide(self, context: DecisionContext) -> DecisionStageResult:
        try:
            raw_decision = self._model.decide(context)
        except ModelAdapterError as error:
            return DecisionStageResult(error_code=error.error_code, retryable=error.retryable)
        except Exception:
            return DecisionStageResult(error_code="MODEL_INVOCATION_ERROR")
        telemetry = getattr(self._model, "last_telemetry", None)
        try:
            decision = parse_agent_decision(normalize_agent_decision_payload(raw_decision))
        except ValidationError:
            return DecisionStageResult(error_code="MODEL_CONTRACT_MISMATCH", retryable=True, telemetry=telemetry)
        decision = canonicalize_evidence_paths(decision)
        validation = validate_evidence(decision, facts=context.facts)
        if not validation.valid:
            return DecisionStageResult(error_code=validation.error_code, telemetry=telemetry)
        return DecisionStageResult(decision=decision, telemetry=telemetry)
