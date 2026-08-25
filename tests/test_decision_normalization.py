from __future__ import annotations

import pytest
from pydantic import ValidationError

from decision.normalization import normalize_agent_decision_payload
from decision.schemas import AnswerDecision, CallToolDecision, HandoffDecision, parse_agent_decision
from decision.validation import canonicalize_evidence_paths, validate_evidence
from tools.arguments import normalize_order_facts_arguments


def call_tool(**overrides) -> dict:
    payload = {
        "action": "CALL_TOOL",
        "tool_name": "get_order_facts",
        "tool_arguments": {"outTradeNo": "202608240001"},
    }
    payload.update(overrides)
    return payload


def test_legal_call_tool_requires_no_answer_null_fields() -> None:
    decision = parse_agent_decision(call_tool())
    assert isinstance(decision, CallToolDecision)


def test_call_tool_empty_answer_placeholder_is_removed_but_nonempty_answer_is_rejected() -> None:
    normalized = normalize_agent_decision_payload(call_tool(final_answer=""))
    assert "final_answer" not in normalized
    assert isinstance(parse_agent_decision(normalized), CallToolDecision)
    with pytest.raises(ValidationError):
        parse_agent_decision(normalize_agent_decision_payload(call_tool(final_answer="订单已经失败")))


def test_answer_and_handoff_empty_irrelevant_placeholders_are_removed() -> None:
    answer = parse_agent_decision(
        normalize_agent_decision_payload(
            {"action": "ANSWER", "final_answer": "能力说明", "used_evidence": [], "tool_arguments": {}, "tool_name": " "}
        )
    )
    handoff = parse_agent_decision(
        normalize_agent_decision_payload(
            {"action": "HANDOFF", "missing_information": ["refund status"], "final_answer": " ", "tool_arguments": {}}
        )
    )
    assert isinstance(answer, AnswerDecision)
    assert isinstance(handoff, HandoffDecision)


def test_handoff_missing_information_string_is_wrapped_without_rewriting_text() -> None:
    raw = {"action": "HANDOFF", "missing_information": "refund status"}
    normalized = normalize_agent_decision_payload(raw)
    assert normalized["missing_information"] == ["refund status"]
    assert isinstance(parse_agent_decision(normalized), HandoffDecision)


def test_handoff_list_is_preserved_empty_string_is_removed_and_invalid_values_are_rejected() -> None:
    assert normalize_agent_decision_payload(
        {"action": "HANDOFF", "missing_information": ["refund status"]}
    )["missing_information"] == ["refund status"]
    assert "missing_information" not in normalize_agent_decision_payload(
        {"action": "HANDOFF", "missing_information": ""}
    )
    for invalid in (123, {}, [123], ["合法", 123]):
        with pytest.raises(ValidationError):
            parse_agent_decision(normalize_agent_decision_payload({"action": "HANDOFF", "missing_information": invalid}))


def test_answer_and_call_tool_string_missing_information_are_not_normalized() -> None:
    for payload in (
        {"action": "ANSWER", "final_answer": "能力说明", "missing_information": "xxx"},
        call_tool(missing_information="xxx"),
    ):
        with pytest.raises(ValidationError):
            parse_agent_decision(normalize_agent_decision_payload(payload))


def test_answer_facts_prefix_is_canonicalized_and_unknown_path_is_rejected() -> None:
    accepted = parse_agent_decision(
        {"action": "ANSWER", "final_answer": "已获取", "used_evidence": ["facts.order.status"]}
    )
    accepted = canonicalize_evidence_paths(accepted)
    assert accepted.used_evidence == ["order.status"]
    assert validate_evidence(accepted, facts={"order": {"status": "CLOSE"}}).valid

    rejected = parse_agent_decision(
        {"action": "ANSWER", "final_answer": "已获取", "used_evidence": ["facts.payment.failed"]}
    )
    rejected = canonicalize_evidence_paths(rejected)
    assert validate_evidence(rejected, facts={"order": {"status": "CLOSE"}}).error_code == "MODEL_EVIDENCE_NOT_AVAILABLE"


def test_sensitive_argument_and_unknown_tool_are_never_rewritten() -> None:
    arguments = {"outTradeNo": "202608240001", "userId": "xfg05"}
    normalized = normalize_agent_decision_payload(call_tool(tool_arguments=arguments))
    assert normalized["tool_arguments"] == arguments
    assert normalize_order_facts_arguments(normalized["tool_arguments"]) is None
    assert normalize_agent_decision_payload(call_tool(tool_name="refund_order"))["tool_name"] == "refund_order"
