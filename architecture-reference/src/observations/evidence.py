"""A 层 Evidence Grounding 的参考实现：精确定位 Observation 版本与事实值。

规范引用是 observation_id:path。为了阅读方便，也可用 tool_name.path；
若同一工具产生多个版本，该短名会变得歧义，必须提供完整 ID。Registry 从
Observation.data 重建证据，不信任外部伪造的 evidence 列表或值。
空集合作为叶节点注册，例如 candidate_teams=[]；非空数组按索引注册叶子。
"""
from copy import deepcopy
from dataclasses import dataclass
from typing import Any
import json


@dataclass(frozen=True)
class Evidence:
    """一个不可混淆的事实版本；返回副本避免外部修改空数组等容器值。"""

    evidence_id: str
    observation_id: str
    tool_name: str
    path: str
    value: Any
    source: str
    created_at: str


def extract_evidence(observation_id, tool_name, data, source, created_at):
    """深度遍历业务 JSON，保留空容器和所有 falsey 原始值。"""
    found = []

    def visit(value, path):
        if isinstance(value, dict) and value:
            for key, item in value.items():
                visit(item, f"{path}.{key}" if path else key)
        elif isinstance(value, list) and value:
            for index, item in enumerate(value):
                visit(item, f"{path}[{index}]")
        elif path:
            found.append(Evidence(f"{observation_id}:{path}", observation_id,
                                  tool_name, path, deepcopy(value), source, created_at))
    visit(data, "")
    return tuple(found)


class EvidenceRegistry:
    """当前任务的证据索引；绝不从 available_tools、source_files 建索引。"""

    def __init__(self):
        self._observations = {}
        self._evidence = {}
        self._aliases = {}

    def register_observation(self, observation):
        """拒绝同 ID 不同快照，避免旧引用被悄悄指向新事实。"""
        from .observation import sanitize
        snapshot = deepcopy(observation)
        if snapshot.observation_id in self._observations:
            if self._observations[snapshot.observation_id] != snapshot:
                raise ValueError("Observation 版本冲突")
            return
        data = sanitize(snapshot.data)
        entries = extract_evidence(snapshot.observation_id, snapshot.tool_name, data,
                                   snapshot.source, snapshot.created_at)
        self._observations[snapshot.observation_id] = snapshot
        for entry in entries:
            self._evidence[entry.evidence_id] = entry
            alias = f"{entry.tool_name}.{entry.path}"
            self._aliases.setdefault(alias, set()).add(entry.evidence_id)

    def resolve(self, path):
        """解析唯一版本；歧义、内部字段、不存在路径都抛 KeyError。"""
        identifier = path
        if identifier not in self._evidence:
            choices = self._aliases.get(path, set())
            if len(choices) != 1:
                raise KeyError("证据不存在或版本不唯一")
            identifier = next(iter(choices))
        return deepcopy(self._evidence[identifier])

    def exists(self, path):
        """检查索引存在性，不以 value 的布尔值判断。"""
        try:
            self.resolve(path)
            return True
        except (KeyError, TypeError):
            return False

    def list_available(self):
        """只公开安全 Evidence 数据，返回脱离内部容器的副本。"""
        return tuple(deepcopy(list(self._evidence.values())))

    def validate_used_evidence(self, used_evidence):
        """既验证引用也验证对象原值，拒绝复制 ID 后篡改 value。"""
        resolved = []
        for reference in used_evidence:
            path = reference.evidence_id if isinstance(reference, Evidence) else reference
            actual = self.resolve(path)
            if isinstance(reference, Evidence):
                same_value = json.dumps(reference.value, sort_keys=True, allow_nan=False) == json.dumps(
                    actual.value, sort_keys=True, allow_nan=False)
                if reference != actual or not same_value:
                    raise ValueError("证据引用与原值不一致")
            resolved.append(actual)
        return tuple(resolved)
