"""A 层参数执行链的来源校验，Reference 使用 Runtime 提供的来源账本。

USER_INPUT 要对照已提取的用户实体；OBSERVATION 要对照特定 ID 的真实路径值。
RUNTIME 仅对照可信代码提供的值，UNKNOWN 拒绝。模型自报 source_type 不构成证明。
此 Guard 不决定答案引用了哪些 Evidence，两种职责独立测试。
"""
from .capability_guard import GuardViolation
from ..observations.provenance import SourceType


class ParameterGroundingGuard:
    """参数、来源声明、原始来源三者必须值相等且类型相等。"""

    def validate(self, arguments, provenance, *, user_values, observations, runtime_values):
        """所有参数必须都有且仅有一个来源，防止缺项或伪造值。"""
        ledger = list(provenance)
        names = [entry.parameter_name for entry in ledger]
        if len(names) != len(set(names)) or set(names) != set(arguments):
            self._reject()
        by_id = {observation.observation_id: observation for observation in observations}
        for entry in ledger:
            try:
                entry.validate_shape()
                if entry.source_type == SourceType.USER_INPUT:
                    original = user_values[entry.source_path]
                elif entry.source_type == SourceType.RUNTIME:
                    original = runtime_values[entry.source_path]
                elif entry.source_type == SourceType.OBSERVATION:
                    original = by_id[entry.source_observation_id].get_path(entry.source_path)
                else:
                    self._reject()
                value = arguments[entry.parameter_name]
                if type(value) is not type(original) or type(value) is not type(entry.parameter_value):
                    self._reject()
                if value != original or value != entry.parameter_value:
                    self._reject()
            except (ValueError, KeyError, TypeError, AttributeError):
                self._reject()
        return dict(arguments)

    @staticmethod
    def _reject():
        """统一错误码，不把实际订单、用户输入或来源值泄漏到异常。"""
        raise GuardViolation("PARAMETER_GROUNDING_FAILED", "参数未绑定可信来源")
