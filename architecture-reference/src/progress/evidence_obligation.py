"""B 层 Evidence Obligation：描述完成维度必须观察到什么，而非必须调用哪个 Tool。"""
from dataclasses import dataclass
from enum import Enum


class EvidenceMatchMode(str, Enum):
    EXACT = "EXACT"
    PREFIX = "PREFIX"


class ObligationStatus(str, Enum):
    PENDING = "PENDING"
    SATISFIED = "SATISFIED"


@dataclass(frozen=True)
class EvidenceCondition:
    """accepted_paths 是可信 Evidence 别名集合；任一路径都可满足同一事实条件。"""

    name: str
    accepted_paths: tuple[str, ...]
    match_mode: EvidenceMatchMode = EvidenceMatchMode.EXACT

    def __post_init__(self):
        paths = tuple(self.accepted_paths)
        if not self.name or not paths or any(not isinstance(path, str) or not path for path in paths):
            raise ValueError("EvidenceCondition 必须声明名称和合法 accepted_paths")
        if not isinstance(self.match_mode, EvidenceMatchMode):
            raise ValueError("Evidence Condition match_mode 必须是 EXACT 或 PREFIX")
        object.__setattr__(self, "accepted_paths", paths)


@dataclass(frozen=True)
class EvidenceObligationSpec:
    """一个 Dimension 的全部 Condition；全部满足才算信息收集充分。"""

    dimension: str
    conditions: tuple[EvidenceCondition, ...]

    def __post_init__(self):
        conditions = tuple(self.conditions)
        names = [item.name for item in conditions]
        if not self.dimension or not conditions or len(names) != len(set(names)):
            raise ValueError("Obligation 必须有维度和不重复的 Condition")
        object.__setattr__(self, "conditions", conditions)


@dataclass(frozen=True)
class ObligationEvaluation:
    """一次确定性评估结果；只表达证据充分性，不生成业务诊断。"""

    dimension: str
    status: ObligationStatus
    satisfied_evidence: tuple[tuple[str, tuple[str, ...]], ...]
    missing_conditions: tuple[str, ...]

    def evidence_for(self, condition_name: str) -> tuple[str, ...]:
        return dict(self.satisfied_evidence).get(condition_name, ())
