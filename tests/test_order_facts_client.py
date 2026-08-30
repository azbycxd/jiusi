from __future__ import annotations

import inspect
import json
import logging

import httpx
import pytest

from agent.orchestrator import OrderFactsOrchestrator
from agent.router import route
from agent.state import AgentState, AgentStatus, Intent
from guardrails.auth_context import AuthContext
from tools.fake_market_client import FakeMarketClient
from tools.arguments import OrderFactsArguments
from tools.java_market_client import JavaMarketClient, JavaMarketClientConfig, JoinableTeamFactsTool, OrderFactsTool
from tools.registry import ToolRegistry
from tools.schemas import Evidence, ToolResult


def java_payload(code: str = "0000", data: dict | None = None) -> dict:
    return {
        "code": code,
        "info": "ignored by the Python contract",
        "data": data if data is not None else {
            "order": {"status": "CLOSE"},
            "team": {
                "status": "PROGRESS", "targetCount": 3, "lockCount": 0,
                "completeCount": 0, "validEndTime": "2026-07-30T03:45:37+08:00",
            },
            "activity": {"status": "EFFECTIVE"},
            "references": {"teamId": "18781389", "activityId": 100123},
        },
    }


def market_client(handler) -> JavaMarketClient:
    return JavaMarketClient(
        JavaMarketClientConfig(
            base_url="http://market.test", timeout_seconds=0.1, enable_dev_auth_header=True
        ),
        httpx.Client(transport=httpx.MockTransport(handler)),
    )


def facts_result() -> ToolResult:
    return ToolResult(
        success=True,
        message="事实",
        data={
            "order": {"status": "CLOSE"},
            "team": {"status": "PROGRESS", "target_count": 3, "lock_count": 0, "complete_count": 0, "valid_end_time": None},
            "activity": {"status": "EFFECTIVE"},
            "references": {"team_id": "team-1", "activity_id": 100123},
        },
        evidence=[Evidence(kind="order.status", value="CLOSE", source="fake_market")],
        source="fake_market",
    )


def facts_agent(results: dict[str, ToolResult]) -> tuple[OrderFactsOrchestrator, FakeMarketClient]:
    fake = FakeMarketClient(results)
    return OrderFactsOrchestrator(
        registry=ToolRegistry([OrderFactsTool(fake)]), compatibility_mode=True
    ), fake


def test_java_0000_parses_normalized_facts_and_injects_trusted_dev_header() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/api/v1/agent/order/facts"
        assert json.loads(request.content) == {"outTradeNo": "A-2026.1"}
        assert request.headers["X-Dev-Authenticated-User-Id"] == "trusted-user"
        assert request.headers["Content-Type"] == "application/json"
        return httpx.Response(200, json=java_payload())

    result = market_client(handler).get_order_facts(AuthContext(authenticated_user_id="trusted-user"), " A-2026.1 ")
    assert result.success is True
    assert result.source == "java_market"
    assert result.data["team"]["target_count"] == 3
    assert result.data["references"]["activity_id"] == 100123
    assert {item.kind for item in result.evidence} >= {"order.status", "team.status", "activity.status"}
    assert "reasonCode" not in result.data


def test_tool_input_has_no_user_id_and_default_registry_only_exposes_allowed_facts_tools() -> None:
    assert "user_id" not in str(inspect.signature(OrderFactsTool.run))
    assert "auth" in str(inspect.signature(JavaMarketClient.get_order_facts))
    assert "user_id" not in str(inspect.signature(JoinableTeamFactsTool.run))
    assert OrderFactsOrchestrator(compatibility_mode=True).registry.allowed_names == (
        "get_order_facts", "get_joinable_team_facts", "search_group_buy_rules"
    )


@pytest.mark.parametrize(
    ("java_code", "retryable"),
    [
        ("AUTH_REQUIRED", False),
        ("INVALID_ARGUMENT", False),
        ("ORDER_NOT_FOUND_OR_NOT_AUTHORIZED", False),
        ("INTERNAL_SERVICE_ERROR", True),
    ],
)
def test_known_java_codes_map_to_stable_tool_results(java_code: str, retryable: bool) -> None:
    result = market_client(lambda _request: httpx.Response(200, json=java_payload(java_code))).get_order_facts(
        AuthContext(authenticated_user_id="trusted-user"), "202608240001"
    )
    assert result.success is False
    assert result.error_code == java_code
    assert result.retryable is retryable


