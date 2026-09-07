"""B 层执行参数溯源，映射真实 Parameter Grounding 边界。

Order Observation.references.activity_id 可以为候选团工具提供 activityId。
最终“没有候选团”的证据来自 candidate_teams=[]，不是 activityId 的来源记录。
来源声明本身不可信；Guard 必须把它与 Runtime 持有的输入实体或 Observation 对照。
"""
from dataclasses import dataclass
from enum import Enum
from typing import Any


class SourceType(str, Enum):
    """来源分类；UNKNOWN 一律拒绝，RUNTIME 必须由可信代码提供值。"""

    USER_INPUT = "USER_INPUT"
    OBSERVATION = "OBSERVATION"
    RUNTIME = "RUNTIME"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class ParameterProvenance:
    """一次参数值与来源路径的绑定，不携带身份凭证。"""

    parameter_name: str
    parameter_value: Any
    source_type: SourceType
    source_path: str
    source_observation_id: str | None = None

    def validate_shape(self):
        """结构错误在读取来源前拒绝，避免把模糊描述当成路径。"""
        if not self.parameter_name or not self.source_path:
            raise ValueError("参数来源缺少名称或路径")
        if self.source_type == SourceType.OBSERVATION and not self.source_observation_id:
            raise ValueError("Observation 来源必须有明确版本标识")
