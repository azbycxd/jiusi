"""B 层超时/瞬时失败分类接口；不在本地强行中止任意 Python 线程。

HTTP timeout/connection/502/503 在只读动作下可有限重试。生产 Client 必须设置
自身传输超时，耗时检查不能替代真正的网络取消。本参考不进行真实网络调用。
权限、业务对象不存在、非法参数和未知异常不因 Provider 自报 retryable 而放行。
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class FailureClassification:
    """安全错误码和是否瞬时可恢复；用于 RetryPolicy。"""

    error_code: str
    retryable: bool
    category: str


class TimeoutPolicy:
    """分类负责可重试性，RetryPolicy 决定剩余次数。"""

    TRANSIENT = {"TOOL_TIMEOUT", "MODEL_TIMEOUT", "TOOL_CONNECTION_ERROR",
                 "MODEL_CONNECTION_ERROR", "HTTP_502", "HTTP_503"}
    BUSINESS = {"NOT_FOUND", "ACTIVITY_NOT_FOUND", "ORDER_NOT_FOUND_OR_NOT_AUTHORIZED",
                "BUSINESS_CONDITION_FAILED"}
    SECURITY = {"AUTH_REQUIRED", "FORBIDDEN", "INVALID_ARGUMENT"}

    def classify(self, error_code, declared_retryable=False):
        """只读动作瞬时白名单优先，其余错误默认不重试。"""
        if error_code in self.TRANSIENT:
            return FailureClassification(error_code, True, "TRANSPORT_FAILURE")
        if error_code in self.BUSINESS:
            return FailureClassification(error_code, False, "BUSINESS_FAILURE")
        if error_code in self.SECURITY:
            return FailureClassification(error_code, False, "SECURITY_FAILURE")
        return FailureClassification(error_code or "UNEXPECTED_ERROR", False, "CONTRACT_FAILURE")

    def validate_duration(self, duration_ms, timeout_ms):
        """这是完成后耗时检测，Reference 不假装实现线程级强制超时。"""
        if duration_ms > timeout_ms:
            return self.classify("TOOL_TIMEOUT")
        return None
