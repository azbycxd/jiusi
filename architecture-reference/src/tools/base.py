"""A 层 Tool 自描述接口的教学实现；四个 Facts 和一个 RAG Tool 都是只读。

AgentTool 定义动作，不规划业务任务；Skill 是任务边界，Registry 是能力集合。
未来写 Tool 需要确认、幂等、审计、事务和补偿策略，本批不实现写操作。
共同执行壳只负责参数、身份、契约和错误映射；子类选择各自 Client 方法。
"""
from abc import ABC, abstractmethod
from copy import deepcopy
from dataclasses import dataclass
from enum import Enum
from time import perf_counter
from .tool_result import ToolResult
from ..observations.observation import sanitize


class SideEffectLevel(str, Enum):
    """声明副作用；枚举存在不代表当前实现了写型工具。"""

    READ_ONLY = "READ_ONLY"
    IDEMPOTENT_WRITE = "IDEMPOTENT_WRITE"
    NON_IDEMPOTENT_WRITE = "NON_IDEMPOTENT_WRITE"


@dataclass(frozen=True)
class RepeatPolicy:
    """限制模型主动相同调用，自动重试不计入此政策。"""

    repeatable: bool = False
    max_same_call: int = 1

    def __post_init__(self):
        """安全上限示例必须为正，不声称为实验最优。"""
        if self.max_same_call < 1:
            raise ValueError("相同调用上限必须为正")


@dataclass(frozen=True)
class ToolMetadata:
    """仅业务 Schema 会进入模型，Client 实例和身份不在 metadata 内。"""

    name: str
    description: str
    version: str
    arguments_schema: dict
    result_schema: dict
    repeat_policy: RepeatPolicy
    timeout_ms: int
    side_effect_level: SideEffectLevel


class ToolExecutionError(Exception):
    """Client 边界的稳定错误；消息不得包含原始下游异常。"""

    def __init__(self, code, retryable=False):
        super().__init__("工具执行失败")
        self.code = code
        self.retryable = retryable


class AgentTool(ABC):
    """共同只读执行壳，子类不接触完整 AgentState，只接收 AuthContext。"""

    name: str
    description: str
    arguments_type: type
    result_schema: dict
    version = "reference-1"
    repeat_policy = RepeatPolicy()
    timeout_ms = 3000
    side_effect_level = SideEffectLevel.READ_ONLY
    source = "reference_stub"
    # 仅供可观测性/Context 的语义提示；v1.1 Completion 绝不读取它。
    dimension: str | None = None

    @property
    def arguments_schema(self):
        """Schema 来自参数类型，Registry 没有 Tool 名特判。"""
        return self.arguments_type.schema

    def metadata(self):
        """提供可审计的完整元信息副本。"""
        return ToolMetadata(self.name, self.description, self.version,
                            deepcopy(self.arguments_schema), deepcopy(self.result_schema),
                            self.repeat_policy, self.timeout_ms, self.side_effect_level)

    def describe(self):
        """生成模型可读的 JSON 描述；不暴露 Runtime 控制对象。"""
        fields = {}
        for name, rule in self.arguments_schema.items():
            fields[name] = {"type": rule.kind.__name__, "required": rule.required,
                            "minimum": rule.minimum, "maximum": rule.maximum,
                            "max_length": rule.max_length}
        return {"name": self.name, "description": self.description,
                "version": self.version, "arguments_schema": fields}

    def validate_arguments(self, arguments):
        """返回已归一化的参数对象；来源仍需 Harness 独立验证。"""
        return self.arguments_type.from_mapping(arguments)

    def validate_result(self, data):
        """检查必需结果字段与 JSON 边界；额外内部字段不可作为事实。"""
        if not isinstance(data, dict):
            raise ValueError("返回值不是业务对象")
        for name, kind in self.result_schema.items():
            if name not in data or type(data[name]) is not kind:
                raise ValueError("结果缺少字段或类型不匹配")
        return sanitize(data)

    def run(self, arguments, trusted_context, *, attempt=1):
        """依次验证、提取身份、调用 Client、规范结果、映射稳定失败。"""
        from ..harness.identity_guard import IdentityGuard
        from ..harness.capability_guard import GuardViolation
        started = perf_counter()
        try:
            IdentityGuard().validate_model_arguments(arguments)
            normalized = self.validate_arguments(arguments)
            auth = IdentityGuard().build_auth_context(trusted_context)
            data = self._invoke(normalized, auth)
            try:
                data = self.validate_result(data)
            except (ValueError, TypeError):
                raise ToolExecutionError("TOOL_CONTRACT_FAILURE") from None
            elapsed = round((perf_counter() - started) * 1000)
            if elapsed > self.timeout_ms:
                raise TimeoutError()
            return ToolResult.success_result(self.name, data, source=self.source,
                                             duration_ms=elapsed, attempt=attempt)
        except TimeoutError:
            code, retryable = "TOOL_TIMEOUT", True
        except ConnectionError:
            code, retryable = "TOOL_CONNECTION_ERROR", True
        except ToolExecutionError as error:
            code, retryable = error.code, error.retryable
        except GuardViolation as error:
            code, retryable = error.code, False
        except PermissionError:
            code, retryable = "AUTH_REQUIRED", False
        except (ValueError, TypeError):
            code, retryable = "INVALID_ARGUMENT", False
        except Exception:
            code, retryable = "TOOL_UNEXPECTED_ERROR", False
        return ToolResult.failure_result(self.name, code, retryable=retryable,
                                         source=self.source, attempt=attempt,
                                         duration_ms=round((perf_counter()-started)*1000))

    @abstractmethod
    def _invoke(self, arguments, auth):
        """子类只组合业务调用，禁止真实 DB/Redis/HTTP 访问。"""
        raise NotImplementedError("由具体只读 Tool 提供参考调用")
