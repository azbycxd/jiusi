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
from tools.arguments import ActivityFactsArguments, UserEligibilityFactsArguments
from tools.java_market_client import (
    ActivityFactsTool,
    JavaMarketClient,
    JavaMarketClientConfig,
    UserEligibilityFactsTool,
)
from tools.registry import ToolRegistry
from tools.schemas import ToolResult


def activity_payload(code: str = "0000", data: dict | None = None) -> dict:
    return {
        "code": code,
        "info": "ignored by the Python contract",
        "data": data if data is not None else {
            "activity": {
                "activityId": 100123,
                "status": "EFFECTIVE",
                "startTime": "2024-12-07T10:19:40+08:00",
                "endTime": "2029-12-07T10:19:40+08:00",
                "tagScope": "2",
                "userTakeLimit": 1,
                "evaluatedAt": "2026-09-01T23:11:04+08:00",
                "withinValidTime": True,
            }
        },
    }


def eligibility_payload(code: str = "0000", data: dict | None = None) -> dict:
    return {
        "code": code,
        "info": "ignored by the Python contract",
        "data": data if data is not None else {
            "activityId": 100123,
            "tagRuleConfigured": True,
            "tagCrowdDataAvailable": True,
            "tagGatePassed": True,
            "tagVisibilityAllowed": True,
            "tagParticipationAllowed": True,
            "userTakeCount": 0,
            "userTakeLimit": 1,
            "participationLimitReached": False,
            "marketDowngraded": False,
            "userWithinReleaseRange": True,
        },
    }


def market_client(handler) -> JavaMarketClient:
    return JavaMarketClient(
        JavaMarketClientConfig(base_url="http://market.test", timeout_seconds=0.1, enable_dev_auth_header=True),
        httpx.Client(transport=httpx.MockTransport(handler)),
    )


@pytest.mark.parametrize(
    "arguments",
    [
        {}, {"activityId": 0}, {"activityId": -1}, {"activityId": True}, {"activityId": "100123"},
        {"activityId": 100123, "userId": "forbidden"},
        {"activityId": 100123, "authenticatedUserId": "forbidden"},
        {"activityId": 100123, "token": "forbidden"},
        {"activityId": 100123, "header": "forbidden"},
        {"activityId": 100123, "authorization": "forbidden"},
        {"activityId": 100123, "baseUrl": "forbidden"},
    ],
)
def test_activity_scoped_arguments_reject_non_strict_and_identity_fields(arguments: object) -> None:
    for schema in (ActivityFactsArguments, UserEligibilityFactsArguments):
        with pytest.raises(ValidationError):
            schema.model_validate(arguments)


def test_activity_client_validates_contract_injects_trusted_identity_and_emits_false_evidence() -> None:
    data = activity_payload()["data"]
    data["activity"]["withinValidTime"] = False

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/api/v1/agent/activity/facts"
        assert json.loads(request.content) == {"activityId": 100123}
        assert request.headers["X-Dev-Authenticated-User-Id"] == "trusted-user"
        return httpx.Response(200, json=activity_payload(data=data))

    result = market_client(handler).get_activity_facts(AuthContext(authenticated_user_id="trusted-user"), 100123)

    assert result.success is True and result.source == "java_market"
    assert result.data["activity"]["activity_id"] == 100123
    assert result.data["activity"]["within_valid_time"] is False
    assert ("activity.within_valid_time", "False") in {(item.kind, item.value) for item in result.evidence}
    observation = Observation.from_successful_tool_result("get_activity_facts", result)
    assert "get_activity_facts.activity.within_valid_time" in [item.kind for item in observation.evidence]


def test_activity_null_user_take_limit_is_preserved_without_evidence_corruption() -> None:
    data = activity_payload()["data"]
    data["activity"]["userTakeLimit"] = None
    result = market_client(lambda _: httpx.Response(200, json=activity_payload(data=data))).get_activity_facts(
        AuthContext(authenticated_user_id="trusted-user"), 100123
    )

    assert result.success is True and result.data["activity"]["user_take_limit"] is None
    assert all(item.kind != "activity.user_take_limit" for item in result.evidence)
    assert Observation.from_successful_tool_result("get_activity_facts", result).data["activity"]["user_take_limit"] is None


@pytest.mark.parametrize(
    ("code", "retryable"),
    [
        ("ACTIVITY_NOT_FOUND", False),
        ("AUTH_REQUIRED", False),
        ("INVALID_ARGUMENT", False),
        ("INTERNAL_SERVICE_ERROR", True),
    ],
)
def test_activity_java_codes_have_stable_error_mapping(code: str, retryable: bool) -> None:
    result = market_client(lambda _: httpx.Response(200, json=activity_payload(code))).get_activity_facts(
        AuthContext(authenticated_user_id="trusted-user"), 100123
    )
    assert (result.success, result.error_code, result.retryable) == (False, code, retryable)


