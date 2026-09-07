"""B 层 Skill 完成守卫，映射真实 DiagnosisProgress 完成约束。

ANSWER 前读取 query-scoped required/obligation status/remaining；不规定工具顺序。
所有必需维度已完成后，额外查询是否必要交给 Skill 的完成扩展政策；
默认不继续探索。政策可允许仍需规则解释的动作，但不能越过 capability。
"""
from .capability_guard import GuardViolation


class CompletionGuard:
    """业务完成条件与资源上限分离。"""

    def validate(self, skill, progress, decision, *, allow_additional=None):
        """缺失进度、缺必要维度、过早回答或无意义扩展均拒绝。"""
        action = getattr(decision.action, "value", decision.action)
        possible = set(skill.possible_dimensions)
        if progress is None:
            if possible:
                raise GuardViolation("COMPLETION_INCOMPLETE", "当前任务没有完成进度")
            return
        required = set(progress.required_dimensions)
        if not required <= possible:
            raise GuardViolation("COMPLETION_ARCHITECTURE_ERROR", "Required 超出 Possible")
        if set(progress.obligation_status) != required:
            raise GuardViolation("COMPLETION_INCOMPLETE", "进度与 Evidence Obligation 不一致")
        remaining = progress.remaining_dimensions
        if action == "ANSWER" and not progress.complete:
            raise GuardViolation("COMPLETION_INCOMPLETE", "仍有 Evidence Condition 未满足")
        if action == "CALL_TOOL" and not remaining:
            allowed = allow_additional and allow_additional(skill, progress, decision)
            if not allowed:
                raise GuardViolation("COMPLETION_ALREADY_SUFFICIENT", "事实充分后无需继续调用工具")
