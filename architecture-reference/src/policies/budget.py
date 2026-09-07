"""工程安全预算示例，不声称为全局最优。"""
from dataclasses import dataclass
@dataclass(frozen=True)
class RuntimeBudget: max_iterations:int=8; max_tool_calls:int=5; max_model_retries:int=1; max_tool_retries:int=1; max_same_call:int=1