def test_activity_transport_and_schema_failures_do_not_escape_the_client() -> None:
    auth = AuthContext(authenticated_user_id="trusted-user")
    connection = market_client(lambda _: (_ for _ in ()).throw(httpx.ConnectError("down"))).get_activity_facts(auth, 100123)
    malformed = market_client(lambda _: httpx.Response(200, content=b"{")).get_activity_facts(auth, 100123)
    mismatch = market_client(lambda _: httpx.Response(200, json=activity_payload(data={"activity": {}}))).get_activity_facts(auth, 100123)
    extra = market_client(lambda _: httpx.Response(200, json=activity_payload(data={
        **activity_payload()["data"], "unexpected": "forbidden",
    }))).get_activity_facts(auth, 100123)
    assert (connection.error_code, connection.retryable) == ("TOOL_CONNECTION_ERROR", True)
    assert malformed.error_code == "TOOL_MALFORMED_JSON"
    assert mismatch.error_code == extra.error_code == "TOOL_CONTRACT_MISMATCH"


@pytest.mark.parametrize(
    ("overrides", "evidence_kind", "evidence_value"),
    [
        ({"tagCrowdDataAvailable": True, "tagGatePassed": True}, "tag_gate_passed", "True"),
        ({"tagCrowdDataAvailable": True, "tagGatePassed": False}, "tag_gate_passed", "False"),
        ({"tagCrowdDataAvailable": False, "tagGatePassed": True}, "tag_crowd_data_available", "False"),
        ({"tagParticipationAllowed": False}, "tag_participation_allowed", "False"),
        ({"participationLimitReached": True}, "participation_limit_reached", "True"),
        ({"marketDowngraded": True}, "market_downgraded", "True"),
        ({"userWithinReleaseRange": False}, "user_within_release_range", "False"),
    ],
)
def test_eligibility_boolean_contract_preserves_real_fallback_and_false_evidence(
    overrides: dict, evidence_kind: str, evidence_value: str
) -> None:
    data = eligibility_payload()["data"]
    data.update(overrides)
    result = market_client(lambda _: httpx.Response(200, json=eligibility_payload(data=data))).get_user_eligibility_facts(
        AuthContext(authenticated_user_id="trusted-user"), 100123
    )

    assert result.success is True
    assert result.data["tag_crowd_data_available"] is data["tagCrowdDataAvailable"]
    assert result.data["tag_gate_passed"] is data["tagGatePassed"]
    assert (evidence_kind, evidence_value) in {(item.kind, item.value) for item in result.evidence}
    observation = Observation.from_successful_tool_result("get_user_eligibility_facts", result)
    assert f"get_user_eligibility_facts.{evidence_kind}" in [item.kind for item in observation.evidence]


def test_eligibility_null_user_take_limit_is_not_coerced_to_zero() -> None:
    data = eligibility_payload()["data"]
    data["userTakeLimit"] = None
    result = market_client(lambda _: httpx.Response(200, json=eligibility_payload(data=data))).get_user_eligibility_facts(
        AuthContext(authenticated_user_id="trusted-user"), 100123
    )

    assert result.success is True and result.data["user_take_limit"] is None
    assert all(item.kind != "user_take_limit" for item in result.evidence)
    assert Observation.from_successful_tool_result("get_user_eligibility_facts", result).data["user_take_limit"] is None


def test_eligibility_rejects_unexpected_java_response_fields() -> None:
    data = {**eligibility_payload()["data"], "eligible": True}
    result = market_client(lambda _: httpx.Response(200, json=eligibility_payload(data=data))).get_user_eligibility_facts(
        AuthContext(authenticated_user_id="trusted-user"), 100123
    )
    assert result.error_code == "TOOL_CONTRACT_MISMATCH"


@pytest.mark.parametrize(
    ("code", "retryable"),
    [
        ("ACTIVITY_NOT_FOUND", False),
        ("AUTH_REQUIRED", False),
        ("INVALID_ARGUMENT", False),
        ("INTERNAL_SERVICE_ERROR", True),
    ],
)
def test_eligibility_java_codes_have_stable_error_mapping(code: str, retryable: bool) -> None:
    result = market_client(lambda _: httpx.Response(200, json=eligibility_payload(code))).get_user_eligibility_facts(
        AuthContext(authenticated_user_id="trusted-user"), 100123
    )
    assert (result.success, result.error_code, result.retryable) == (False, code, retryable)


