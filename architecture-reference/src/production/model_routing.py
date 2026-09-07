"""【生产化扩展设计，当前真实项目未实现】按能力、延迟、成本与 Context 的模型路由。"""
from dataclasses import dataclass


@dataclass(frozen=True)
class ModelProfile:
    name:str
    max_context:int
    supports_tools:bool
    supports_structured_output:bool
    quality_tier:int
    latency_tier:int
    cost_tier:int


class ModelRouter:
    def __init__(self,profiles): self.profiles=tuple(profiles)
    def select(self,*,complexity,context_tokens,requires_tools,latency_tier=None,cost_tier=None):
        candidates=[p for p in self.profiles if p.max_context>=context_tokens
                    and (not requires_tools or p.supports_tools)
                    and p.supports_structured_output]
        if latency_tier is not None: candidates=[p for p in candidates if p.latency_tier<=latency_tier]
        if cost_tier is not None: candidates=[p for p in candidates if p.cost_tier<=cost_tier]
        required_quality=2 if complexity=="open_diagnosis" else 1
        candidates=[p for p in candidates if p.quality_tier>=required_quality]
        if not candidates: raise LookupError("没有满足约束的模型")
        return min(candidates,key=lambda p:(p.cost_tier,p.latency_tier,-p.quality_tier))
