"""【生产化扩展设计，当前真实项目未实现】Fallback 不得把规则知识伪装成实时事实。"""
from dataclasses import dataclass
from enum import Enum


class FailureDomain(str,Enum): MODEL="MODEL"; REALTIME_FACTS="REALTIME_FACTS"; RULE_KNOWLEDGE="RULE_KNOWLEDGE"


@dataclass(frozen=True)
class FallbackDecision:
    action:str
    target:str|None
    reason:str


class FallbackPolicy:
    def decide(self,domain,*,backup_model=None):
        if domain is FailureDomain.MODEL and backup_model:
            return FallbackDecision("USE_BACKUP_MODEL",backup_model,"主模型暂时不可用")
        if domain is FailureDomain.REALTIME_FACTS:
            return FallbackDecision("HANDOFF",None,"实时事实失败，禁止用 RAG 替代")
        return FallbackDecision("HANDOFF",None,"当前证据源不可用")
