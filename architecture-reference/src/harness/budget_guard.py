"""B 层预算快照接口；A 层真实工程已有模型/工具计数限制。

token、耗时、成本是可选估算输入；Reference 没有收费服务或生产计费结论。
如果配置了某项预算但没有观测值，拒绝把未知当作零。BudgetDecision 返回
明确 reason，使调用方能分辨预算耗尽和观测缺失；它不判断业务完整性。
"""
from dataclasses import dataclass
from .capability_guard import GuardViolation


@dataclass(frozen=True)
class BudgetSnapshot:
    """已消费资源；None 表示尚未计量。"""

    model_calls: int = 0
    tool_calls: int = 0
    estimated_tokens: int | None = None
    elapsed_ms: int | None = None
    estimated_cost: float | None = None


@dataclass(frozen=True)
class BudgetDecision:
    """预算准入结果，可用于 Trace 的稳定分类。"""

    allowed: bool
    reason: str


class BudgetGuard:
    """调用前做预测增加，调用后可用新 snapshot 检查硬上限。"""

    def evaluate(self, snapshot, limits, *, next_model=0, next_tool=0):
        """使用明确配置的上限，缺失可选计量时 fail closed。"""
        values = {"max_model_calls": snapshot.model_calls + next_model,
                  "max_tool_calls": snapshot.tool_calls + next_tool,
                  "max_tokens": snapshot.estimated_tokens,
                  "max_elapsed_ms": snapshot.elapsed_ms,
                  "max_cost": snapshot.estimated_cost}
        for name, value in values.items():
            if name not in limits:
                continue
            if value is None:
                return BudgetDecision(False, "BUDGET_MEASUREMENT_MISSING")
            if value < 0 or value > limits[name]:
                return BudgetDecision(False, "BUDGET_EXCEEDED")
        return BudgetDecision(True, "WITHIN_BUDGET")

    def validate(self, snapshot, limits, **increments):
        """不允许时转成结构化 GuardViolation，禁止静默忽略预算。"""
        decision = self.evaluate(snapshot, limits, **increments)
        if not decision.allowed:
            raise GuardViolation(decision.reason, "资源预算不允许继续")
        return decision
