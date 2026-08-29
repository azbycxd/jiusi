from __future__ import annotations

import inspect
import json

import httpx
import pytest
from pydantic import ValidationError

from agent.orchestrator import OrderFactsOrchestrator
from agent.state import AgentState, AgentStatus, Observation
from decision.model import FakeDecisionModel
from guardrails.auth_context import AuthContext
from tools.arguments import JoinableTeamFactsArguments
from tools.fake_market_client import FakeMarketClient
from tools.java_market_client import JavaMarketClient, JavaMarketClientConfig, JoinableTeamFactsTool, OrderFactsTool
from tools.registry import ToolRegistry
from tools.schemas import Evidence, ToolResult


def joinable_payload(code: str = "0000", data: dict | None = None) -> dict:
    return {
        "code": code,
        "info": "ignored by the Python contract",
        "data": data if data is not None else {
            "activityId": 100123,
            "candidateTeams": [
                {
                    "teamId": "18781389",
                    "targetCount": 3,
                    "completeCount": 1,
                    "lockCount": 1,
                    "validEndTime": "2026-07-30T03:45:37+08:00",
                }
            ],
            "statistics": {
                "allTeamCount": 1,
                "allTeamCompleteCount": 1,
                "allTeamUserCount": 3,
            },
        },
    }


def market_client(handler) -> JavaMarketClient:
    return JavaMarketClient(
        JavaMarketClientConfig(base_url="http://market.test", timeout_seconds=0.1, enable_dev_auth_header=True),
        httpx.Client(transport=httpx.MockTransport(handler)),
    )


def joinable_result() -> ToolResult:
    return ToolResult(
        success=True,
        message="joinable facts",
        data={
            "activity_id": 100123,
            "candidate_teams": [{
                "team_id": "18781389", "target_count": 3, "complete_count": 1,
                "lock_count": 1, "valid_end_time": "2026-07-30T03:45:37+08:00",
            }],
            "statistics": {"all_team_count": 1, "all_team_complete_count": 1, "all_team_user_count": 3},
        },
        evidence=[
            Evidence(kind="activity_id", value="100123", source="fake_market"),
            Evidence(kind="statistics.all_team_count", value="1", source="fake_market"),
            Evidence(kind="statistics.all_team_complete_count", value="1", source="fake_market"),
            Evidence(kind="statistics.all_team_user_count", value="3", source="fake_market"),
            Evidence(kind="candidate_teams.0.team_id", value="18781389", source="fake_market"),
        ],
        source="fake_market",
    )


def empty_joinable_result() -> ToolResult:
    return ToolResult(
        success=True,
        message="empty joinable facts",
        data={
            "activity_id": 100123,
            "candidate_teams": [],
            "statistics": {"all_team_count": 1, "all_team_complete_count": 1, "all_team_user_count": 3},
        },
        evidence=[
            Evidence(kind="activity_id", value="100123", source="fake_market"),
            Evidence(kind="candidate_teams", value="[]", source="fake_market"),
            Evidence(kind="statistics.all_team_count", value="1", source="fake_market"),
        ],
        source="fake_market",
    )


def order_result_for_cross_tool_evidence() -> ToolResult:
    return ToolResult(
        success=True,
        message="order facts",
        data={
            "order": {"status": "CLOSE"},
            "team": {"status": "PROGRESS", "target_count": 3, "lock_count": 0, "complete_count": 0},
            "activity": {"status": "EFFECTIVE"},
            "references": {"team_id": "team-1", "activity_id": 100123},
        },
        evidence=[
            Evidence(kind="order.status", value="CLOSE", source="fake_market"),
            Evidence(kind="references.activity_id", value="100123", source="fake_market"),
        ],
        source="fake_market",
    )


class RecordingJoinableClient:
    def __init__(self, result: ToolResult) -> None:
        self.result = result
        self.calls: list[tuple[object, int]] = []

    def get_joinable_team_facts(self, auth: object, activity_id: int) -> ToolResult:
        self.calls.append((auth, activity_id))
        return self.result


@pytest.mark.parametrize(
    "arguments",
    [
        {}, {"activityId": 0}, {"activityId": -1}, {"activityId": True}, {"activityId": "100123"},
        {"activityId": 100123, "userId": "xfg05"},
        {"activityId": 100123, "authenticatedUserId": "xfg05"},
        {"activityId": 100123, "outTradeNo": "644398015396"},
        {"activityId": 100123, "token": "forbidden"}, {"activityId": 100123, "header": "forbidden"},
        {"activityId": 100123, "url": "forbidden"}, {"activityId": 100123, "sql": "forbidden"},
        {"activityId": 100123, "limit": 1}, {"activityId": 100123, "topK": 1},
    ],
)
def test_joinable_arguments_are_strict_and_reject_privileged_or_query_shaping_fields(arguments: object) -> None:
    with pytest.raises(ValidationError):
        JoinableTeamFactsArguments.model_validate(arguments)


