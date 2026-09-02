from __future__ import annotations

import json
import logging

import httpx
import pytest

from agent.orchestrator import OrderFactsOrchestrator
from agent.state import AgentStatus, Observation
from decision.real_llm import SYSTEM_PROMPT, RealLLMConfig, RealLLMDecisionModel
from decision.schemas import DecisionContext
from decision.stage import DecisionStage
from tools.fake_market_client import FakeMarketClient
from tools.java_market_client import JoinableTeamFactsTool, OrderFactsTool
from tools.registry import ToolRegistry
from tools.schemas import Evidence


def context(*, observations: list[Observation] | None = None) -> DecisionContext:
    return DecisionContext(
        user_query="为什么订单还没有拼团成功？",
        observations=observations or [],
        available_tools=ToolRegistry([OrderFactsTool(FakeMarketClient({}))]).available_tools,
    )


def multi_tool_context() -> DecisionContext:
    return DecisionContext(
        user_query="这个活动还能加入哪些团？",
        observations=[],
        available_tools=ToolRegistry([
            OrderFactsTool(FakeMarketClient({})), JoinableTeamFactsTool(object())
        ]).available_tools,
    )


def order_observation() -> Observation:
    return Observation(
        tool_name="get_order_facts",
        data={"order": {"status": "CLOSE"}},
        evidence=[Evidence(kind="get_order_facts.order.status", value="CLOSE", source="test")],
    )