class RecordingActivityClient:
    def __init__(self, result: ToolResult) -> None:
        self.result = result
        self.calls: list[tuple[object, int]] = []

    def get_activity_facts(self, auth: object, activity_id: int) -> ToolResult:
        self.calls.append((auth, activity_id))
        return self.result


class RecordingEligibilityClient:
    def __init__(self, result: ToolResult) -> None:
        self.result = result
        self.calls: list[tuple[object, int]] = []

    def get_user_eligibility_facts(self, auth: object, activity_id: int) -> ToolResult:
        self.calls.append((auth, activity_id))
        return self.result


def test_new_tools_use_only_trusted_state_identity_and_do_not_mutate_state() -> None:
    activity_result = market_client(lambda _: httpx.Response(200, json=activity_payload())).get_activity_facts(
        AuthContext(authenticated_user_id="trusted-user"), 100123
    )
    eligibility_result = market_client(lambda _: httpx.Response(200, json=eligibility_payload())).get_user_eligibility_facts(
        AuthContext(authenticated_user_id="trusted-user"), 100123
    )
    activity_client = RecordingActivityClient(activity_result)
    eligibility_client = RecordingEligibilityClient(eligibility_result)
    activity_tool = ActivityFactsTool(activity_client)
    eligibility_tool = UserEligibilityFactsTool(eligibility_client)
    state = AgentState(session_id="new-tool-auth", authenticated_user_id="trusted-user")
    before = state.model_dump()

    assert activity_tool.run(state, ActivityFactsArguments(activityId=100123)).success
    assert eligibility_tool.run(state, UserEligibilityFactsArguments(activityId=100123)).success
    assert state.model_dump() == before
    assert activity_client.calls[0][0].authenticated_user_id == "trusted-user"
    assert eligibility_client.calls[0][0].authenticated_user_id == "trusted-user"
    assert "user_id" not in str(inspect.signature(ActivityFactsTool.run))
    assert "user_id" not in str(inspect.signature(UserEligibilityFactsTool.run))
    assert "user_id" not in str(ActivityFactsArguments.model_json_schema(by_alias=True))
    assert "user_id" not in str(UserEligibilityFactsArguments.model_json_schema(by_alias=True))
    missing_state = AgentState(session_id="new-tool-no-auth", authenticated_user_id="")
    assert activity_tool.run(missing_state, ActivityFactsArguments(activityId=100123)).error_code == "AUTH_REQUIRED"
    assert eligibility_tool.run(missing_state, UserEligibilityFactsArguments(activityId=100123)).error_code == "AUTH_REQUIRED"
    assert len(activity_client.calls) == len(eligibility_client.calls) == 1


def test_activity_connection_failure_retries_finitely_through_runtime_policy() -> None:
    failure = ToolResult.infrastructure_failure("TOOL_CONNECTION_ERROR", "down", retryable=True, source="test")
    client = RecordingActivityClient(failure)
    agent = OrderFactsOrchestrator(
        registry=ToolRegistry([ActivityFactsTool(client)]),
        decision_model=FakeDecisionModel([
            {"action": "CALL_TOOL", "tool_name": "get_activity_facts", "tool_arguments": {"activityId": 100123}},
        ]),
    )

    state = agent.handle_message("activity-retry", "trusted-user", "查询活动")

    assert state.status is AgentStatus.HANDOFF
    assert state.tool_call_count == 2 and state.retry_count == 1 and len(client.calls) == 2


def test_default_registry_exposes_exactly_five_generic_tools_to_decision_context() -> None:
    model = FakeDecisionModel([{"action": "ANSWER", "final_answer": "能力说明", "used_evidence": []}])
    agent = OrderFactsOrchestrator(decision_model=model)
    state = agent.handle_message("five-tools", "trusted-user", "你能做什么？")

    names = tuple(item["name"] for item in agent.registry.available_tools)
    assert names == (
        "get_order_facts", "get_joinable_team_facts", "search_group_buy_rules",
        "get_activity_facts", "get_user_eligibility_facts",
    )
    assert state.status is AgentStatus.FINISHED
    assert {item.name for item in model.contexts[0].available_tools} == set(names)
    schemas = {item["name"]: item["parameters_schema"] for item in agent.registry.available_tools}
    assert schemas["get_activity_facts"]["required"] == ["activityId"]
    assert schemas["get_user_eligibility_facts"]["required"] == ["activityId"]
    assert agent.registry.repeat_policy("get_activity_facts").allowed_same_call_count == 1
    assert agent.registry.repeat_policy("get_user_eligibility_facts").allowed_same_call_count == 1
    assert "get_activity_facts" not in inspect.getsource(ToolRegistry)
    assert "get_user_eligibility_facts" not in inspect.getsource(ToolRegistry)
