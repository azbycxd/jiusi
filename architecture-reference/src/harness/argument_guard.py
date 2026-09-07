"""A 层格式 Guard；在 Tool 执行前检查自描述 Schema。

必填、类型、范围、枚举、格式和额外字段在工具参数模型中定义。
本 Guard 委托这些规则，返回规范化字典，供签名和 Grounding 使用。
格式合法不意味着来源可信：随机猜出的 activityId=100123 仍可能被下一层拒绝。
异常只携带 INVALID_ARGUMENT，不把提交的敏感参数回显到用户。
"""
from .capability_guard import GuardViolation


class ArgumentGuard:
    """参数类型是 Tool 的能力契约，不由 Prompt 或 Registry 的分支推断。"""

    def validate(self, arguments, arguments_contract):
        """成功返回规范值；失败统一映射稳定拒绝码。"""
        try:
            value = arguments_contract.from_mapping(arguments)
            return value.to_mapping()
        except (ValueError, TypeError, KeyError):
            raise GuardViolation("INVALID_ARGUMENT", "工具参数不符合格式契约") from None
