"""A 层 ToolResult 的参考实现：执行是否成功与业务是否满足条件是两件事。

调用方：只读 Tool 和 Registry。消费者：Harness 与 ObservationFactory。
例如 success=True、participation_limit_reached=True 表示查询成功、资格受限。
失败数据不得进入业务 Observation；metadata 只允许技术计数，不保存认证数据。
"""
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ToolResult:
    """每一次实际执行（包含自动重试）有自己的结果和 attempt。"""

    tool_name: str
    success: bool
    data: dict[str, Any] | None
    error_code: str | None
    error_message: str
    retryable: bool
    source: str
    duration_ms: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    attempt: int = 1

    def __post_init__(self):
        """拒绝矛盾的执行状态；业务条件失败必须放在成功 data 内。"""
        if not self.tool_name or not self.source or self.attempt < 1:
            raise ValueError("结果缺少工具、来源或合法执行序号")
        if self.duration_ms < 0:
            raise ValueError("耗时不能为负")
        if self.success and (self.error_code or self.retryable or not isinstance(self.data, dict)):
            raise ValueError("成功结果必须是业务对象且没有执行错误")
        if not self.success and (not self.error_code or self.data is not None):
            raise ValueError("失败结果必须有稳定错误码且不能携带业务事实")
        if set(self.metadata) - {"http_status", "input_size", "result_size"}:
            raise ValueError("结果元信息含未允许字段")

    @classmethod
    def success_result(cls, tool_name, data, *, source="reference_stub", duration_ms=0, attempt=1):
        """复制成功数据；空字典和空数组不按真假值丢弃。"""
        return cls(tool_name, True, deepcopy(data), None, "", False, source,
                   duration_ms=duration_ms, attempt=attempt)

    @classmethod
    def failure_result(cls, tool_name, error_code, *, retryable=False,
                       source="reference_stub", duration_ms=0, attempt=1):
        """仅返回安全文案；不接收原始堆栈、SQL 或认证 Header。"""
        return cls(tool_name, False, None, error_code, "暂时无法取得所需业务事实",
                   retryable, source, duration_ms=duration_ms, attempt=attempt)

    @property
    def message(self):
        """保留既有参考调用方使用的 message 只读别名。"""
        return self.error_message
