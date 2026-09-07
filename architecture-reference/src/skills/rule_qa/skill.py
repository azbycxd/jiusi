"""规则问答 Skill；知识证据必需，实例 Facts 不在能力范围。"""
from ..base import KnowledgePolicy, SecurityPolicy, SkillSpec
from .completion_policy import (
    complete, EVIDENCE_OBLIGATIONS, POSSIBLE_DIMENSIONS, resolve_requirements,
)
from .context_policy import select
from .failure_policy import decide
from .prompt import PROMPT

SPEC = SkillSpec(
    name="rule_qa", version="reference-1", description="解释稳定拼团规则与术语",
    required_entities=(), allowed_tools=("search_group_buy_rules",),
    knowledge_policy=KnowledgePolicy.REQUIRED,
    prompt_policy=PROMPT, context_policy="RAG evidence only",
    progress_policy="non-empty rule Evidence Obligation evaluation",
    completion_policy="at least one rule Evidence satisfies the obligation",
    failure_policy="empty/unavailable knowledge hands off",
    possible_dimensions=POSSIBLE_DIMENSIONS,
    evidence_obligations=EVIDENCE_OBLIGATIONS,
    runtime_budget={"max_iterations": 5, "max_tool_calls": 2, "max_model_calls": 5,
                    "max_tool_retries": 1, "max_same_call": 1},
    security_policy=SecurityPolicy(allow_request_input=False, allow_rule_search=True),
    intents=("RULE_QA",), requirement_resolver=resolve_requirements,
    observation_selector=select, completion_resolver=complete, failure_resolver=decide,
)
