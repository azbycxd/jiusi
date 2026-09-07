"""订单事实诊断 Skill。"""
from ..base import KnowledgePolicy, SecurityPolicy, SkillSpec
from .completion_policy import (
    complete, EVIDENCE_OBLIGATIONS, POSSIBLE_DIMENSIONS, resolve_requirements,
)
from .context_policy import select
from .failure_policy import decide
from .prompt import PROMPT

SPEC = SkillSpec(
    name="order_diagnosis", version="reference-1",
    description="解释订单和拼团订单的当前事实",
    required_entities=("outTradeNo",),
    allowed_tools=("get_order_facts", "search_group_buy_rules"),
    knowledge_policy=KnowledgePolicy.OPTIONAL,
    prompt_policy=PROMPT, context_policy="order facts and optional rules",
    progress_policy="order Evidence Obligation evaluation",
    completion_policy="query-scoped order obligation satisfied",
    failure_policy="request outTradeNo or handoff safely",
    possible_dimensions=POSSIBLE_DIMENSIONS,
    evidence_obligations=EVIDENCE_OBLIGATIONS,
    runtime_budget={"max_iterations": 6, "max_tool_calls": 3, "max_model_calls": 6,
                    "max_tool_retries": 1, "max_same_call": 1},
    security_policy=SecurityPolicy(allow_rule_search=True),
    intents=("ORDER_DIAGNOSIS",), requirement_resolver=resolve_requirements,
    observation_selector=select, completion_resolver=complete, failure_resolver=decide,
)
