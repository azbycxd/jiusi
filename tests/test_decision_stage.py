from __future__ import annotations

import json
import logging

import pytest
from pydantic import BaseModel

import agent.orchestrator as orchestrator_module
from agent.orchestrator import OrderFactsOrchestrator
from agent.state import AgentStatus, Intent, Observation
from decision.model import FakeDecisionModel
from decision.schemas import DecisionContext, parse_agent_decision
from tools.fake_market_client import FakeMarketClient
from tools.base import RepeatPolicy
from tools.java_market_client import OrderFactsTool
from tools.registry import ToolRegistry
from tools.schemas import Evidence, ToolResult


def facts_result() -> ToolResult:
    return ToolResult(
        success=True,
        message="facts",
        data={
            "order": {"status": "CLOSE"},
            "team": {"status": "PROGRESS", "target_count": 3, "lock_count": 0, "complete_count": 0, "valid_end_time": None},
            "activity": {"status": "EFFECTIVE"},
            "references": {"team_id": "team-1", "activity_id": 100123},
        },
        evidence=[
            Evidence(kind="order.status", value="CLOSE", source="fake_market"),
            Evidence(kind="team.status", value="PROGRESS", source="fake_market"),
            Evidence(kind="team.target_count", value="3", source="fake_market"),
            Evidence(kind="team.complete_count", value="0", source="fake_market"),
            Evidence(kind="activity.status", value="EFFECTIVE", source="fake_market"),
        ],
        source="fake_market",
    )


def call_facts(arguments: dict | None = None) -> dict:
    return {
        "action": "CALL_TOOL",
        "tool_name": "get_order_facts",
        "tool_arguments": arguments or {"outTradeNo": "202608240001"},
    }


def answer(evidence: list[str] | None = None) -> dict:
    return {
        "action": "ANSWER",
        "final_answer": "基于当前已获取的事实给出可验证答复。",
        "used_evidence": evidence if evidence is not None else [
            "get_order_facts.order.status",
            "get_order_facts.team.status",
            "get_order_facts.team.complete_count",
            "get_order_facts.team.target_count",
        ],
    }


def decision_agent(responses: list[object], result: ToolResult | None = None):
    market = FakeMarketClient({"202608240001": result or facts_result()})
    model = FakeDecisionModel(responses)
    agent = OrderFactsOrchestrator(
        registry=ToolRegistry([OrderFactsTool(market)]),
        decision_model=model,
    )
    return agent, model, market


class SequentialMarketClient:
    """Test double for separating physical Tool retries from model actions."""

    def __init__(self, results: list[ToolResult]) -> None:
        self.results = list(results)
        self.calls: list[tuple[object, str]] = []

    def get_order_facts(self, auth: object, out_trade_no: str) -> ToolResult:
        self.calls.append((auth, out_trade_no))
        return self.results.pop(0)


def decision_agent_with_tool(responses: list[object], tool: OrderFactsTool):
    model = FakeDecisionModel(responses)
    agent = OrderFactsOrchestrator(registry=ToolRegistry([tool]), decision_model=model)
    return agent, model


def test_multi_round_call_tool_observation_answer_and_trace(caplog) -> None:
    caplog.set_level(logging.INFO, logger="group_buy_agent.trace")
    agent, model, market = decision_agent([call_facts(), answer()])
    state = agent.handle_message("loop-happy", "trusted-user", "为什么订单还未完成？订单号 202608240001")
    assert state.status is AgentStatus.FINISHED
    assert state.final_answer == answer()["final_answer"]
    assert state.tool_call_count == 1 and state.model_call_count == 2
    assert len(market.calls) == 1
    assert len(state.observations) == 1
    assert state.observations[0].tool_name == "get_order_facts"
    assert state.observations[0].data["team"]["complete_count"] == 0
    assert len(model.contexts) == 2
    assert model.contexts[0].observations == []
    assert model.contexts[1].observations[0].data["team"]["complete_count"] == 0
    assert model.contexts[1].evidence
    assert "authenticated_user_id" not in model.contexts[0].model_dump()
    assert model.contexts[0].available_tools[0].parameters_schema["required"] == ["outTradeNo"]
    events = [json.loads(record.message) for record in caplog.records]
    stages = [event["stage"] for event in events]
    assert "MODEL_DECISION" in stages and "TOOL_CALL" in stages and "TOOL_RESULT" in stages
    assert any(event["stage"] == "MODEL_DECISION" and event["action"] == "ANSWER" for event in events)


