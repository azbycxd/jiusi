"""B 层 Query-scoped Requirement：把 Skill 能力空间与本次必须取证维度分离。"""
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ResolvedRequirements:
    """RequirementResolver 的确定性输出，不携带身份、Trace 或 Tool 错误。"""

    required_dimensions: frozenset[str]
    reason_codes: tuple[str, ...]

    def __post_init__(self):
        required = frozenset(self.required_dimensions)
        reasons = tuple(self.reason_codes)
        if any(not isinstance(item, str) or not item for item in required):
            raise ValueError("required_dimensions 必须是非空字符串集合")
        if not reasons or any(not isinstance(item, str) or not item for item in reasons):
            raise ValueError("Requirement 需要稳定 reason_codes")
        object.__setattr__(self, "required_dimensions", required)
        object.__setattr__(self, "reason_codes", reasons)


class RequirementResolver(Protocol):
    """只接收 Query 与基础路由语义；实现不得依赖身份、Trace 或 Tool 错误。"""

    def __call__(self, query: str, *, routing_intent=None,
                 routing_entities=None) -> ResolvedRequirements:
        ...
