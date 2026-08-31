from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from evals.contracts import EvalCase, EvalCaseStatus, EvalExecution, ExpectedFinalAction, ToolCallRecord
from evals.deterministic import run_deterministic_case
from evals.harness import aggregate_results, evaluate_case
from evals.run import REAL_BEHAVIOR_CATEGORIES, load_cases, run_cases


def case(**overrides) -> EvalCase:
    payload = {
        "case_id": "eval-unit", "category": "unit", "user_query": "测试", "description": "测试断言",
        "expected_final_action": "ANSWER", "required_tools": [], "forbidden_tools": [],
        "required_evidence_prefixes": [], "forbidden_evidence_prefixes": [], "max_tool_calls": 3,
    }
    payload.update(overrides)
    return EvalCase.model_validate(payload)


def execution(**overrides) -> EvalExecution:
    payload = {"final_action": "ANSWER", "tool_calls": [], "observations": [], "used_evidence": [], "final_answer": "安全回答"}
    payload.update(overrides)
    return EvalExecution.model_validate(payload)


def test_eval_case_contract_is_strict() -> None:
    with pytest.raises(ValidationError):
        EvalCase.model_validate({"case_id": "x", "category": "x", "user_query": "x", "description": "x", "expected_final_action": "FINISHED"})
    with pytest.raises(ValidationError):
        EvalCase.model_validate({**case().model_dump(), "unknown": True})


def test_case_dataset_has_all_required_category_counts() -> None:
    cases = load_cases()
    counts = {category: sum(item.category == category for item in cases) for category in {item.category for item in cases}}
    assert len(cases) == 50
    assert counts == {
        "rule_knowledge": 8, "realtime_facts": 6, "multi_source": 6, "dynamic_chaining": 4,
        "handoff": 6, "injection": 5, "unrelated": 4, "capability": 3, "evidence_attack": 4, "repeat_loop": 4,
    }


def test_real_behavior_categories_select_exactly_42_cases() -> None:
    cases = load_cases()
    selected = [case for case in cases if case.category in REAL_BEHAVIOR_CATEGORIES]
    assert len(selected) == 42
    assert {case.category for case in selected} == set(REAL_BEHAVIOR_CATEGORIES)


def test_required_forbidden_and_order_assertions() -> None:
    required = evaluate_case(case(required_tools=("get_order_facts",)), execution())
    assert required.status is EvalCaseStatus.FAIL and "TOOL_SELECTION" in required.failure_types
    forbidden = evaluate_case(case(forbidden_tools=("search_group_buy_rules",)), execution(tool_calls=[ToolCallRecord(tool_name="search_group_buy_rules", arguments={})]))
    assert forbidden.status is EvalCaseStatus.FAIL and "FORBIDDEN_TOOL" in forbidden.failure_types
    dynamic = evaluate_case(case(required_tools=("a", "b")), execution(tool_calls=[ToolCallRecord(tool_name="b", arguments={}), ToolCallRecord(tool_name="a", arguments={})]))
    assert dynamic.status is EvalCaseStatus.PASS
    ordered = evaluate_case(case(required_tools=("a", "b"), allowed_tool_orders=(("a", "b"),)), execution(tool_calls=[ToolCallRecord(tool_name="b", arguments={}), ToolCallRecord(tool_name="a", arguments={})]))
    assert ordered.status is EvalCaseStatus.FAIL


def test_grounding_evidence_claim_and_guard_assertions() -> None:
    base = execution(
        tool_calls=[ToolCallRecord(tool_name="get_joinable_team_facts", arguments={"activityId": 100123})],
        observations=[{"tool_name": "get_order_facts", "data": {"references": {"activity_id": 100123}}}],
        used_evidence=["get_order_facts.team.status"],
    )
    grounded = evaluate_case(case(
        required_tools=("get_joinable_team_facts",), required_evidence_prefixes=("get_order_facts.team.",),
        expected_business_constraints={"parameter_grounding": [{"tool_name": "get_joinable_team_facts", "argument": "activityId", "source_tool": "get_order_facts", "source_path": "references.activity_id"}]},
    ), base)
    assert grounded.status is EvalCaseStatus.PASS
    ungrounded = evaluate_case(case(expected_business_constraints={"parameter_grounding": [{"tool_name": "get_joinable_team_facts", "argument": "activityId", "source_tool": "get_order_facts", "source_path": "references.activity_id"}]}), execution(tool_calls=[ToolCallRecord(tool_name="get_joinable_team_facts", arguments={"activityId": 9})], observations=base.observations))
    assert "PARAMETER_GROUNDING" in ungrounded.failure_types
    evidence = evaluate_case(case(forbidden_evidence_prefixes=("available_tools.",)), execution(used_evidence=["available_tools.x"]))
    assert "EVIDENCE" in evidence.failure_types
    claim = evaluate_case(case(expected_business_constraints={"forbidden_answer_claims": ["已经到账"]}), execution(final_answer="退款已经到账"))
    assert "UNSUPPORTED_CLAIM" in claim.failure_types
    pattern = evaluate_case(
        case(expected_business_constraints={"forbidden_answer_patterns": [r"预计\s*\d+\s*天到账"]}),
        execution(final_answer="预计 3 天到账"),
    )
    assert "UNSUPPORTED_CLAIM" in pattern.failure_types
    guard = evaluate_case(case(expected_final_action="HANDOFF", expected_guard_error="MODEL_EVIDENCE_NOT_AVAILABLE"), execution(final_action="HANDOFF", guard_errors=["MODEL_EVIDENCE_NOT_AVAILABLE"]))
    assert guard.status is EvalCaseStatus.PASS


def test_aggregate_and_provider_infrastructure_classification() -> None:
    passed = evaluate_case(case(case_id="pass"), execution())
    infra = evaluate_case(case(case_id="infra"), execution(infrastructure_error="MODEL_TIMEOUT", model_retry_count=1))
    aggregate = aggregate_results([passed, infra])
    assert infra.status is EvalCaseStatus.INFRA_FAILURE
    assert aggregate["provider_failure_count"] == 1 and aggregate["provider_retry_count"] == 1
    assert aggregate["pass_rate"] == 0.5
    assert infra.failure_classification == "PROVIDER_RELIABILITY"


def test_failure_classification_and_guard_attempt_are_safe_result_metadata() -> None:
    forbidden = evaluate_case(
        case(forbidden_tools=("search_group_buy_rules",)),
        execution(tool_calls=[ToolCallRecord(tool_name="search_group_buy_rules", arguments={})]),
    )
    blocked = evaluate_case(case(), execution(guard_errors=["MODEL_TOOL_ARGUMENTS_INVALID"]))
    assert forbidden.failure_classification == "TOOL_SELECTION"
    assert blocked.status is EvalCaseStatus.PASS and blocked.model_attempt_blocked_by_guard is True


def test_deterministic_runner_exercises_all_cases_without_live_provider() -> None:
    cases = load_cases()
    output = run_cases(cases, mode="deterministic")
    assert output["aggregate"]["total"] == 50
    assert output["aggregate"]["passed"] == 50
    assert output["aggregate"]["provider_failure_count"] == 0
    assert run_deterministic_case(next(item for item in cases if item.case_id == "chain_order_joinable_001")).tool_calls[1].arguments["activityId"] == 100123


def test_case_loader_rejects_duplicate_ids(tmp_path) -> None:
    first = case().model_dump(mode="json")
    path = tmp_path / "cases.json"
    path.write_text(json.dumps({"cases": [first, first]}), encoding="utf-8")
    with pytest.raises(ValueError, match="unique"):
        load_cases(path)
