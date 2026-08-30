from __future__ import annotations

from agent.state import AgentState
from knowledge.catalog_loader import load_knowledge_catalog
from knowledge.retriever import LexicalRuleRetriever, RuleRetriever
from tools.arguments import SearchGroupBuyRulesArguments
from tools.base import RepeatPolicy
from tools.schemas import Evidence, ToolResult


class SearchGroupBuyRulesTool:
    """Read-only lookup of reviewed stable rules, never a source of live user facts."""

    name = "search_group_buy_rules"
    description = (
        "Search stable group-buy rules, status meanings, and refund semantics. "
        "This is not a real-time order, team, or activity facts query."
    )
    arguments_schema = SearchGroupBuyRulesArguments
    repeat_policy = RepeatPolicy(repeatable=False, max_same_call=1)

    def __init__(self, retriever: RuleRetriever | None = None) -> None:
        self._retriever = retriever or LexicalRuleRetriever(load_knowledge_catalog())

    def run(self, state: AgentState, arguments: SearchGroupBuyRulesArguments) -> ToolResult:
        result = self._retriever.search(arguments.query)
        data = result.model_dump(mode="json")
        evidence = [Evidence(kind="catalog_version", value=result.catalog_version, source="knowledge_catalog")]
        if not result.results:
            evidence.append(Evidence(kind="results", value="[]", source="knowledge_catalog"))
        for index, item in enumerate(result.results):
            prefix = f"results.{index}"
            evidence.extend(
                Evidence(kind=f"{prefix}.{field}", value=str(getattr(item, field)), source="knowledge_catalog")
                for field in ("knowledge_id", "title", "content", "requires_realtime_facts")
            )
        return ToolResult(success=True, data=data, evidence=evidence, source="knowledge_catalog")