def test_java_success_normalizes_joinable_facts_injects_trusted_identity_and_emits_candidate_evidence() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/api/v1/agent/team/joinable-facts"
        assert json.loads(request.content) == {"activityId": 100123}
        assert request.headers["X-Dev-Authenticated-User-Id"] == "trusted-user"
        return httpx.Response(200, json=joinable_payload())

    result = market_client(handler).get_joinable_team_facts(
        auth=AuthContext(authenticated_user_id="trusted-user"), activity_id=100123
    )

    assert result.success is True and result.source == "java_market"
    assert result.data["activity_id"] == 100123
    assert result.data["candidate_teams"][0]["team_id"] == "18781389"
    assert result.data["statistics"] == {"all_team_count": 1, "all_team_complete_count": 1, "all_team_user_count": 3}
    assert {item.kind for item in result.evidence} >= {
        "activity_id", "statistics.all_team_count", "statistics.all_team_complete_count",
        "statistics.all_team_user_count", "candidate_teams.0.team_id",
    }
    observation = Observation.from_successful_tool_result("get_joinable_team_facts", result)
    assert observation.evidence[-1].kind.startswith("get_joinable_team_facts.candidate_teams.0.")


def test_empty_candidate_teams_are_successful_facts_and_produce_a_valid_observation() -> None:
    data = joinable_payload()["data"]
    data["candidateTeams"] = []
    result = market_client(lambda _: httpx.Response(200, json=joinable_payload(data=data))).get_joinable_team_facts(
        AuthContext(authenticated_user_id="trusted-user"), 100123
    )

    assert result.success is True
    assert result.data["candidate_teams"] == []
    assert any(item.kind == "candidate_teams" and item.value == "[]" for item in result.evidence)
    assert all(item.kind != "candidate_teams.0.team_id" for item in result.evidence)
    observation = Observation.from_successful_tool_result("get_joinable_team_facts", result)
    assert observation.data["candidate_teams"] == []
    assert any(item.kind == "get_joinable_team_facts.candidate_teams" for item in observation.evidence)


def test_joinable_client_keeps_contract_and_transport_failures_stable() -> None:
    auth = AuthContext(authenticated_user_id="trusted-user")
    malformed = market_client(lambda _: httpx.Response(200, content=b"{")).get_joinable_team_facts(auth, 100123)
    wrong_schema = market_client(lambda _: httpx.Response(200, json=joinable_payload(data={"activityId": 100123}))).get_joinable_team_facts(auth, 100123)
    extra_field = market_client(lambda _: httpx.Response(200, json=joinable_payload(data={**joinable_payload()["data"], "phone": "forbidden"}))).get_joinable_team_facts(auth, 100123)
    connection = market_client(lambda _: (_ for _ in ()).throw(httpx.ConnectError("down"))).get_joinable_team_facts(auth, 100123)
    java_error = market_client(lambda _: httpx.Response(200, json=joinable_payload("AUTH_REQUIRED"))).get_joinable_team_facts(auth, 100123)

    assert malformed.error_code == "TOOL_MALFORMED_JSON"
    assert wrong_schema.error_code == extra_field.error_code == "TOOL_CONTRACT_MISMATCH"
    assert (connection.error_code, connection.retryable) == ("TOOL_CONNECTION_ERROR", True)
    assert (java_error.error_code, java_error.retryable) == ("AUTH_REQUIRED", False)


def test_tool_uses_trusted_state_identity_and_has_no_state_side_effect() -> None:
    client = RecordingJoinableClient(joinable_result())
    tool = JoinableTeamFactsTool(client)
    state = AgentState(session_id="joinable-auth", authenticated_user_id="trusted-user")
    before = state.model_dump()

    result = tool.run(state, JoinableTeamFactsArguments(activityId=100123))

    assert result.success is True and state.model_dump() == before
    assert client.calls[0][0].authenticated_user_id == "trusted-user"
    assert client.calls[0][1] == 100123
    missing_auth = tool.run(AgentState(session_id="joinable-no-auth", authenticated_user_id=""), JoinableTeamFactsArguments(activityId=100123))
    assert (missing_auth.success, missing_auth.error_code) == (False, "AUTH_REQUIRED")
    assert len(client.calls) == 1


def test_joinable_tool_metadata_registry_capability_and_unknown_tool_boundaries() -> None:
    joinable_tool = JoinableTeamFactsTool(RecordingJoinableClient(joinable_result()))
    registry = ToolRegistry([OrderFactsTool(FakeMarketClient({})), joinable_tool])
    state = AgentState(session_id="joinable-registry", authenticated_user_id="trusted-user")

    assert "user_id" not in str(inspect.signature(JoinableTeamFactsTool.run))
    assert joinable_tool.repeat_policy.repeatable is True and joinable_tool.repeat_policy.max_same_call == 2
    assert tuple(item["name"] for item in registry.available_tools) == ("get_order_facts", "get_joinable_team_facts")
    assert registry.available_tools[1]["parameters_schema"]["required"] == ["activityId"]
    assert "candidate teams" in registry.available_tools[1]["description"]
    assert "get_joinable_team_facts" not in inspect.getsource(ToolRegistry)
    assert state.capability.allowed_tools == ("get_order_facts", "get_joinable_team_facts")
    arguments = registry.validate_arguments("get_joinable_team_facts", {"activityId": 100123})
    assert isinstance(arguments, JoinableTeamFactsArguments)
    assert registry.call("get_joinable_team_facts", state, arguments).success is True
    assert registry.validate_arguments("refund_order", {"activityId": 100123}) is None
    assert registry.call("refund_order", state, arguments).error_code == "TOOL_NOT_ALLOWED"


