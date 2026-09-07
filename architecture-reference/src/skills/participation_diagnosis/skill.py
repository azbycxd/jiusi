"""参与诊断只声明范围和完成条件，不声明固定 Tool Workflow。"""
from ..base import KnowledgePolicy, SecurityPolicy, SkillSpec
from .completion_policy import (
    complete, EVIDENCE_OBLIGATIONS, POSSIBLE_DIMENSIONS, resolve_requirements,
)
from .context_policy import select
from .failure_policy import decide
from .prompt import PROMPT

SPEC = SkillSpec(
    name="participation_diagnosis", version="reference-1",
    description="诊断用户为何不能参加指定拼团活动",
    required_entities=("activityId",),
    allowed_tools=("get_activity_facts", "get_user_eligibility_facts", "search_group_buy_rules"),
    knowledge_policy=KnowledgePolicy.OPTIONAL,
    prompt_policy=PROMPT, context_policy="activity/eligibility relevant facts only",
    progress_policy="evidence obligations refresh query-scoped progress",
    completion_policy="all query-scoped evidence obligations satisfied",
    failure_policy="request missing entity; bounded retry; otherwise handoff",
    possible_dimensions=POSSIBLE_DIMENSIONS,
    evidence_obligations=EVIDENCE_OBLIGATIONS,
    runtime_budget={"max_iterations": 8, "max_tool_calls": 5, "max_model_calls": 8,
                    "max_tool_retries": 1, "max_same_call": 1},
    security_policy=SecurityPolicy(allow_rule_search=True),
    intents=("PARTICIPATION_DIAGNOSIS",), requirement_resolver=resolve_requirements,
    observation_selector=select, completion_resolver=complete, failure_resolver=decide,
)
