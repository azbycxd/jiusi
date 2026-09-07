"""v1.1 Evidence-driven Progress：状态由 Obligation Evaluation 推导，不由 Tool 名推进。"""
from dataclasses import dataclass, field
from .evidence_obligation import ObligationStatus


@dataclass
class SkillProgress:
    """当前任务的 query-scoped Evidence 充分性快照。"""

    goal: str
    required_dimensions: frozenset[str]
    reason_codes: tuple[str, ...] = ()
    obligation_status: dict[str, ObligationStatus] = field(default_factory=dict)
    satisfied_evidence: dict[str, dict[str, tuple[str, ...]]] = field(default_factory=dict)
    missing_conditions: dict[str, tuple[str, ...]] = field(default_factory=dict)

    def __post_init__(self):
        self.required_dimensions = frozenset(self.required_dimensions)
        self.reason_codes = tuple(self.reason_codes)
        unknown = set(self.obligation_status) - set(self.required_dimensions)
        if unknown:
            raise ValueError("obligation_status 含非 Required Dimension")
        for dimension in self.required_dimensions:
            self.obligation_status.setdefault(dimension, ObligationStatus.PENDING)
            self.satisfied_evidence.setdefault(dimension, {})
            self.missing_conditions.setdefault(dimension, ())

    def apply_evaluations(self, evaluations):
        """原子替换全部 Required Dimension 评估；调用时机由 Harness 决定。"""
        mapping = {item.dimension: item for item in evaluations}
        if set(mapping) != set(self.required_dimensions):
            raise ValueError("Obligation Evaluation 与 required_dimensions 不一致")
        self.obligation_status = {name: item.status for name, item in mapping.items()}
        self.satisfied_evidence = {
            name: {condition: tuple(ids) for condition, ids in item.satisfied_evidence}
            for name, item in mapping.items()
        }
        self.missing_conditions = {
            name: tuple(item.missing_conditions) for name, item in mapping.items()
        }

    @property
    def satisfied_dimensions(self):
        return frozenset(
            name for name, status in self.obligation_status.items()
            if status is ObligationStatus.SATISFIED
        )

    @property
    def checked_dimensions(self):
        """Deprecated compatibility：只读别名；v1.1 核心代码不得人工 mark checked。"""
        return self.satisfied_dimensions

    @property
    def remaining_dimensions(self):
        return self.required_dimensions - self.satisfied_dimensions

    @property
    def complete(self):
        return not self.remaining_dimensions

    def snapshot(self):
        """模型安全视图展示每个维度状态、已满足 Evidence 和缺失 Condition。"""
        dimensions = {}
        for name in sorted(self.required_dimensions):
            dimensions[name] = {
                "status": self.obligation_status[name].value,
                "satisfied_evidence": {
                    condition: tuple(ids)
                    for condition, ids in sorted(self.satisfied_evidence[name].items())
                },
                "missing_conditions": tuple(self.missing_conditions[name]),
            }
        return {
            "goal": self.goal,
            "reason_codes": tuple(self.reason_codes),
            "required_dimensions": tuple(sorted(self.required_dimensions)),
            "dimensions": dimensions,
            "satisfied_dimensions": tuple(sorted(self.satisfied_dimensions)),
            "remaining_dimensions": tuple(sorted(self.remaining_dimensions)),
            "complete": self.complete,
        }
