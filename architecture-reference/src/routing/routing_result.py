"""Router 的结构化输出；它描述任务类别，不描述下一步 Tool。"""
from dataclasses import dataclass, field
from enum import Enum


class Intent(str, Enum):
    PARTICIPATION_DIAGNOSIS = "PARTICIPATION_DIAGNOSIS"
    ORDER_DIAGNOSIS = "ORDER_DIAGNOSIS"
    JOINABLE_TEAM = "JOINABLE_TEAM"
    RULE_QA = "RULE_QA"
    UNKNOWN = "UNKNOWN"


class RoutingSource(str, Enum):
    RULE = "RULE"
    LLM = "LLM"
    FALLBACK = "FALLBACK"


@dataclass(frozen=True)
class RoutingResult:
    """可审计的路由结论；intent_switch 只表示任务切换，不执行切换。"""

    intent: Intent
    skill_name: str | None
    entities: dict[str, object] = field(default_factory=dict)
    confidence: float = 0.0
    reason_code: str = "LOW_CONFIDENCE"
    source: RoutingSource = RoutingSource.FALLBACK
    intent_switch: bool = False
    matched_signals: tuple[str, ...] = ()

    def __post_init__(self):
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("路由置信度必须位于 0..1")
        if self.intent is Intent.UNKNOWN and self.skill_name is not None:
            raise ValueError("UNKNOWN 不能绑定 Skill")


INTENT_TO_SKILL = {
    Intent.PARTICIPATION_DIAGNOSIS: "participation_diagnosis",
    Intent.ORDER_DIAGNOSIS: "order_diagnosis",
    Intent.JOINABLE_TEAM: "joinable_team",
    Intent.RULE_QA: "rule_qa",
}
