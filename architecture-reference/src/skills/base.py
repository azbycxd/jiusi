"""
SkillSpec 是 B 层架构重构抽象：它描述一类可完整解决的业务任务。
Skill 比 Intent 重，因为它同时声明实体、工具、安全、上下文、进度和结束条件；
Skill 比 Tool 高，因为 Tool 只是一次动作；Skill 不是 SubAgent，不拥有独立模型或自治循环。
possible_dimensions 描述能力空间，RequirementResolver 决定本次 Query 的 Required 子集；
Evidence Obligation 规定必须获得什么事实，绝不规定固定 Tool 执行顺序。
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable
from ..progress.evidence_obligation import EvidenceObligationSpec
from ..progress.requirements import RequirementResolver, ResolvedRequirements

class KnowledgePolicy(str, Enum): REQUIRED='REQUIRED'; OPTIONAL='OPTIONAL'; NONE='NONE'

@dataclass(frozen=True)
class SecurityPolicy:
    """Skill 的最小权限边界，仍需 Harness 作为硬约束执行。"""
    allow_request_input: bool = True
    allow_handoff: bool = True
    allow_rule_search: bool = False
    forbidden_parameters: tuple[str,...] = ('userId','token','header','sql','redisKey')

@dataclass(frozen=True)
class SkillSpec:
    """可加载 Skill 的不可变配置；生命周期由 Orchestrator 管理。"""
    name: str
    version: str
    description: str
    required_entities: tuple[str,...]
    allowed_tools: tuple[str,...]
    knowledge_policy: KnowledgePolicy
    prompt_policy: str
    context_policy: str
    progress_policy: str
    completion_policy: str
    failure_policy: str
    possible_dimensions: tuple[str,...]
    evidence_obligations: tuple[EvidenceObligationSpec,...]
    runtime_budget: dict[str,int] = field(default_factory=lambda:{'max_iterations':8,'max_tool_calls':5,'max_same_call':1})
    security_policy: SecurityPolicy = field(default_factory=SecurityPolicy)
    intents: tuple[str,...] = ()
    requirement_resolver: RequirementResolver | None = field(default=None, repr=False, compare=False)
    observation_selector: Callable | None = field(default=None, repr=False, compare=False)
    completion_resolver: Callable | None = field(default=None, repr=False, compare=False)
    failure_resolver: Callable | None = field(default=None, repr=False, compare=False)

    def __post_init__(self):
        possible = tuple(self.possible_dimensions)
        if not possible or len(possible) != len(set(possible)):
            raise ValueError("possible_dimensions 必须非空且不重复")
        if any(not isinstance(item, EvidenceObligationSpec) for item in self.evidence_obligations):
            raise TypeError("evidence_obligations 必须使用 EvidenceObligationSpec")
        obligation_dimensions = [item.dimension for item in self.evidence_obligations]
        if len(obligation_dimensions) != len(set(obligation_dimensions)):
            raise ValueError("Evidence Obligation 维度不能重复")
        if not set(obligation_dimensions) <= set(possible):
            raise ValueError("Evidence Obligation 超出 possible_dimensions")

    def missing_entities(self, entities: dict[str,object]) -> list[str]:
        """Skill 激活前找出可由用户补齐的实体，供 REQUEST_INPUT 使用。"""
        return [name for name in self.required_entities if not entities.get(name)]

    def allows_tool(self, tool_name: str) -> bool:
        """在全局 Registry allowlist 之上再做 Skill 级最小权限限制。"""
        return tool_name in self.allowed_tools

    def resolve_requirements(self, query: str, *, routing_intent=None, routing_entities=None):
        """得到本次 Query 的 Required 子集；Resolver 不能访问身份、Trace 或错误。"""
        if self.requirement_resolver is None:
            resolved = ResolvedRequirements(frozenset(self.possible_dimensions), ("DEFAULT_ALL",))
        else:
            resolved = self.requirement_resolver(
                query,
                routing_intent=routing_intent,
                routing_entities=dict(routing_entities or {}),
            )
        if not isinstance(resolved, ResolvedRequirements):
            raise TypeError("requirement_resolver 必须返回 ResolvedRequirements")
        if not set(resolved.required_dimensions) <= set(self.possible_dimensions):
            raise ValueError("required_dimensions 超出 Skill possible_dimensions")
        for dimension in resolved.required_dimensions:
            self.evidence_obligation(dimension)
        return resolved

    def evidence_obligation(self, dimension: str):
        """按业务维度找证据契约；契约可接受多个 Tool Evidence 路径。"""
        matches = [item for item in self.evidence_obligations if item.dimension == dimension]
        if len(matches) != 1:
            raise ValueError(f"维度 {dimension} 缺少唯一 Evidence Obligation")
        return matches[0]

    def create_progress(self, goal: str, query: str | None = None, *,
                        routing_intent=None, routing_entities=None):
        """Skill 激活时解析 query-scoped Requirements，再创建 PENDING Progress。"""
        from ..progress.skill_progress import SkillProgress
        resolved = self.resolve_requirements(
            query or goal,
            routing_intent=routing_intent,
            routing_entities=routing_entities,
        )
        return SkillProgress(goal=goal,
                             required_dimensions=resolved.required_dimensions,
                             reason_codes=resolved.reason_codes)

    def is_complete(self, progress) -> bool:
        """Progress 的 remaining 为空才代表信息充分，而不是某个 Tool 调用过。"""
        return progress.complete and (
            self.completion_resolver(progress) if self.completion_resolver else True
        )

    def select_observations(self, observations):
        """Skill 可进一步收窄通用 Selector 的结果。"""
        return tuple(self.observation_selector(observations)) if self.observation_selector else tuple(observations)

    def failure_action(self, missing=(), unavailable=False, retryable=False):
        """失败策略返回控制动作；实际重试次数仍由 Harness 强制。"""
        if self.failure_resolver:
            return self.failure_resolver(missing, unavailable, retryable)
        return 'REQUEST_INPUT' if missing else ('HANDOFF' if unavailable else 'CONTINUE')

    def unload_reason(self, terminal_status: str) -> str:
        """Skill 结束时给出可审计的生命周期原因。"""
        return f'{self.name}@{self.version} 以 {terminal_status} 结束'
