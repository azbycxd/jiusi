from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from agent.orchestrator import OrderFactsOrchestrator
from agent.state import AgentState, AgentStatus, Observation
from decision.model import FakeDecisionModel
from decision.schemas import parse_agent_decision
from decision.validation import validate_evidence
from knowledge.catalog_loader import CatalogLoadError, DEFAULT_CATALOG_PATH, load_knowledge_catalog
from knowledge.evaluation import IRRELEVANT_RULE_QUERIES, evaluate_rule_retriever
from knowledge.retriever import LexicalRuleRetriever
from tools.arguments import SearchGroupBuyRulesArguments
from tools.fake_market_client import FakeMarketClient
from tools.java_market_client import JoinableTeamFactsTool, OrderFactsTool
from tools.registry import ToolRegistry
from tools.rule_search import SearchGroupBuyRulesTool


def catalog():
    return load_knowledge_catalog()


def retriever() -> LexicalRuleRetriever:
    return LexicalRuleRetriever(catalog())


def rule_tool() -> SearchGroupBuyRulesTool:
    return SearchGroupBuyRulesTool(retriever())


def test_catalog_loads_the_approved_fifteen_entries() -> None:
    loaded = catalog()
    assert loaded.catalog == "group_buy_rules"
    assert loaded.version == "v1"
    assert loaded.entry_count == 15 == len(loaded.entries)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda raw: raw.update(entry_count=14),
        lambda raw: raw["entries"].__setitem__(1, {**raw["entries"][1], "knowledge_id": raw["entries"][0]["knowledge_id"]}),
        lambda raw: raw["entries"][0].update(source_level="LEVEL_4"),
        lambda raw: raw["entries"][0].update(source_files=[]),
    ],
)
def test_catalog_contract_rejects_bad_count_duplicate_id_and_source_level(tmp_path, mutation) -> None:
    raw = json.loads(DEFAULT_CATALOG_PATH.read_text(encoding="utf-8"))
    mutation(raw)
    path = tmp_path / "invalid_catalog.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(CatalogLoadError):
        load_knowledge_catalog(path)


def test_rule_search_arguments_are_strict_and_normalized() -> None:
    assert SearchGroupBuyRulesArguments.model_validate({"query": "  CLOSE 是什么  "}).query == "CLOSE 是什么"
    for payload in (
        {"query": "   "},
        {"query": 123},
        {"query": "规则", "topK": 3},
        {"query": "规则", "source_files": []},
        {"query": "规则", "sql": "select 1"},
        {"query": "规则", "userId": "forbidden"},
        {"query": "规则", "token": "forbidden"},
    ):
        with pytest.raises(ValidationError):
            SearchGroupBuyRulesArguments.model_validate(payload)


@pytest.mark.parametrize(
    ("query", "knowledge_id"),
    [
        ("订单CLOSE是不是说明钱已经退回来了", "group_buy_close_status_semantics"),
        ("几个人才算拼团成功", "group_buy_team_complete_rule"),
        ("lockCount和completeCount有什么区别", "group_buy_team_count_semantics"),
    ],
)
def test_lexical_retriever_finds_core_rule_queries(query: str, knowledge_id: str) -> None:
    assert knowledge_id in [item.knowledge_id for item in retriever().search(query).results]


def test_retrieval_eval_and_irrelevant_query_rejection() -> None:
    local_retriever = retriever()
    metrics = evaluate_rule_retriever(local_retriever)
    assert metrics.top3_hit_rate >= 0.90
    assert all(local_retriever.search(query).results == [] for query in IRRELEVANT_RULE_QUERIES)


