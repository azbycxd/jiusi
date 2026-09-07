"""A 层参数 Contract 的标准库参考实现。

格式检查包含必填、类型、范围、枚举、长度和额外字段。所有模型参数使用
HTTP/Tool 的别名，例如 outTradeNo；Python 对象可使用 out_trade_no。
这里不推断订单真实格式，也不从自然语言猜实体。来源验证在 GroundingGuard。
"""
from dataclasses import dataclass
from typing import ClassVar
import re


@dataclass(frozen=True)
class ArgumentField:
    """一个字段的确定性规则；禁止 bool 被当成 int 通过。"""

    kind: type
    required: bool = True
    minimum: int | None = None
    maximum: int | None = None
    min_length: int = 1
    max_length: int = 128
    choices: tuple = ()
    pattern: str | None = None

    def normalize(self, value):
        """返回规范值；错误为 ValueError，调用层再映射稳定错误码。"""
        if type(value) is not self.kind:
            raise ValueError("参数类型错误")
        if self.kind is str:
            value = value.strip()
            if not self.min_length <= len(value) <= self.max_length:
                raise ValueError("字符串长度不合法")
            if any(ord(char) < 32 for char in value):
                raise ValueError("参数含控制字符")
            if self.pattern and re.fullmatch(self.pattern, value) is None:
                raise ValueError("字符串格式不合法")
        if self.kind is int:
            if self.minimum is not None and value < self.minimum:
                raise ValueError("数值小于允许范围")
            if self.maximum is not None and value > self.maximum:
                raise ValueError("数值超出允许范围")
        if self.choices and value not in self.choices:
            raise ValueError("参数不属于允许枚举")
        return value


def validate_schema(arguments, schema):
    """Schema 不包含 userId；未知字段直接拒绝而非悄悄删除。"""
    if not isinstance(arguments, dict) or set(arguments) - set(schema):
        raise ValueError("参数必须是对象且不能有额外字段")
    normalized = {}
    for name, rule in schema.items():
        if name not in arguments:
            if rule.required:
                raise ValueError("必填参数缺失")
            continue
        normalized[name] = rule.normalize(arguments[name])
    return normalized


class ArgumentsContract:
    """可序列化的参数基类；单独模型让 Tool 契约能被审阅和测试。"""

    schema: ClassVar[dict[str, ArgumentField]]
    aliases: ClassVar[dict[str, str]]

    @classmethod
    def from_mapping(cls, arguments):
        """先校验模型可控对象，再构建明确的参数类型。"""
        values = validate_schema(arguments, cls.schema)
        return cls(**{cls.aliases[name]: value for name, value in values.items()})

    def to_mapping(self):
        """只输出业务参数的 Tool 别名，不输出可信身份。"""
        return {name: getattr(self, attr) for name, attr in self.aliases.items()}


@dataclass(frozen=True)
class OrderFactsArguments(ArgumentsContract):
    """订单号支持非纯数字；仅约束长度与控制字符。"""

    out_trade_no: str
    schema = {"outTradeNo": ArgumentField(str)}
    aliases = {"outTradeNo": "out_trade_no"}


@dataclass(frozen=True)
class ActivityFactsArguments(ArgumentsContract):
    """活动标识是正整数；上限是参考传输边界而非场景绑定。"""

    activity_id: int
    schema = {"activityId": ArgumentField(int, minimum=1, maximum=2**63-1)}
    aliases = {"activityId": "activity_id"}


@dataclass(frozen=True)
class EligibilityFactsArguments(ActivityFactsArguments):
    """资格查询只有活动标识；用户始终取自可信上下文。"""


@dataclass(frozen=True)
class JoinableTeamFactsArguments(ActivityFactsArguments):
    """候选团查询只有活动标识；不允许传 SQL 或团队筛选后门。"""


@dataclass(frozen=True)
class RuleSearchArguments(ArgumentsContract):
    """检索文本可包含中文；上限防止无界输入。"""

    query: str
    schema = {"query": ArgumentField(str, max_length=1000)}
    aliases = {"query": "query"}
