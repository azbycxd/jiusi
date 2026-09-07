"""【C 生产扩展，当前未实现】Token 聚合与运行时价格协议，不内置虚构价格。"""
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class TokenUsage:
    input_tokens:int=0
    output_tokens:int=0
    cached_tokens:int=0
    estimated_cost:float|None=None
    def __add__(self,other):
        costs=None if self.estimated_cost is None or other.estimated_cost is None else self.estimated_cost+other.estimated_cost
        return TokenUsage(self.input_tokens+other.input_tokens,self.output_tokens+other.output_tokens,
                          self.cached_tokens+other.cached_tokens,costs)


class ModelPricing(Protocol):
    def estimate(self,model:str,usage:TokenUsage)->float: ...


class CostCalculator:
    def __init__(self,pricing:ModelPricing): self.pricing=pricing
    def calculate(self,model,usage): return self.pricing.estimate(model,usage)
