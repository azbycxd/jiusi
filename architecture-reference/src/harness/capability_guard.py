"""A 层能力白名单的参考实现：在执行动作前做三层交集检查。

输入是 Skill、Runtime allowlist、当前 Registry；不是模型自报的工具清单。
例如 Participation Skill 中请求 refund_order，即使全局存在也不得执行。
Prompt 可能被注入覆盖，确定性许可必须在动作之前执行。
失败抛 GuardViolation：只有稳定 code 和安全文案，不包含身份或参数值。
"""


class GuardViolation(PermissionError):
    """所有 Guard 的结构化拒绝，调用方可映射到安全 HANDOFF。"""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class CapabilityGuard:
    """工具必须同时属于 Skill、Runtime、Registry。"""

    def validate(self, tool_name, skill, runtime_allowlist, registry):
        """未知、未注册、不在当前任务范围中的工具全部拒绝。"""
        if not isinstance(tool_name, str):
            raise GuardViolation("CAPABILITY_DENIED", "工具名称无效")
        layers = (set(skill.allowed_tools), set(runtime_allowlist), registry.names())
        if any(tool_name not in allowed for allowed in layers):
            raise GuardViolation("CAPABILITY_DENIED", "当前任务没有此工具能力")
        return registry.get(tool_name).metadata()