def test_transport_and_contract_failures_are_stable_tool_results() -> None:
    timeout = market_client(lambda _request: (_ for _ in ()).throw(httpx.ReadTimeout("timeout"))).get_order_facts(
        AuthContext(authenticated_user_id="trusted-user"), "202608240001"
    )
    connection = market_client(lambda _request: (_ for _ in ()).throw(httpx.ConnectError("down"))).get_order_facts(
        AuthContext(authenticated_user_id="trusted-user"), "202608240001"
    )
    malformed = market_client(lambda _request: httpx.Response(200, content=b"{" )).get_order_facts(
        AuthContext(authenticated_user_id="trusted-user"), "202608240001"
    )
    mismatch = market_client(lambda _request: httpx.Response(200, json=java_payload(data={"order": {}}))).get_order_facts(
        AuthContext(authenticated_user_id="trusted-user"), "202608240001"
    )
    unexpected_status = market_client(lambda _request: httpx.Response(503)).get_order_facts(
        AuthContext(authenticated_user_id="trusted-user"), "202608240001"
    )
    assert (timeout.error_code, timeout.retryable) == ("TOOL_TIMEOUT", True)
    assert (connection.error_code, connection.retryable) == ("TOOL_CONNECTION_ERROR", True)
    assert malformed.error_code == "TOOL_MALFORMED_JSON"
    assert mismatch.error_code == "TOOL_CONTRACT_MISMATCH"
    assert (unexpected_status.error_code, unexpected_status.retryable) == ("HTTP_UNEXPECTED_STATUS", True)


def test_successful_facts_become_one_observation_without_generating_diagnosis() -> None:
    agent, fake = facts_agent({"202608240001": facts_result()})
    state = agent.handle_message("facts-context", "trusted-user", "查询拼团订单 202608240001")
    assert state.status is AgentStatus.FINISHED
    assert state.final_answer == "FACTS_RETRIEVED"
    assert state.intent is Intent.ORDER_FACTS
    assert len(state.observations) == 1
    assert state.observations[0].tool_name == "get_order_facts"
    assert state.observations[0].data["order"]["status"] == "CLOSE"
    assert state.observations[0].evidence[0].kind == "get_order_facts.order.status"
    assert state.team_id == "team-1"
    assert state.activity_id == "100123"
    assert len(state.tool_results) == 1 and state.tool_results[0].success
    assert state.observations[0].evidence and state.diagnosis_code is None
    assert fake.calls[0][0].authenticated_user_id == "trusted-user"


def test_session_resume_and_invalid_slot_do_not_call_facts_tool() -> None:
    agent, fake = facts_agent({"202608240001": facts_result()})
    first = agent.handle_message("facts-resume", "trusted-user", "我的拼团为什么还没成功？")
    second = agent.handle_message("facts-resume", "trusted-user", "202608240001")
    assert first.status is AgentStatus.WAITING_USER
    assert second.status is AgentStatus.FINISHED
    assert second.iteration_count == 2
    assert len(fake.calls) == 1

    invalid_agent, invalid_fake = facts_agent({"202608240001": facts_result()})
    invalid = invalid_agent.handle_message("facts-invalid", "trusted-user", "查询订单 202608240001@")
    assert invalid.status is AgentStatus.WAITING_USER
    assert invalid.tool_call_count == 0
    assert invalid_fake.calls == []


def test_missing_trusted_identity_is_rejected_before_market_client_call() -> None:
    agent, fake = facts_agent({"202608240001": facts_result()})
    state = agent.handle_message("facts-no-auth", "", "查询订单 202608240001")
    assert state.status is AgentStatus.FAILED
    assert state.tool_results[0].error_code == "AUTH_REQUIRED"
    assert state.tool_results[0].retryable is False
    assert fake.calls == []


def test_internal_service_error_retries_with_finite_read_only_policy() -> None:
    failure = ToolResult.infrastructure_failure("INTERNAL_SERVICE_ERROR", "", retryable=True, source="fake_market")
    agent, fake = facts_agent({"202608240005": failure})
    state = agent.handle_message("facts-retry", "trusted-user", "查询订单 202608240005")
    assert state.status is AgentStatus.HANDOFF
    assert state.tool_call_count == 2
    assert state.retry_count == 1
    assert len(fake.calls) == 2


def test_facts_trace_records_tool_name_error_and_retry_count(caplog) -> None:
    caplog.set_level(logging.INFO, logger="group_buy_agent.trace")
    failure = ToolResult.infrastructure_failure("INTERNAL_SERVICE_ERROR", "", retryable=True, source="fake_market")
    agent, _ = facts_agent({"202608240005": failure})
    agent.handle_message("facts-trace", "trusted-user", "查询拼团订单 202608240005")
    events = [json.loads(record.message) for record in caplog.records]
    tool_events = [event for event in events if event["stage"] == "TOOL_RESULT" and event["tool_name"] == "get_order_facts"]
    assert [event["retry_count"] for event in tool_events] == [0, 1]
    assert tool_events[-1]["tool_success"] is False
    assert tool_events[-1]["error_code"] == "INTERNAL_SERVICE_ERROR"


def test_router_and_tool_remain_state_side_effect_free() -> None:
    state = AgentState(session_id="pure", authenticated_user_id="trusted-user")
    before_router = state.model_dump()
    assert route("查询订单 202608240001", state.intent).intent is Intent.ORDER_FACTS
    assert state.model_dump() == before_router
    before_tool = state.model_dump()
    assert OrderFactsTool(FakeMarketClient({"202608240001": facts_result()})).run(
        state, OrderFactsArguments(outTradeNo="202608240001")
    ).success
    assert state.model_dump() == before_tool
