"""DecisionContext 是 AgentState 的模型可见投影，不是另一套运行状态。"""
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ContextBudget:
    """工程示例值，不代表当前真实项目实验得到的最优配置。"""
    max_estimated_tokens: int = 8000
    reserved_prompt_tokens: int = 1800
    reserved_output_tokens: int = 1000
    observation_budget: int = 2800
    rag_budget: int = 1400
    tools_budget: int = 1000

    @property
    def content_budget(self):
        return self.max_estimated_tokens - self.reserved_prompt_tokens - self.reserved_output_tokens


@dataclass(frozen=True)
class DecisionContext:
    task_id: str
    skill_name: str
    current_query: str
    skill_instructions: str
    relevant_observations: tuple[Any, ...]
    available_evidence: tuple[Any, ...]
    skill_progress: Any
    available_tools: tuple[Any, ...]
    context_version: int
    estimated_tokens: int

    @property
    def observations(self):
        """兼容早期 Reference 命名。"""
        return self.relevant_observations

    @property
    def evidence(self):
        return self.available_evidence
