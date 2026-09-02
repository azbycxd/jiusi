from __future__ import annotations

import json

from pydantic import BaseModel

from agent.orchestrator import OrderFactsOrchestrator
from agent.state import AgentStatus
from decision.model import FakeDecisionModel
from tools.arguments import ActivityFactsArguments
from tools.base import RepeatPolicy
from tools.registry import ToolRegistry
from tools.schemas import Evidence, ToolResult


class DimensionTool:
    arguments_schema = ActivityFactsArguments
    repeat_policy = RepeatPolicy(repeatable=False, max_same_call=1)

    def __init__(self, name: str, data: dict, evidence: list[Evidence], dimension: str | None) -> None:
        self.name = name
        self.description = f"test {name}"
        self._data = data
        self._evidence = evidence
        self.calls: list[dict] = []
        if dimension is not None:
            self.diagnosis_dimension = dimension

    def run(self, state, arguments: BaseModel) -> ToolResult:
        self.calls.append(arguments.model_dump(by_alias=True))
        return ToolResult(success=True, data=self._data, evidence=self._evidence, source="test")


def _activity_tool() -> DimensionTool:
    return DimensionTool(
        "get_activity_facts",
        {"activity": {"status": "EFFECTIVE", "within_valid_time": True}},
        [
            Evidence(kind="activity.status", value="EFFECTIVE", source="test"),
            Evidence(kind="activity.within_valid_time", value="True", source="test"),
        ],
        "activity",
    )


def _eligibility_tool() -> DimensionTool:
    return DimensionTool(
        "get_user_eligibility_facts",
        {"participation_limit_reached": True, "user_take_count": 1, "user_take_limit": 1},
        [
            Evidence(kind="participation_limit_reached", value="True", source="test"),
            Evidence(kind="user_take_count", value="1", source="test"),
            Evidence(kind="user_take_limit", value="1", source="test"),
        ],
        "eligibility",
    )


def _joinable_tool() -> DimensionTool:
    return DimensionTool(
        "get_joinable_team_facts",
        {"candidate_teams": []},
        [Evidence(kind="candidate_teams", value="[]", source="test")],
        None,
    )


def _call(tool_name: str) -> dict:
    return {"action": "CALL_TOOL", "tool_name": tool_name, "tool_arguments": {"activityId": 100123}}


def _answer(evidence: list[str]) -> dict:
    return {"action": "ANSWER", "final_answer": "基于实时事实的诊断结论。", "used_evidence": evidence}


def _agent(responses: list[object], tools: list[DimensionTool]) -> tuple[OrderFactsOrchestrator, FakeDecisionModel]:
    model = FakeDecisionModel(responses)
    return OrderFactsOrchestrator(registry=ToolRegistry(tools), decision_model=model), model


def test_progress_blocks_premature_answer_until_all_relevant_dimensions_are_checked(caplog) -> None:
    caplog.set_level("INFO", logger="group_buy_agent.trace")
    activity = _activity_tool()
    eligibility = _eligibility_tool()
    agent, model = _agent([
        _call("get_user_eligibility_facts"),
        _answer(["get_user_eligibility_facts.participation_limit_reached"]),
        _call("get_activity_facts"),
        _answer([
            "get_user_eligibility_facts.participation_limit_reached",
            "get_activity_facts.activity.status",
            "get_activity_facts.activity.within_valid_time",
        ]),
    ], [activity, eligibility])

    state = agent.handle_message("progress-premature", "trusted-user", "为什么我参加不了活动 100123？")

    assert state.status is AgentStatus.FINISHED
    assert state.tool_call_count == 2
    assert state.diagnosis_progress is not None
    assert state.diagnosis_progress.checked_dimensions == ("eligibility", "activity")
    assert state.diagnosis_progress.remaining_dimensions == ()
    assert model.contexts[0].diagnosis_progress is not None
    assert model.contexts[1].diagnosis_progress.remaining_dimensions == ("activity",)
    assert model.contexts[2].diagnosis_progress.remaining_dimensions == ("activity",)
    assert model.contexts[3].diagnosis_progress.is_complete
    events = [json.loads(record.message) for record in caplog.records]
    assert any(
        event["stage"] == "DIAGNOSIS_PROGRESS_BLOCKED"
        and event["error_code"] == "DIAGNOSIS_DIMENSIONS_REMAIN"
        for event in events
    )


def test_progress_blocks_irrelevant_tool_after_completion_and_allows_model_answer(caplog) -> None:
    caplog.set_level("INFO", logger="group_buy_agent.trace")
    activity = _activity_tool()
    eligibility = _eligibility_tool()
    joinable = _joinable_tool()
    agent, _ = _agent([
        _call("get_activity_facts"),
        _call("get_user_eligibility_facts"),
        _call("get_joinable_team_facts"),
        _answer([
            "get_activity_facts.activity.status",
            "get_user_eligibility_facts.participation_limit_reached",
        ]),
    ], [activity, eligibility, joinable])

    state = agent.handle_message("progress-over-query", "trusted-user", "为什么我参加不了活动 100123？")

    assert state.status is AgentStatus.FINISHED
    assert state.tool_call_count == 2
    assert joinable.calls == []
    events = [json.loads(record.message) for record in caplog.records]
    assert any(
        event["stage"] == "DIAGNOSIS_PROGRESS_BLOCKED"
        and event["error_code"] == "DIAGNOSIS_ALREADY_COMPLETE"
        for event in events
    )


def test_non_diagnostic_control_question_keeps_minimal_tool_usage() -> None:
    activity = _activity_tool()
    agent, model = _agent([
        _call("get_activity_facts"),
        _answer(["get_activity_facts.activity.within_valid_time"]),
    ], [activity])

    state = agent.handle_message("progress-control", "trusted-user", "活动 100123 是否还在有效期内？")

    assert state.status is AgentStatus.FINISHED
    assert state.tool_call_count == 1 and len(activity.calls) == 1
    assert state.diagnosis_progress is None
    assert model.contexts[0].diagnosis_progress is None


def test_request_input_preserves_diagnosis_progress_until_same_session_completes() -> None:
    activity = _activity_tool()
    eligibility = _eligibility_tool()
    agent, model = _agent([
        {"action": "REQUEST_INPUT", "missing_information": ["activityId"]},
        _call("get_activity_facts"),
        _call("get_user_eligibility_facts"),
        _answer([
            "get_activity_facts.activity.status",
            "get_user_eligibility_facts.participation_limit_reached",
        ]),
    ], [activity, eligibility])

    waiting = agent.handle_message("progress-resume", "trusted-user", "为什么我参加不了这个活动？")
    assert waiting.status is AgentStatus.WAITING_INPUT
    assert waiting.diagnosis_progress is not None
    assert waiting.diagnosis_progress.remaining_dimensions == ("activity", "eligibility")

    finished = agent.handle_message("progress-resume", "trusted-user", "活动是 100123")
    assert finished.status is AgentStatus.FINISHED
    assert finished.diagnosis_progress is not None and finished.diagnosis_progress.is_complete
    assert "为什么我参加不了这个活动？" in model.contexts[1].user_query
    assert "活动是 100123" in model.contexts[1].user_query
