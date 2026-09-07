"""A 层显式 Registry 的完整参考实现。

注册阶段只接受 AgentTool 实例；不扫描模块、不自动暴露函数。
Registry 校验格式和结果接口，Harness 校验 Skill、身份、来源、预算和证据。
本类没有按 Tool 名的业务 if 分支，扩展由自描述 metadata 驱动。
注销仅用于 Reference 组装演示，不提供模型或公开 API 调用入口。
"""
from .base import AgentTool
from .tool_result import ToolResult


class ToolRegistry:
    """应用初始化时建立的工具表；返回描述副本避免外部污染。"""

    def __init__(self, tools=()):
        self._tools = {}
        for tool in tools:
            self.register(tool)

    def register(self, tool):
        """显式注册且拒绝重复名字，防止同名能力静默替换。"""
        if not isinstance(tool, AgentTool):
            raise TypeError("只允许注册 AgentTool")
        if not tool.name or tool.name in self._tools:
            raise ValueError("工具名称为空或重复")
        metadata = tool.metadata()
        if metadata.timeout_ms <= 0:
            raise ValueError("工具必须声明正超时")
        self._tools[tool.name] = tool

    def unregister(self, name):
        """Reference-only：模型不可调用，未知名称应暴露配置错误。"""
        if name not in self._tools:
            raise KeyError("工具未注册")
        del self._tools[name]

    def get(self, name):
        """精确查找；不接受任意函数名、HTTP 地址或模糊匹配。"""
        if name not in self._tools:
            raise KeyError("工具未注册")
        return self._tools[name]

    def names(self):
        """给 CapabilityGuard 当前注册能力集合。"""
        return frozenset(self._tools)

    def describe(self, names=None):
        """只描述指定 Skill 的工具，拒绝未注册声明。"""
        selected = self.names() if names is None else names
        return [self.get(name).describe() for name in selected]

    def list_metadata(self):
        """供确定性 Runtime 和人工审查读取完整元信息。"""
        return tuple(tool.metadata() for tool in self._tools.values())

    def validate_arguments(self, name, arguments):
        """使用 Tool 自带参数模型，不在 Registry 硬编码字段。"""
        return self.get(name).validate_arguments(arguments)

    def call(self, name, arguments, trusted_context, *, attempt=1):
        """执行 Tool 并约束返回接口；Guard 的业务前置条件由 Harness 完成。"""
        tool = self.get(name)
        result = tool.run(arguments, trusted_context, attempt=attempt)
        if not isinstance(result, ToolResult) or result.tool_name != name:
            return ToolResult.failure_result(name, "TOOL_CONTRACT_FAILURE")
        if result.success:
            try:
                tool.validate_result(result.data)
            except (ValueError, TypeError):
                return ToolResult.failure_result(name, "TOOL_CONTRACT_FAILURE")
        return result

    def repeat_policy(self, name):
        """把工具自身的 RepeatPolicy 交给 Harness 合并预算。"""
        return self.get(name).repeat_policy
