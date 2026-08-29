from __future__ import annotations

from dataclasses import dataclass

from agent.state import Observation
from decision.schemas import AgentDecision, AnswerDecision


@dataclass(frozen=True)
class DecisionValidationResult:
    valid: bool
    error_code: str | None = None


def _observation_evidence_paths(observations: list[Observation]) -> set[str]:
    return {item.kind for observation in observations for item in observation.evidence}


def canonicalize_evidence_paths(
    decision: AgentDecision, *, observations: list[Observation]
) -> AgentDecision:
    """Migrate legacy facts paths only when one Observation proves an unambiguous match."""
    if not isinstance(decision, AnswerDecision):
        return decision
    available_paths = _observation_evidence_paths(observations)

    def canonicalize(path: str) -> str:
        if path in available_paths:
            return path
        legacy_path = path.removeprefix("facts.")
        matches = [
            f"{observation.tool_name}.{legacy_path}"
            for observation in observations
            if f"{observation.tool_name}.{legacy_path}" in available_paths
        ]
        return matches[0] if len(matches) == 1 else path

    return decision.model_copy(
        update={"used_evidence": [canonicalize(path) for path in decision.used_evidence]}
    )


def validate_evidence(
    decision: AgentDecision, *, observations: list[Observation]
) -> DecisionValidationResult:
    if not isinstance(decision, AnswerDecision):
        return DecisionValidationResult(True)
    available_paths = _observation_evidence_paths(observations)
    if any(path not in available_paths for path in decision.used_evidence):
        return DecisionValidationResult(False, "MODEL_EVIDENCE_NOT_AVAILABLE")
    return DecisionValidationResult(True)