def test_first_decision_answer_needs_no_tool_or_facts() -> None:
    agent, model, market = decision_agent([answer(evidence=[])])
    state = agent.handle_message("loop-answer", "trusted-user", "你能做什么？")
    assert state.status is AgentStatus.FINISHED
    assert state.tool_call_count == 0 and market.calls == []
    assert state.observations == []
    assert model.contexts[0].observations == []


def test_dynamic_path_does_not_invoke_legacy_router_and_traces_input_prepared(monkeypatch, caplog) -> None:
    caplog.set_level(logging.INFO, logger="group_buy_agent.trace")

    def legacy_router_must_not_run(*_args, **_kwargs):
        raise AssertionError("dynamic Agent Path must not invoke the legacy router")

    monkeypatch.setattr(orchestrator_module, "route", legacy_router_must_not_run)
    agent, model, market = decision_agent([answer(evidence=[])])
    state = agent.handle_message("loop-no-router", "trusted-user", "   我能获得什么帮助？   ")

    assert state.status is AgentStatus.FINISHED
    assert state.user_query == "我能获得什么帮助？"
    assert state.intent is Intent.UNKNOWN and state.out_trade_no is None
    assert len(model.contexts) == 1 and market.calls == []
    stages = [json.loads(record.message)["stage"] for record in caplog.records]
    assert "INPUT_PREPARED" in stages
    assert "ROUTED" not in stages


def test_dynamic_no_keyword_question_reaches_llm_and_tool_arguments_not_legacy_slots() -> None:
    agent, model, market = decision_agent([call_facts(), answer()])
    state = agent.handle_message("loop-no-keywords", "trusted-user", "我这个团怎么还没凑齐？")

    assert state.status is AgentStatus.FINISHED
    assert len(model.contexts) == 2 and len(market.calls) == 1
    assert state.intent is Intent.UNKNOWN and state.out_trade_no is None
    assert market.calls[0][1] == "202608240001"


def test_refund_question_reaches_decision_stage_before_handoff() -> None:
    agent, model, market = decision_agent([
        {"action": "HANDOFF", "missing_information": ["refund facts"]}
    ])
    state = agent.handle_message("loop-refund-decision", "trusted-user", "我的退款什么时候到账？")

    assert state.status is AgentStatus.HANDOFF
    assert state.model_call_count == 1 and len(model.contexts) == 1
    assert state.tool_call_count == 0 and market.calls == []


def test_unallowed_refund_tool_is_rejected_without_execution() -> None:
    response = call_facts()
    response["tool_name"] = "refund_order"
    agent, _, market = decision_agent([response])
    state = agent.handle_message("loop-refund", "trusted-user", "退款")
    assert state.status is AgentStatus.HANDOFF
    assert state.tool_call_count == 0 and market.calls == []


@pytest.mark.parametrize(
    "forbidden_key", ["userId", "authenticated_user_id", "header", "base_url", "teamId", "activityId", "sql"]
)
def test_extra_or_privileged_tool_arguments_are_rejected(forbidden_key: str) -> None:
    agent, _, market = decision_agent([call_facts({"outTradeNo": "202608240001", forbidden_key: "forbidden"})])
    state = agent.handle_message("loop-user-id", "trusted-user", "查询")
    assert state.status is AgentStatus.HANDOFF
    assert state.tool_call_count == 0 and market.calls == []


def test_tool_identity_comes_from_state_not_model_arguments() -> None:
    agent, _, market = decision_agent([call_facts(), answer()])
    agent.handle_message("loop-auth", "trusted-user", "查询")
    assert market.calls[0][0].authenticated_user_id == "trusted-user"


def test_dynamic_tool_arguments_do_not_need_or_overwrite_state_slot() -> None:
    agent, _, market = decision_agent([call_facts(), answer()])
    state = agent.handle_message("loop-argument-state", "trusted-user", "请查询订单")
    assert state.status is AgentStatus.FINISHED
    assert state.out_trade_no is None
    assert market.calls[0][1] == "202608240001"


def test_answer_with_fabricated_evidence_is_rejected(caplog) -> None:
    caplog.set_level(logging.INFO, logger="group_buy_agent.trace")
    agent, _, market = decision_agent([call_facts(), answer(["payment.failed"])])
    state = agent.handle_message("loop-evidence", "trusted-user", "查询")
    assert state.status is AgentStatus.HANDOFF
    assert state.tool_call_count == 1 and len(market.calls) == 1
    events = [json.loads(record.message) for record in caplog.records]
    assert any(event["stage"] == "MODEL_VALIDATION_ERROR" and event["error_code"] == "MODEL_EVIDENCE_NOT_AVAILABLE" for event in events)


