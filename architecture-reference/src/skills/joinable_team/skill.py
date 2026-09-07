"""候选团队查询 Skill；空集合仍完成。"""
from ..base import KnowledgePolicy, SecurityPolicy, SkillSpec
from .completion_policy import (
    complete, EVIDENCE_OBLIGATIONS, POSSIBLE_DIMENSIONS, resolve_requirements,
)
from .context_policy import select
from .failure_policy import decide
from .prompt import PROMPT

SPEC = SkillSpec(
    name="joinable_team", version="reference-1",
    description="查询指定活动当前可加入的候选团队",
    required_entities=("activityId",),
    allowed_tools=("get_joinable_team_facts", "search_group_buy_rules"),
    knowledge_policy=KnowledgePolicy.OPTIONAL,
    prompt_policy=PROMPT, context_policy="candidate team facts and optional rules",
    progress_policy="candidate collection Evidence Obligation evaluation",
    completion_policy="candidate availability obligation satisfied, including empty list",
    failure_policy="request activityId or handoff safely",
    possible_dimensions=POSSIBLE_DIMENSIONS,
    evidence_obligations=EVIDENCE_OBLIGATIONS,
    runtime_budget={"max_iterations": 5, "max_tool_calls": 3, "max_model_calls": 5,
                    "max_tool_retries": 1, "max_same_call": 1},
    security_policy=SecurityPolicy(allow_rule_search=True),
    intents=("JOINABLE_TEAM",), requirement_resolver=resolve_requirements,
    observation_selector=select, completion_resolver=complete, failure_resolver=decide,
)