def test_dynamic_agent_can_request_joinable_tool_and_pass_its_observation_to_the_next_decision() -> None:
    client = RecordingJoinableClient(joinable_result())
    model = FakeDecisionModel([
        {"action": "CALL_TOOL", "tool_name": "get_joinable_team_facts", "tool_arguments": {"activityId": 100123}},
        {
            "action": "ANSWER", "final_answer": "已获取当前可加入候选团队与活动统计。",
            "used_evidence": [
                "get_joinable_team_facts.activity_id",
                "get_joinable_team_facts.statistics.all_team_count",
                "get_joinable_team_facts.candidate_teams.0.team_id",
            ],
        },
    ])
    agent = OrderFactsOrchestrator(
        registry=ToolRegistry([OrderFactsTool(FakeMarketClient({})), JoinableTeamFactsTool(client)]),
        decision_model=model,
    )

    state = agent.handle_message("joinable-loop", "trusted-user", "这个活动还能加入哪些团？")

    assert state.status is AgentStatus.FINISHED
    assert state.tool_call_count == 1 and len(client.calls) == 1
    assert [observation.tool_name for observation in state.observations] == ["get_joinable_team_facts"]
    assert state.observations[0].data["statistics"]["all_team_user_count"] == 3
    assert "joinable_team_facts" not in state.context.model_dump()
    assert {tool.name for tool in model.contexts[0].available_tools} == {"get_order_facts", "get_joinable_team_facts"}
    assert model.contexts[1].observations[0].tool_name == "get_joinable_team_facts"
    assert "get_joinable_team_facts.statistics.all_team_count" in [item["kind"] for item in model.contexts[1].evidence]


def test_dynamic_agent_accepts_empty_candidate_collection_as_final_answer_evidence() -> None:
    client = RecordingJoinableClient(empty_joinable_result())
    model = FakeDecisionModel([
        {"action": "CALL_TOOL", "tool_name": "get_joinable_team_facts", "tool_arguments": {"activityId": 100123}},
        {
            "action": "ANSWER", "final_answer": "本次查询没有返回候选团队。",
            "used_evidence": ["get_joinable_team_facts.candidate_teams"],
        },
    ])
    agent = OrderFactsOrchestrator(
        registry=ToolRegistry([OrderFactsTool(FakeMarketClient({})), JoinableTeamFactsTool(client)]),
        decision_model=model,
    )

    state = agent.handle_message("empty-joinable-loop", "trusted-user", "活动还有可加入的团吗？")

    assert state.status is AgentStatus.FINISHED
    assert state.observations[0].data["candidate_teams"] == []
    assert "get_joinable_team_facts.candidate_teams" in [item["kind"] for item in model.contexts[1].evidence]


def test_two_observation_answer_accepts_order_and_empty_candidate_evidence_together() -> None:
    joinable_client = RecordingJoinableClient(empty_joinable_result())
    model = FakeDecisionModel([
        {"action": "CALL_TOOL", "tool_name": "get_order_facts", "tool_arguments": {"outTradeNo": "202608240001"}},
        {"action": "CALL_TOOL", "tool_name": "get_joinable_team_facts", "tool_arguments": {"activityId": 100123}},
        {
            "action": "ANSWER", "final_answer": "订单事实已获取，本次查询没有返回候选团队。",
            "used_evidence": [
                "get_order_facts.order.status",
                "get_joinable_team_facts.candidate_teams",
            ],
        },
    ])
    agent = OrderFactsOrchestrator(
        registry=ToolRegistry([
            OrderFactsTool(FakeMarketClient({"202608240001": order_result_for_cross_tool_evidence()})),
            JoinableTeamFactsTool(joinable_client),
        ]),
        decision_model=model,
    )

    state = agent.handle_message("cross-tool-empty-evidence", "trusted-user", "查询订单和其它可加入团队")

    assert state.status is AgentStatus.FINISHED
    assert [item.tool_name for item in state.observations] == ["get_order_facts", "get_joinable_team_facts"]
    assert [item.tool_name for item in model.contexts[2].observations] == ["get_order_facts", "get_joinable_team_facts"]
    assert "get_joinable_team_facts.candidate_teams" in [item["kind"] for item in model.contexts[2].evidence]