def test_third_identical_repeat_is_blocked_before_execution(caplog) -> None:
    caplog.set_level(logging.INFO, logger="group_buy_agent.trace")
    agent, _, market = decision_agent([call_facts(), call_facts(), call_facts()])
    state = agent.handle_message("loop-duplicate", "trusted-user", "查询")
    assert state.status is AgentStatus.HANDOFF
    assert state.tool_call_count == 2 and len(market.calls) == 2
    assert len(state.context.tool_call_history) == 2
    events = [json.loads(record.message) for record in caplog.records]
    assert any(
        event["stage"] == "TOOL_REPEAT_BLOCKED"
        and event["tool_name"] == "get_order_facts"
        and event["same_call_count"] == 2
        and event["allowed_same_call_count"] == 2
        for event in events
    )


def test_tool_timeout_keeps_tool_retry_counters_separate_from_model() -> None:
    timeout = ToolResult.infrastructure_failure("TOOL_TIMEOUT", "", retryable=True, source="fake_market")
    market = SequentialMarketClient([timeout, facts_result()])
    agent, model = decision_agent_with_tool([call_facts(), answer()], OrderFactsTool(market))
    state = agent.handle_message("loop-timeout", "trusted-user", "查询")
    assert state.status is AgentStatus.FINISHED
    assert state.tool_call_count == 2 and state.retry_count == 1
    assert state.model_call_count == 2 and state.model_retry_count == 0
    assert len(market.calls) == 2
    assert len(state.observations) == 1
    assert len(state.context.tool_call_history) == 1
    assert len(model.contexts) == 2


def test_second_identical_repeat_is_permitted_and_produces_two_observations() -> None:
    market = SequentialMarketClient([facts_result(), facts_result()])
    agent, model = decision_agent_with_tool(
        [call_facts(), call_facts(), answer()], OrderFactsTool(market)
    )
    state = agent.handle_message("loop-repeat-allowed", "trusted-user", "查询")

    assert state.status is AgentStatus.FINISHED
    assert state.tool_call_count == 2 and len(market.calls) == 2
    assert len(state.context.tool_call_history) == 2
    assert len(state.observations) == 2
    assert len(model.contexts[2].observations) == 2


def test_non_repeatable_tool_blocks_second_identical_model_action() -> None:
    market = SequentialMarketClient([facts_result(), facts_result()])
    tool = OrderFactsTool(market)
    tool.repeat_policy = RepeatPolicy(repeatable=False, max_same_call=2)
    agent, _ = decision_agent_with_tool([call_facts(), call_facts()], tool)
    state = agent.handle_message("loop-non-repeatable", "trusted-user", "查询")

    assert state.status is AgentStatus.HANDOFF
    assert state.tool_call_count == 1 and len(market.calls) == 1
    assert len(state.context.tool_call_history) == 1


def test_same_tool_with_different_validated_arguments_is_not_a_repeat() -> None:
    market = SequentialMarketClient([facts_result(), facts_result()])
    agent, _ = decision_agent_with_tool(
        [call_facts({"outTradeNo": "202608240001"}), call_facts({"outTradeNo": "202608240002"}), answer()],
        OrderFactsTool(market),
    )
    state = agent.handle_message("loop-different-arguments", "trusted-user", "查询")

    assert state.status is AgentStatus.FINISHED
    assert state.tool_call_count == 2
    assert [call[1] for call in market.calls] == ["202608240001", "202608240002"]
    assert len(set(state.context.tool_call_history)) == 2


class OrderedArguments(BaseModel):
    first: str
    second: int


def test_tool_call_signature_is_canonical_after_validation_not_raw_key_order() -> None:
    first = OrderedArguments.model_validate({"second": 2, "first": "one"})
    second = OrderedArguments.model_validate({"first": "one", "second": 2})
    assert OrderFactsOrchestrator._tool_call_signature("test_tool", first) == (
        OrderFactsOrchestrator._tool_call_signature("test_tool", second)
    )


def test_multiple_repeat_observations_do_not_accept_fabricated_evidence() -> None:
    market = SequentialMarketClient([facts_result(), facts_result()])
    agent, model = decision_agent_with_tool(
        [call_facts(), call_facts(), answer(["get_order_facts.payment.status"])],
        OrderFactsTool(market),
    )
    state = agent.handle_message("loop-repeat-evidence", "trusted-user", "查询")

    assert state.status is AgentStatus.HANDOFF
    assert state.tool_call_count == 2 and len(state.observations) == 2
    assert len(model.contexts[2].observations) == 2


