"""A 层有限 Retry 的参考决策：retry_count 是首次失败之后的额外调用次数。

Retry 是同一动作自动再执行；Repeat 是模型再次提出相同动作。
Fallback 是切换安全处理方式；Replan 是模型提出新路径。本 Policy 不做后二者。
backoff_ms 仅提供调度建议，测试和 Reference 不进行 sleep。
写 Tool 即使报瞬时失败也不能自动重试，必须先建立幂等与确认契约。
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class RetryDecision:
    """retry_index 是将发生的额外重试序号，停止时保留已用序号。"""

    should_retry: bool
    retry_index: int
    reason: str
    backoff_ms: int


class RetryPolicy:
    """只读重试安全上限与副作用策略分开判断。"""

    def decide(self, classification, retry_count, max_retries, *, read_only=True):
        """max_retries=1 表示首次执行加最多一次重试。"""
        if retry_count < 0 or max_retries < 0:
            raise ValueError("重试次数必须非负")
        if not read_only:
            return RetryDecision(False, retry_count, "SIDE_EFFECT_RETRY_FORBIDDEN", 0)
        if not classification.retryable:
            return RetryDecision(False, retry_count, "NON_RETRYABLE", 0)
        if retry_count >= max_retries:
            return RetryDecision(False, retry_count, "RETRY_EXHAUSTED", 0)
        next_index = retry_count + 1
        return RetryDecision(True, next_index, "TRANSIENT_FAILURE", min(100 * 2**min(retry_count, 6), 5000))
