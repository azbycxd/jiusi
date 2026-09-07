"""AgentState + SkillSpec + ToolRegistry → 最小 DecisionContext。"""
from copy import deepcopy
from .compressor import ContextCompressor
from .decision_context import ContextBudget, DecisionContext
from .selector import ContextSelector
from ..prompts.base_system_prompt import SYSTEM_PROMPT
from ..prompts.decision_contract_prompt import DECISION_CONTRACT_PROMPT


class ContextBuilder:
    """完整 State 留在程序侧；身份、计数器、Trace、错误细节永不投影。"""
    def __init__(self, selector=None, compressor=None, budget=None):
        self.selector = selector or ContextSelector()
        self.compressor = compressor or ContextCompressor()
        self.budget = budget or ContextBudget()

    def build(self, state, skill, tools):
        observations = skill.select_observations(self.selector.select(state, skill, tools))
        evidence = tuple(item for observation in observations for item in observation.evidence)
        instructions = "\n\n".join((SYSTEM_PROMPT, skill.prompt_policy,
                                      DECISION_CONTRACT_PROMPT))
        context = DecisionContext(
            task_id=state.task_id,
            skill_name=skill.name,
            current_query=state.current_query,
            skill_instructions=instructions,
            relevant_observations=observations,
            available_evidence=evidence,
            skill_progress=deepcopy(state.skill_progress.snapshot()),
            available_tools=tuple(tools.describe(skill.allowed_tools)),
            context_version=state.state_version,
            estimated_tokens=0,
        )
        return self.compressor.fit(context, self.budget)
