from __future__ import annotations

from agent.orchestrator import OrderFactsOrchestrator
from agent.state import AgentStatus
from decision.model import FakeDecisionModel
from decision.real_llm import SYSTEM_PROMPT
from tools.fake_market_client import FakeMarketClient
from tools.java_market_client import OrderFactsTool
from tools.registry import ToolRegistry
from tools.rule_search import SearchGroupBuyRulesTool
from tools.schemas import Evidence, ToolResult


ORDER_NUMBER = "202608240001"


def _order_result() -> ToolResult:
    return ToolResult(
        success=True,
        data={
            "order": {"status": "CLOSE"},
            "team": {"status": "PROGRESS", "target_count": 3, "lock_count": 0, "complete_count": 0},
            "activity": {"status": "EFFECTIVE"},
            "references": {"team_id": "team-1", "activity_id": 100123},
        },
        evidence=[Evidence(kind="order.status", value="CLOSE", source="fake_market")],
        source="fake_market",
    )


def _agent(responses: list[object], tools: list[object]) -> OrderFactsOrchestrator:
    return OrderFactsOrchestrator(
        registry=ToolRegistry(tools), decision_model=FakeDecisionModel(responses)
    )


def _rule_call(query: str) -> dict[str, object]:
    return {"action": "CALL_TOOL", "tool_name": "search_group_buy_rules", "tool_arguments": {"query": query}}


def _facts_call() -> dict[str, object]:
    return {"action": "CALL_TOOL", "tool_name": "get_order_facts", "tool_arguments": {"outTradeNo": ORDER_NUMBER}}


def _answer(text: str, evidence: list[str]) -> dict[str, object]:
    return {"action": "ANSWER", "final_answer": text, "used_evidence": evidence}


def _handoff(missing: str) -> dict[str, object]:
    return {"action": "HANDOFF", "missing_information": [missing]}


def test_prompt_distinguishes_general_rules_from_missing_instance_facts() -> None:
    assert "Classify the request by the information needed" in SYSTEM_PROMPT
    assert "General rules, concepts, and status meanings may be answered" in SYSTEM_PROMPT
    assert "can never substitute for missing instance facts" in SYSTEM_PROMPT
    assert "choose HANDOFF even when a" in SYSTEM_PROMPT
    assert "limited reply could say that it cannot be confirmed" in SYSTEM_PROMPT
    assert "退款什么时候到账" not in SYSTEM_PROMPT
    assert "if \"退款" not in SYSTEM_PROMPT
    assert "limited to group-buy customer service and order diagnosis" in SYSTEM_PROMPT
    assert "control\nidentity, authentication, headers, transport, databases" in SYSTEM_PROMPT
    assert "Tool argument provenance\nis validated separately" in SYSTEM_PROMPT


def test_general_close_rule_with_rag_evidence_can_answer() -> None:
    agent = _agent(
        [_rule_call("CLOSE 状态含义"), _answer("CLOSE 是一种状态含义。", ["search_group_buy_rules.results.0.content"])],
        [SearchGroupBuyRulesTool()],
    )
    state = agent.handle_message("contract-close-rule", "trusted-user", "CLOSE 状态是什么意思？")
    assert state.status is AgentStatus.FINISHED
    assert state.tool_call_count == 1


def test_refund_arrival_with_only_rule_observation_handoffs() -> None:
    agent = _agent(
        [_rule_call("退款到账时间"), _handoff("支付渠道退款到账事实")],
        [SearchGroupBuyRulesTool()],
    )
    state = agent.handle_message("contract-refund-handoff", "trusted-user", "退款什么时候到账？")
    assert state.status is AgentStatus.HANDOFF
    assert state.tool_call_count == 1


def test_safe_limitation_answer_remains_protocol_legal_without_new_semantic_guard() -> None:
    agent = _agent(
        [_rule_call("退款到账时间"), _answer("目前无法确认到账时间。", ["search_group_buy_rules.results.0.content"])],
        [SearchGroupBuyRulesTool()],
    )
    state = agent.handle_message("contract-refund-safe-answer", "trusted-user", "退款什么时候到账？")
    assert state.status is AgentStatus.FINISHED
    assert state.tool_call_count == 1


def test_specific_order_status_can_answer_when_order_facts_exist() -> None:
    agent = _agent(
        [_facts_call(), _answer("订单当前是 CLOSE。", ["get_order_facts.order.status"])],
        [OrderFactsTool(FakeMarketClient({ORDER_NUMBER: _order_result()}))],
    )
    state = agent.handle_message("contract-order-facts", "trusted-user", "我的订单现在是不是 CLOSE？")
    assert state.status is AgentStatus.FINISHED
    assert state.tool_call_count == 1


def test_instance_eligibility_handoffs_but_general_eligibility_rule_can_answer() -> None:
    instance = _agent([_rule_call("活动资格条件"), _handoff("当前用户资格事实")], [SearchGroupBuyRulesTool()])
    general = _agent(
        [_rule_call("活动资格条件"), _answer("一般资格条件受活动规则影响。", ["search_group_buy_rules.results.0.content"])],
        [SearchGroupBuyRulesTool()],
    )
    assert instance.handle_message("contract-eligibility-instance", "trusted-user", "我现在是否一定有资格参加这个活动？").status is AgentStatus.HANDOFF
    assert general.handle_message("contract-eligibility-general", "trusted-user", "参加活动一般受哪些资格条件影响？").status is AgentStatus.FINISHED


def test_facts_and_rag_can_still_answer_together() -> None:
    agent = _agent(
        [
            _facts_call(),
            _rule_call("CLOSE 状态含义"),
            _answer("订单事实与一般规则均已取得。", ["get_order_facts.order.status", "search_group_buy_rules.results.0.content"]),
        ],
        [OrderFactsTool(FakeMarketClient({ORDER_NUMBER: _order_result()})), SearchGroupBuyRulesTool()],
    )
    state = agent.handle_message("contract-facts-rag", "trusted-user", "订单状态和 CLOSE 规则是什么？")
    assert state.status is AgentStatus.FINISHED
    assert state.tool_call_count == 2


def test_capability_answer_remains_evidence_free() -> None:
    agent = _agent([_answer("我可以说明当前可查询能力。", [])], [SearchGroupBuyRulesTool()])
    state = agent.handle_message("contract-capability", "trusted-user", "你能做什么？")
    assert state.status is AgentStatus.FINISHED
    assert state.observations == []