def test_rule_tool_hides_catalog_governance_fields_and_emits_observation_evidence() -> None:
    result = rule_tool().run(
        AgentState(session_id="rules-tool", authenticated_user_id="trusted-user"),
        SearchGroupBuyRulesArguments(query="CLOSE状态退款"),
    )
    assert result.success and result.source == "knowledge_catalog"
    assert set(result.data) == {"catalog_version", "query", "results"}
    assert result.data["results"]
    serialized = json.dumps(result.data, ensure_ascii=False)
    for forbidden in ("source_files", "source_symbols", "group-buy-market-domain", "TradeRepository.java", "cn.bugstack"):
        assert forbidden not in serialized
    observation = Observation.from_successful_tool_result("search_group_buy_rules", result)
    assert any(item.kind == "search_group_buy_rules.catalog_version" for item in observation.evidence)
    assert any(item.kind == "search_group_buy_rules.results.0.content" for item in observation.evidence)
    answer = parse_agent_decision({
        "action": "ANSWER", "final_answer": "CLOSE 不能单独证明退款到账。",
        "used_evidence": ["search_group_buy_rules.results.0.content"],
    })
    assert validate_evidence(answer, observations=[observation]).valid
    fabricated = parse_agent_decision({
        "action": "ANSWER", "final_answer": "不可验证。",
        "used_evidence": ["search_group_buy_rules.results.0.source_files"],
    })
    assert validate_evidence(fabricated, observations=[observation]).error_code == "MODEL_EVIDENCE_NOT_AVAILABLE"


def test_empty_rule_result_is_successful_and_produces_terminal_list_evidence() -> None:
    result = rule_tool().run(
        AgentState(session_id="rules-empty", authenticated_user_id="trusted-user"),
        SearchGroupBuyRulesArguments(query="今天天气怎么样"),
    )
    assert result.success and result.data["results"] == []
    observation = Observation.from_successful_tool_result("search_group_buy_rules", result)
    assert any(item.kind == "search_group_buy_rules.results" and item.value == "[]" for item in observation.evidence)


def test_registry_capability_and_repeat_policy_support_exactly_three_default_tools() -> None:
    tool = rule_tool()
    registry = ToolRegistry([
        OrderFactsTool(FakeMarketClient({})), JoinableTeamFactsTool(object()), tool,
    ])
    state = AgentState(session_id="rules-registry", authenticated_user_id="trusted-user")
    assert registry.allowed_names == ("get_order_facts", "get_joinable_team_facts", "search_group_buy_rules")
    assert state.capability.allowed_tools[:3] == registry.allowed_names
    assert registry.available_tools[2]["parameters_schema"]["required"] == ["query"]
    assert tool.repeat_policy.repeatable is False and tool.repeat_policy.max_same_call == 1


def test_same_rule_query_is_blocked_but_different_queries_can_run() -> None:
    tool = rule_tool()
    same_agent = OrderFactsOrchestrator(
        registry=ToolRegistry([tool]),
        decision_model=FakeDecisionModel([
            {"action": "CALL_TOOL", "tool_name": "search_group_buy_rules", "tool_arguments": {"query": "CLOSE 是什么"}},
            {"action": "CALL_TOOL", "tool_name": "search_group_buy_rules", "tool_arguments": {"query": "CLOSE 是什么"}},
        ]),
    )
    same_state = same_agent.handle_message("rules-repeat-same", "trusted-user", "查询规则")
    assert same_state.status is AgentStatus.HANDOFF and same_state.tool_call_count == 1

    different_agent = OrderFactsOrchestrator(
        registry=ToolRegistry([rule_tool()]),
        decision_model=FakeDecisionModel([
            {"action": "CALL_TOOL", "tool_name": "search_group_buy_rules", "tool_arguments": {"query": "CLOSE 是什么"}},
            {"action": "CALL_TOOL", "tool_name": "search_group_buy_rules", "tool_arguments": {"query": "拼团成团条件"}},
            {"action": "HANDOFF", "missing_information": ["结束测试"]},
        ]),
    )
    different_state = different_agent.handle_message("rules-repeat-different", "trusted-user", "查询规则")
    assert different_state.status is AgentStatus.HANDOFF and different_state.tool_call_count == 2
