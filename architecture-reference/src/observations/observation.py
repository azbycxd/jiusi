"""A 层事实 Observation 与 B 层工厂实现；成功查询后才生成业务快照。

工厂接收已通过 Tool result_schema 校验的 ToolResult，并再做 JSON/脱敏边界检查。
失败不生成 Observation；契约异常抛出而不能偷换为 success。对象 ID 区分同一
Tool 的多次调用。这里不实现事实 TTL；消费者只应使用当前任务的有效快照。
"""
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4
import math
import re

FORBIDDEN = {"userid", "authenticateduserid", "token", "authorization", "header",
             "headers", "sql", "rediskey", "baseurl", "sourcefiles", "stack", "apikey",
             "availabletools", "rootcause", "cannotjoinreason", "recommendation"}


def normalize_key(key):
    """统一安全字段拼写，防止下划线和大小写绕过。"""
    return re.sub(r"[^a-z0-9]", "", str(key).lower())


def sanitize(value):
    """深拷贝 JSON 值；拒绝内部字段，保留 0、False、None 和 []。"""
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
                raise ValueError("事实键不是可寻址业务字段")
            if normalize_key(key) in FORBIDDEN:
                raise ValueError("事实包含禁止暴露的内部字段")
            result[key] = sanitize(item)
        return result
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    if value is None or type(value) in (str, int, bool):
        return value
    if type(value) is float and math.isfinite(value):
        return value
    raise ValueError("事实包含非 JSON 数据")


def resolve_path(data, path):
    """支持 candidate_teams、candidate_teams[0].team_id；越界/负索引拒绝。"""
    if not path:
        raise KeyError("证据路径不能为空")
    parts = re.findall(r"[A-Za-z_][A-Za-z0-9_]*|\[\d+\]", path)
    rebuilt = ""
    current = data
    for part in parts:
        rebuilt += part if part.startswith("[") or not rebuilt else "." + part
        if part.startswith("["):
            if not isinstance(current, list):
                raise KeyError(path)
            index = int(part[1:-1])
            if index >= len(current):
                raise KeyError(path)
            current = current[index]
        else:
            if not isinstance(current, dict) or part not in current:
                raise KeyError(path)
            current = current[part]
    if rebuilt != path or not parts:
        raise KeyError(path)
    return deepcopy(current)


@dataclass(frozen=True)
class Observation:
    """成功事实快照；evidence 由工厂从同一份 data 提取。"""

    observation_id: str
    tool_name: str
    data: dict[str, Any]
    source: str
    created_at: str
    evidence: tuple = field(default_factory=tuple)
    sequence_no: int = 1

    @classmethod
    def from_tool_result(cls, result, sequence_no=1):
        """便利入口：失败返回 None，成功经工厂校验。"""
        return ObservationFactory().create(result, sequence_no)

    def get_path(self, path):
        """返回路径值副本，防止外部修改已注册事实。"""
        return resolve_path(self.data, path)

    def has_path(self, path):
        """不存在与空集合严格区分。"""
        try:
            self.get_path(path)
            return True
        except KeyError:
            return False

    @property
    def facts(self):
        """兼容前批参考中 facts 的命名。"""
        return deepcopy(self.data)


class ObservationFactory:
    """Tool 成功 → 契约检查 → 脱敏 → 快照 → Evidence 提取。"""

    def create(self, result, sequence_no=1):
        """只有成功结果生成 Observation，空业务集合也是完整成功。"""
        from .evidence import extract_evidence
        if not result.success:
            return None
        if not isinstance(result.data, dict) or sequence_no < 1:
            raise ValueError("TOOL_CONTRACT_FAILURE")
        data = sanitize(result.data)
        observation_id = uuid4().hex
        created_at = datetime.now(timezone.utc).isoformat()
        evidence = extract_evidence(observation_id, result.tool_name, data,
                                    result.source, created_at)
        return Observation(observation_id, result.tool_name, data, result.source,
                           created_at, evidence, sequence_no)
