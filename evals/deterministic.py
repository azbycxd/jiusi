from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from agent.orchestrator import OrderFactsOrchestrator
from agent.state import AgentState, AgentStatus
from decision.model import FakeDecisionModel
from evals.contracts import EvalCase, EvalExecution, ExpectedFinalAction, ToolCallRecord
from tools.fake_market_client import FakeMarketClient
from tools.java_market_client import JoinableTeamFactsTool, OrderFactsTool
from tools.registry import ToolRegistry
from tools.rule_search import SearchGroupBuyRulesTool
from tools.schemas import Evidence, ToolResult


ORDER_NUMBER = "644398015396"
ACTIVITY_ID = 100123


def _order_result() -> ToolResult:
    data = {
        "order": {"status": "CLOSE"},
        "team": {"status": "PROGRESS", "target_count": 3, "lock_count": 0, "complete_count": 0},
        "activity": {"status": "EFFECTIVE"},
        "references": {"team_id": "18781389", "activity_id": ACTIVITY_ID},
    }
    return ToolResult(
        success=True, data=data, source="fake_market",
        evidence=[
            Evidence(kind="order.status", value="CLOSE", source="fake_market"),
            Evidence(kind="team.status", value="PROGRESS", source="fake_market"),
            Evidence(kind="team.target_count", value="3", source="fake_market"),
            Evidence(kind="team.complete_count", value="0", source="fake_market"),
            Evidence(kind="activity.status", value="EFFECTIVE", source="fake_market"),
            Evidence(kind="references.activity_id", value=str(ACTIVITY_ID), source="fake_market"),
        ],
    )


def _joinable_result() -> ToolResult:
    data = {
        "activity_id": ACTIVITY_ID,
        "candidate_teams": [],
        "statistics": {"all_team_count": 1, "all_team_complete_count": 1, "all_team_user_count": 3},
    }
    return ToolResult(
        success=True, data=data, source="fake_market",
        evidence=[
            Evidence(kind="activity_id", value=str(ACTIVITY_ID), source="fake_market"),
            Evidence(kind="statistics.all_team_count", value="1", source="fake_market"),
            Evidence(kind="statistics.all_team_complete_count", value="1", source="fake_market"),
            Evidence(kind="statistics.all_team_user_count", value="3", source="fake_market"),
            Evidence(kind="candidate_teams", value="[]", source="fake_market"),
        ],
    )


@dataclass
class FakeJoinableClient:
    result: ToolResult

    def get_joinable_team_facts(self, auth, activity_id: int) -> ToolResult:
        assert activity_id == ACTIVITY_ID
        return self.result


