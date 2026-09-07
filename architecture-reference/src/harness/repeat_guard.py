"""A 层模型 Repeat 限制；动作前以规范参数生成稳定签名。

签名只含工具名和业务参数；不含身份、时间戳、Retry 序号。
只有真正接受的模型新动作由调用方写入 history；自动 Retry 使用原签名，
不再次记入模型调用历史。工程安全值 max_same_call 不是全局实验最优。
"""
import json
from .capability_guard import GuardViolation


class RepeatGuard:
    """repeatable=False 时最多一次；可重复时使用工具与 Runtime 上限交集。"""

    def signature(self, tool_name, normalized_arguments):
        """规范参数排序让键顺序变化不能绕过重复检测。"""
        return json.dumps([tool_name, normalized_arguments], ensure_ascii=False,
                          sort_keys=True, separators=(",", ":"), allow_nan=False)

    def validate(self, tool_name, normalized_arguments, history, policy, runtime_limit):
        """只检查不写入历史，所有 Guard 通过后才由执行入口记账。"""
        signature = self.signature(tool_name, normalized_arguments)
        maximum = min(policy.max_same_call if policy.repeatable else 1, runtime_limit)
        if maximum < 1 or history.count(signature) >= maximum:
            raise GuardViolation("TOOL_REPEAT_LIMIT", "同一业务动作已达重复上限")
        return signature