def test_decision_context_aggregates_multiple_observations() -> None:
    first = Observation(
        tool_name="get_order_facts",
        data={"order": {"status": "CLOSE"}},
        evidence=[Evidence(kind="get_order_facts.order.status", value="CLOSE", source="test")],
    )
    second = Observation(
        tool_name="future_tool",
        data={"policy": {"status": "EFFECTIVE"}},
        evidence=[Evidence(kind="future_tool.policy.status", value="EFFECTIVE", source="test")],
    )
    agent, model, _ = decision_agent([answer(evidence=[])])
    context = agent._decision_stage.build_context(  # type: ignore[union-attr]
        user_query="测试多个 Observation", observations=[first, second]
    )
    assert [item.tool_name for item in context.observations] == ["get_order_facts", "future_tool"]
    assert [item["kind"] for item in context.evidence] == [
        "get_order_facts.order.status", "future_tool.policy.status"
    ]
    assert model.contexts == []


def test_malformed_model_schema_retries_then_answers() -> None:
    agent, _, market = decision_agent([{"action": "ANSWER"}, answer(evidence=[])])
    state = agent.handle_message("loop-model-retry", "trusted-user", "能力说明")
    assert state.status is AgentStatus.FINISHED
    assert state.model_call_count == 2 and state.model_retry_count == 1
    assert state.tool_call_count == 0 and market.calls == []


def test_malformed_model_schema_handoffs_at_max_retries_without_loop() -> None:
    malformed = {"action": "ANSWER"}
    agent, _, market = decision_agent([malformed, malformed])
    state = agent.handle_message("loop-model-max", "trusted-user", "能力说明")
    assert state.status is AgentStatus.HANDOFF
    assert state.model_call_count == 2 and state.model_retry_count == 1
    assert state.tool_call_count == 0 and market.calls == []


def test_handoff_action_does_not_execute_tool() -> None:
    response = {
        "action": "HANDOFF",
        "missing_information": ["refund status"],
    }
    agent, _, market = decision_agent([response])
    state = agent.handle_message("loop-handoff", "trusted-user", "退款")
    assert state.status is AgentStatus.HANDOFF
    assert state.tool_call_count == 0 and market.calls == []
    assert "refund status" not in (state.final_answer or "")


def test_no_model_uses_explicit_facts_compatibility_path(caplog) -> None:
    caplog.set_level(logging.INFO, logger="group_buy_agent.trace")
    market = FakeMarketClient({"202608240001": facts_result()})
    agent = OrderFactsOrchestrator(
        registry=ToolRegistry([OrderFactsTool(market)]), compatibility_mode=True
    )
    state = agent.handle_message("loop-no-model", "trusted-user", "查询订单 202608240001")
    assert state.status is AgentStatus.FINISHED
    assert state.final_answer == "FACTS_RETRIEVED"
    assert state.model_call_count == 0 and state.tool_call_count == 1
    events = [json.loads(record.message) for record in caplog.records]
    assert any(event["stage"] == "ROUTED" and event["action"] == "legacy_route" for event in events)


def test_no_model_requires_explicit_compatibility_mode() -> None:
    with pytest.raises(ValueError, match="DecisionModel"):
        OrderFactsOrchestrator(registry=ToolRegistry([OrderFactsTool(FakeMarketClient({}))]))


def test_terminal_session_starts_a_new_task_but_waiting_session_still_resumes() -> None:
    agent, _, _ = decision_agent([answer(evidence=[]), answer(evidence=[])])
    first = agent.handle_message("loop-terminal", "trusted-user", "你能做什么？")
    second = agent.handle_message("loop-terminal", "trusted-user", "你能做什么？")
    assert first.status is AgentStatus.FINISHED and second.status is AgentStatus.FINISHED
    assert second.iteration_count == 1
    assert second.tool_call_count == 0 and second.context.tool_call_history == []


def test_agent_decision_and_context_are_strict() -> None:
    try:
        parse_agent_decision({"action": "ANSWER", "final_answer": "x", "tool_name": "get_order_facts"})
    except Exception:
        pass
    else:
        raise AssertionError("ANSWER with tool request must be rejected")
    try:
        DecisionContext.model_validate({"user_query": "q", "observations": [], "available_tools": [], "authenticated_user_id": "forbidden"})
    except Exception:
        pass
    else:
        raise AssertionError("model context must reject identity fields")