def provider_payload(content: object, *, usage: dict | None = None) -> dict:
    return {
        "model": "provider-model",
        "choices": [{"message": {"content": content}}],
        "usage": usage if usage is not None else {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
    }


def model_with(handler) -> RealLLMDecisionModel:
    return RealLLMDecisionModel(
        RealLLMConfig(model="configured-model", api_key="llm-secret-value", base_url="http://llm.test/v1", timeout_seconds=0.1),
        httpx.Client(transport=httpx.MockTransport(handler)),
    )


def test_real_adapter_converts_legal_call_tool_response_and_uses_safe_payload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer llm-secret-value"
        body = json.loads(request.content)
        serialized = json.dumps(body, ensure_ascii=False)
        assert "llm-secret-value" not in serialized
        assert "trusted-user" not in serialized
        visible = json.loads(body["messages"][1]["content"])
        assert set(visible) == {"user_query", "diagnosis_progress", "available_tools", "observations", "evidence"}
        assert visible["diagnosis_progress"] is None
        assert visible["available_tools"][0]["parameters_schema"]["required"] == ["outTradeNo"]
        return httpx.Response(200, json=provider_payload(json.dumps({
            "action": "CALL_TOOL", "tool_name": "get_order_facts",
            "tool_arguments": {"outTradeNo": "202608240001"},
        })))

    result = DecisionStage(model_with(handler), context().available_tools).decide(context())
    assert result.decision is not None
    assert result.decision.tool_name == "get_order_facts"
    assert result.telemetry is not None and result.telemetry.total_tokens == 18


def test_prompt_and_provider_payload_follow_dynamic_tool_contracts_without_fixed_workflow() -> None:
    assert "activityId" not in SYSTEM_PROMPT
    assert "outTradeNo" not in SYSTEM_PROMPT
    assert "parameters_schema" in SYSTEM_PROMPT
    assert "validated observations/evidence" in SYSTEM_PROMPT
    assert "only paths that exist in DecisionContext.evidence" in SYSTEM_PROMPT
    assert "evidence entry's kind field" in SYSTEM_PROMPT
    assert "evidence[0]" in SYSTEM_PROMPT
    assert "available_tools metadata" in SYSTEM_PROMPT
    assert "must set used_evidence to []" in SYSTEM_PROMPT
    assert "you can do" not in SYSTEM_PROMPT.lower()
    assert "one verified condition is not automatically a complete\ndiagnosis" in SYSTEM_PROMPT
    assert "do not assume a fixed tool order or call every tool" in SYSTEM_PROMPT
    assert "Do not use a rule lookup unless a rule explanation is actually needed" in SYSTEM_PROMPT
    assert "REQUEST_INPUT" in SYSTEM_PROMPT
    assert "instead of exploring an unrelated available capability" in SYSTEM_PROMPT
    assert "takes precedence over REQUEST_INPUT" in SYSTEM_PROMPT
    for forbidden in ("userId", "authenticated_user_id", "token", "headers", "auth context", "SQL", "base_url"):
        assert forbidden in SYSTEM_PROMPT
    assert "get_order_facts -> get_joinable_team_facts" not in SYSTEM_PROMPT

    context_with_two_tools = multi_tool_context()
    payload = model_with(lambda _: httpx.Response(500)).build_payload(context_with_two_tools)
    visible = json.loads(payload["messages"][1]["content"])
    schemas = {tool["name"]: tool["parameters_schema"] for tool in visible["available_tools"]}
    assert schemas["get_order_facts"]["required"] == ["outTradeNo"]
    assert schemas["get_joinable_team_facts"]["required"] == ["activityId"]


def test_real_adapter_accepts_legal_joinable_tool_decision_from_dynamic_metadata() -> None:
    response = json.dumps({
        "action": "CALL_TOOL", "tool_name": "get_joinable_team_facts", "tool_arguments": {"activityId": 100123},
    })
    context_with_two_tools = multi_tool_context()
    result = DecisionStage(
        model_with(lambda _: httpx.Response(200, json=provider_payload(response))),
        context_with_two_tools.available_tools,
    ).decide(context_with_two_tools)
    assert result.decision is not None
    assert result.decision.tool_name == "get_joinable_team_facts"
    assert result.decision.tool_arguments == {"activityId": 100123}


def test_real_adapter_answer_still_passes_evidence_validation() -> None:
    answer = json.dumps({
        "action": "ANSWER", "final_answer": "订单状态已获取。", "used_evidence": ["order.status"],
    })
    facts_context = context(observations=[order_observation()])
    result = DecisionStage(
        model_with(lambda _: httpx.Response(200, json=provider_payload(answer))), facts_context.available_tools
    ).decide(facts_context)
    assert result.decision is not None and result.decision.action.value == "ANSWER"


def test_real_adapter_capability_answer_uses_no_business_evidence() -> None:
    answer = json.dumps({
        "action": "ANSWER",
        "final_answer": "我可以查询订单拼团事实和当前可加入团队。",
        "used_evidence": [],
    })
    result = DecisionStage(
        model_with(lambda _: httpx.Response(200, json=provider_payload(answer))), context().available_tools
    ).decide(context())
    assert result.decision is not None
    assert result.decision.action.value == "ANSWER"
    assert result.decision.used_evidence == []


@pytest.mark.parametrize(
    "metadata_path",
    [
        "available_tools.get_order_facts.description",
        "available_tools.get_joinable_team_facts.description",
    ],
)
def test_real_adapter_rejects_capability_metadata_as_business_evidence(metadata_path: str) -> None:
    answer = json.dumps({
        "action": "ANSWER",
        "final_answer": "我可以查询当前能力。",
        "used_evidence": [metadata_path],
    })
    result = DecisionStage(
        model_with(lambda _: httpx.Response(200, json=provider_payload(answer))), multi_tool_context().available_tools
    ).decide(multi_tool_context())
    assert result.decision is None
    assert result.error_code == "MODEL_EVIDENCE_NOT_AVAILABLE"


def test_real_adapter_handoff_is_a_valid_decision() -> None:
    handoff = json.dumps({
        "action": "HANDOFF", "missing_information": ["refund policy"],
    })
    result = DecisionStage(model_with(lambda _: httpx.Response(200, json=provider_payload(handoff))), context().available_tools).decide(context())
    assert result.decision is not None and result.decision.action.value == "HANDOFF"


@pytest.mark.parametrize(
    "response_body, error_code",
    [
        (provider_payload("not json"), "MODEL_INVALID_RESPONSE"),
        (provider_payload(""), "MODEL_INVALID_RESPONSE"),
        (provider_payload(json.dumps({"action": "ANSWER"})), "MODEL_CONTRACT_MISMATCH"),
    ],
)
def test_real_adapter_malformed_or_contract_response_is_model_failure(response_body: dict, error_code: str) -> None:
    result = DecisionStage(model_with(lambda _: httpx.Response(200, json=response_body)), context().available_tools).decide(context())
    assert result.decision is None and result.error_code == error_code


@pytest.mark.parametrize(
    "failure, error_code",
    [
        (httpx.ReadTimeout("timeout"), "MODEL_TIMEOUT"),
        (httpx.ConnectError("down"), "MODEL_CONNECTION_ERROR"),
    ],
)
def test_model_timeout_or_connection_uses_bounded_model_retry(failure: Exception, error_code: str) -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise failure

    agent = OrderFactsOrchestrator(
        registry=ToolRegistry([OrderFactsTool(FakeMarketClient({}))]), decision_model=model_with(handler)
    )
    state = agent.handle_message("real-model-retry", "trusted-user", "你能做什么？")
    assert state.status is AgentStatus.HANDOFF
    assert state.model_call_count == 2 and state.model_retry_count == 1
    assert state.tool_call_count == 0 and calls == 2
    assert state.context.model_decision is None
    assert error_code in {"MODEL_TIMEOUT", "MODEL_CONNECTION_ERROR"}


def test_rate_limit_has_stable_model_error() -> None:
    result = DecisionStage(model_with(lambda _: httpx.Response(429, json={})), context().available_tools).decide(context())
    assert result.error_code == "MODEL_RATE_LIMITED" and result.retryable is True


def test_http_failure_and_invalid_envelope_have_stable_model_errors() -> None:
    unavailable = DecisionStage(
        model_with(lambda _: httpx.Response(503, json={})), context().available_tools
    ).decide(context())
    invalid_json = DecisionStage(
        model_with(lambda _: httpx.Response(200, content=b"{")), context().available_tools
    ).decide(context())
    assert unavailable.error_code == "MODEL_HTTP_ERROR" and unavailable.retryable is True
    assert invalid_json.error_code == "MODEL_INVALID_RESPONSE" and invalid_json.retryable is False


def test_trace_uses_only_safe_model_telemetry(caplog) -> None:
    caplog.set_level(logging.INFO, logger="group_buy_agent.trace")
    answer = json.dumps({
        "action": "ANSWER", "final_answer": "我可以查询订单事实。", "used_evidence": [],
    })
    agent = OrderFactsOrchestrator(
        registry=ToolRegistry([OrderFactsTool(FakeMarketClient({}))]),
        decision_model=model_with(lambda _: httpx.Response(200, json=provider_payload(answer))),
    )
    state = agent.handle_message("real-model-trace", "trusted-user", "你能帮我做什么？")
    assert state.status is AgentStatus.FINISHED
    events = [json.loads(record.message) for record in caplog.records]
    model_event = next(event for event in events if event["stage"] == "MODEL_DECISION")
    assert model_event["model"] == "provider-model" and model_event["total_tokens"] == 18
    assert all("llm-secret-value" not in record.message and "trusted-user" not in record.message for record in caplog.records)


def test_real_model_config_requires_all_values() -> None:
    with pytest.raises(ValueError, match="LLM_MODEL"):
        RealLLMDecisionModel(RealLLMConfig(model="x", api_key=None, base_url="http://llm.test"))


def test_invalid_timeout_is_an_explicit_configuration_error(monkeypatch) -> None:
    monkeypatch.setenv("LLM_TIMEOUT", "not-a-number")
    with pytest.raises(ValueError, match="LLM_TIMEOUT"):
        RealLLMConfig.from_environment()