class _TraceCollector(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.errors: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        try:
            event = json.loads(record.getMessage())
        except (TypeError, json.JSONDecodeError):
            return
        error_code = event.get("error_code")
        if isinstance(error_code, str):
            self.errors.append(error_code)


def _tool_decision(tool_name: str, query: str) -> dict[str, object]:
    if tool_name == "get_order_facts":
        return {"action": "CALL_TOOL", "tool_name": tool_name, "tool_arguments": {"outTradeNo": ORDER_NUMBER}}
    if tool_name == "get_joinable_team_facts":
        return {"action": "CALL_TOOL", "tool_name": tool_name, "tool_arguments": {"activityId": ACTIVITY_ID}}
    return {"action": "CALL_TOOL", "tool_name": tool_name, "tool_arguments": {"query": query}}


def _answer_for_tools(tool_names: list[str]) -> dict[str, object]:
    paths: list[str] = []
    if "get_order_facts" in tool_names:
        paths.append("get_order_facts.team.status")
    if "get_joinable_team_facts" in tool_names:
        paths.append("get_joinable_team_facts.candidate_teams")
    if "search_group_buy_rules" in tool_names:
        paths.append("search_group_buy_rules.results.0.content")
    return {"action": "ANSWER", "final_answer": "受控评测回答。", "used_evidence": paths}


def _responses_for(case: EvalCase) -> list[object]:
    fixture = case.deterministic_fixture
    if fixture == "handoff":
        return [{"action": "HANDOFF", "missing_information": ["当前能力不足"]}]
    if fixture == "capability":
        return [{"action": "ANSWER", "final_answer": "当前能力说明。", "used_evidence": []}]
    if fixture == "attack_unknown":
        return [{"action": "ANSWER", "final_answer": "不可验证。", "used_evidence": ["fake.path"]}]
    if fixture == "attack_metadata":
        return [{"action": "ANSWER", "final_answer": "不可验证。", "used_evidence": ["available_tools.get_order_facts.description"]}]
    if fixture == "attack_empty_collection":
        return [
            _tool_decision("get_joinable_team_facts", case.user_query),
            {"action": "ANSWER", "final_answer": "不可验证。", "used_evidence": ["get_joinable_team_facts.candidate_teams.0.team_id"]},
        ]
    if fixture == "attack_governance":
        return [
            _tool_decision("search_group_buy_rules", case.user_query),
            {"action": "ANSWER", "final_answer": "不可验证。", "used_evidence": ["search_group_buy_rules.results.0.source_files"]},
        ]
    if fixture == "repeat_rule":
        decision = _tool_decision("search_group_buy_rules", case.user_query)
        return [decision, decision]
    if fixture in {"repeat_order", "repeat_joinable"}:
        tool_name = "get_order_facts" if fixture == "repeat_order" else "get_joinable_team_facts"
        decision = _tool_decision(tool_name, case.user_query)
        return [decision, decision, decision]
    if fixture == "different_rule_queries":
        return [
            _tool_decision("search_group_buy_rules", "拼团成团条件"),
            _tool_decision("search_group_buy_rules", "CLOSE状态含义"),
            {"action": "HANDOFF", "missing_information": ["结束评测"]},
        ]
    tools = list(case.required_tools)
    return [_tool_decision(name, case.user_query) for name in tools] + [_answer_for_tools(tools)]


def _records_from_state(state: AgentState) -> list[ToolCallRecord]:
    records: list[ToolCallRecord] = []
    for signature in state.context.tool_call_history:
        name, raw = signature.split(":", 1)
        records.append(ToolCallRecord(tool_name=name, arguments=json.loads(raw)))
    return records


def run_deterministic_case(case: EvalCase) -> EvalExecution:
    """Execute a case through the real harness with fake model and fact boundaries."""
    logger = logging.getLogger("group_buy_agent.trace")
    original_handlers = list(logger.handlers)
    collector = _TraceCollector()
    logger.handlers = [collector]
    model = FakeDecisionModel(_responses_for(case))
    registry = ToolRegistry([
        OrderFactsTool(FakeMarketClient({ORDER_NUMBER: _order_result()})),
        JoinableTeamFactsTool(FakeJoinableClient(_joinable_result())),
        SearchGroupBuyRulesTool(),
    ])
    try:
        state = OrderFactsOrchestrator(registry=registry, decision_model=model).handle_message(
            f"deterministic-{case.case_id}", "eval-trusted-user", case.user_query
        )
    finally:
        logger.handlers = original_handlers
    final_action = ExpectedFinalAction.ANSWER if state.status is AgentStatus.FINISHED else ExpectedFinalAction.HANDOFF
    decision = state.context.model_decision or {}
    used_evidence = decision.get("used_evidence", []) if decision.get("action") == "ANSWER" else []
    return EvalExecution(
        final_action=final_action, tool_calls=_records_from_state(state),
        observations=[item.model_dump(mode="json") for item in state.observations],
        used_evidence=used_evidence if isinstance(used_evidence, list) else [],
        final_answer=state.final_answer or "", model_call_count=state.model_call_count,
        model_retry_count=state.model_retry_count, retry_count=state.retry_count,
        guard_errors=collector.errors,
    )
