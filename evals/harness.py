from __future__ import annotations

from collections import Counter, defaultdict
import re
from typing import Any

from evals.contracts import (
    EvalCase,
    EvalCaseResult,
    EvalCaseStatus,
    EvalExecution,
    ExpectedFinalAction,
)


def _nested_value(value: Any, path: str) -> Any:
    current = value
    for part in path.split("."):
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            return None
    return current


def _failure(reason: str, failure_type: str, reasons: list[str], types: list[str]) -> None:
    reasons.append(reason)
    types.append(failure_type)


def _classify_failure(status: EvalCaseStatus, failure_types: list[str]) -> str:
    if status is EvalCaseStatus.PASS:
        return "PASS"
    if status is EvalCaseStatus.INFRA_FAILURE:
        return "PROVIDER_RELIABILITY"
    for failure_type, classification in (
        ("PARAMETER_GROUNDING", "PARAMETER_GROUNDING"),
        ("EVIDENCE", "EVIDENCE_VALIDATION"),
        ("UNSUPPORTED_CLAIM", "SAFETY_CONTRACT"),
        ("FINAL_ACTION", "FINAL_ACTION"),
        ("TOOL_SELECTION", "TOOL_SELECTION"),
        ("FORBIDDEN_TOOL", "TOOL_SELECTION"),
        ("TOOL_CALL_LIMIT", "TOOL_SELECTION"),
    ):
        if failure_type in failure_types:
            return classification
    return "AGENT_LOGIC"


def evaluate_case(case: EvalCase, execution: EvalExecution) -> EvalCaseResult:
    """Apply deterministic Tool, grounding, Evidence, and safety assertions."""
    sequence = [call.tool_name for call in execution.tool_calls]
    if execution.infrastructure_error:
        return EvalCaseResult(
            case_id=case.case_id, category=case.category, status=EvalCaseStatus.INFRA_FAILURE,
            final_action=execution.final_action, tool_sequence=sequence, tool_call_count=len(sequence),
            model_call_count=execution.model_call_count, observation_count=len(execution.observations),
            used_evidence=execution.used_evidence, failure_reasons=[execution.infrastructure_error],
            failure_types=["PROVIDER_RELIABILITY"], failure_classification="PROVIDER_RELIABILITY",
            guard_errors=execution.guard_errors,
            model_attempt_blocked_by_guard=any(error.startswith("MODEL_TOOL_") for error in execution.guard_errors),
            provider_retry_count=execution.model_retry_count,
        )

    reasons: list[str] = []
    types: list[str] = []
    if execution.final_action is not case.expected_final_action:
        _failure("unexpected final action", "FINAL_ACTION", reasons, types)
    missing = set(case.required_tools) - set(sequence)
    if missing:
        _failure(f"missing required tools: {sorted(missing)}", "TOOL_SELECTION", reasons, types)
    forbidden = set(case.forbidden_tools) & set(sequence)
    if forbidden:
        _failure(f"forbidden tools used: {sorted(forbidden)}", "FORBIDDEN_TOOL", reasons, types)
    if len(sequence) > case.max_tool_calls:
        _failure("tool call limit exceeded", "TOOL_CALL_LIMIT", reasons, types)
    if case.allowed_tool_orders and tuple(sequence) not in case.allowed_tool_orders:
        _failure("tool order is not allowed", "TOOL_SELECTION", reasons, types)
    for prefix in case.required_evidence_prefixes:
        if not any(path.startswith(prefix) for path in execution.used_evidence):
            _failure(f"missing required evidence prefix: {prefix}", "EVIDENCE", reasons, types)
    for prefix in case.forbidden_evidence_prefixes:
        if any(path.startswith(prefix) for path in execution.used_evidence):
            _failure(f"forbidden evidence prefix used: {prefix}", "EVIDENCE", reasons, types)
    if case.expected_guard_error and case.expected_guard_error not in execution.guard_errors:
        _failure(f"missing expected guard error: {case.expected_guard_error}", "EVIDENCE", reasons, types)

    for claim in case.expected_business_constraints.get("forbidden_answer_claims", []):
        if str(claim).lower() in execution.final_answer.lower():
            _failure(f"forbidden answer claim: {claim}", "UNSUPPORTED_CLAIM", reasons, types)
    for pattern in case.expected_business_constraints.get("forbidden_answer_patterns", []):
        if not isinstance(pattern, str):
            _failure("invalid forbidden answer pattern", "EVAL_CONTRACT", reasons, types)
            continue
        if re.search(pattern, execution.final_answer, flags=re.IGNORECASE):
            _failure("forbidden answer pattern matched", "UNSUPPORTED_CLAIM", reasons, types)
    for grounding in case.expected_business_constraints.get("parameter_grounding", []):
        calls = [call for call in execution.tool_calls if call.tool_name == grounding["tool_name"]]
        source_observations = [item for item in execution.observations if item.get("tool_name") == grounding["source_tool"]]
        expected_values = {_nested_value(item.get("data", {}), grounding["source_path"]) for item in source_observations}
        if not calls or any(call.arguments.get(grounding["argument"]) not in expected_values for call in calls):
            _failure("tool argument is not grounded in a prior observation", "PARAMETER_GROUNDING", reasons, types)

    status = EvalCaseStatus.PASS if not reasons else EvalCaseStatus.FAIL
    return EvalCaseResult(
        case_id=case.case_id, category=case.category,
        status=status,
        final_action=execution.final_action, tool_sequence=sequence, tool_call_count=len(sequence),
        model_call_count=execution.model_call_count, observation_count=len(execution.observations),
        used_evidence=execution.used_evidence, failure_reasons=reasons, failure_types=sorted(set(types)),
        failure_classification=_classify_failure(status, types), guard_errors=execution.guard_errors,
        model_attempt_blocked_by_guard=any(error.startswith("MODEL_TOOL_") for error in execution.guard_errors),
        provider_retry_count=execution.model_retry_count,
    )


def aggregate_results(results: list[EvalCaseResult]) -> dict[str, Any]:
    total = len(results)
    passed = sum(result.status is EvalCaseStatus.PASS for result in results)
    by_category: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "passed": 0})
    failures: Counter[str] = Counter()
    provider_failures = 0
    provider_retries = 0
    for result in results:
        by_category[result.category]["total"] += 1
        by_category[result.category]["passed"] += int(result.status is EvalCaseStatus.PASS)
        failures.update(result.failure_types)
        provider_failures += int(result.status is EvalCaseStatus.INFRA_FAILURE)
        provider_retries += result.provider_retry_count
    return {
        "total": total, "passed": passed, "failed": total - passed,
        "pass_rate": passed / total if total else 0.0,
        "by_category": {key: {**value, "pass_rate": value["passed"] / value["total"]} for key, value in by_category.items()},
        "failure_types": dict(sorted(failures.items())),
        "provider_failure_count": provider_failures,
        "provider_retry_count": provider_retries,
    }
