from __future__ import annotations

from dataclasses import dataclass

from decision.schemas import AgentDecision, AnswerDecision


@dataclass(frozen=True)
class DecisionValidationResult:
    valid: bool
    error_code: str | None = None


def _fact_paths(value: object, prefix: str = "") -> set[str]:
    if not isinstance(value, dict):
        return {prefix} if prefix else set()
    paths: set[str] = set()
    for key, child in value.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        paths.update(_fact_paths(child, path))
    return paths


def canonicalize_evidence_paths(decision: AgentDecision) -> AgentDecision:
    """Accept only the explicit outer `facts.` prefix emitted by some providers."""
    if not isinstance(decision, AnswerDecision):
        return decision
    return decision.model_copy(
        update={"used_evidence": [path.removeprefix("facts.") for path in decision.used_evidence]}
    )


def validate_evidence(decision: AgentDecision, *, facts: dict) -> DecisionValidationResult:
    if not isinstance(decision, AnswerDecision):
        return DecisionValidationResult(True)
    available_paths = _fact_paths(facts)
    if any(path not in available_paths for path in decision.used_evidence):
        return DecisionValidationResult(False, "MODEL_EVIDENCE_NOT_AVAILABLE")
    return DecisionValidationResult(True)
