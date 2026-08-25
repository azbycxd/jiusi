"""Stable Tool error taxonomy and safe exception-to-result conversion."""

from __future__ import annotations

from tools.schemas import ToolResult


class ToolTimeoutError(Exception):
    pass


class ToolConnectionError(Exception):
    pass


class ToolAuthorizationError(Exception):
    pass


class ToolInvalidArgumentError(Exception):
    pass


class ToolUnexpectedError(Exception):
    pass


def to_tool_result(error: Exception, *, source: str) -> ToolResult:
    """Return stable, user-safe outcomes without serializing exception text."""
    if isinstance(error, ToolTimeoutError):
        return ToolResult.infrastructure_failure("TOOL_TIMEOUT", "订单事实服务响应超时", retryable=True, source=source)
    if isinstance(error, ToolConnectionError):
        return ToolResult.infrastructure_failure("TOOL_CONNECTION_ERROR", "订单事实服务暂时不可用", retryable=True, source=source)
    if isinstance(error, ToolAuthorizationError):
        return ToolResult.infrastructure_failure("TOOL_AUTHORIZATION_ERROR", "当前账号无权执行订单诊断", retryable=False, source=source)
    if isinstance(error, ToolInvalidArgumentError):
        return ToolResult.infrastructure_failure("TOOL_INVALID_ARGUMENT", "订单诊断参数无效", retryable=False, source=source)
    return ToolResult.infrastructure_failure("TOOL_UNEXPECTED_ERROR", "订单诊断工具发生未预期错误", retryable=False, source=source)
